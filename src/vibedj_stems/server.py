"""HTTP e WebSocket em 127.0.0.1. O front manda a faixa e ouve o andamento. Os WAV saem pela caixa de pasta."""

import asyncio
import re
import threading

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from starlette.websockets import WebSocketState

from vibedj_stems.config import FONTE_CADEIRA, VERSAO

_LOCAL = re.compile(r"http://(localhost|127\.0\.0\.1)(:\d+)?$")
_CAMPOS = ("id", "nome", "state", "stage", "rotulo", "bloco", "blocos", "progress", "erro", "stems", "destino")
_STEMS = {f"{fonte}.wav" for fonte in FONTE_CADEIRA}


def origem_permitida(origem: str | None, extras: list[str]) -> bool:
    """localhost em qualquer porta, mais as origens do config.json (o domínio publicado)."""
    if not origem:
        return False
    return origem in extras or bool(_LOCAL.fullmatch(origem))


def visao(job: dict) -> dict:
    """O que o front precisa, sem caminho de disco nem hash."""
    return {campo: job[campo] for campo in _CAMPOS}


def mensagem(job: dict) -> dict:
    """Pacote do WebSocket. `concluido` e `falha` encerram o acompanhamento.

    job: visão interna do JobStore, com state, progress e stems.
    """
    if job["state"] == "done":
        tipo = "concluido"
    elif job["state"] == "error":
        tipo = "falha"
    else:
        tipo = "andamento"
    return {"tipo": tipo, **visao(job)}


class Sala:
    """Leva o aviso da thread do worker até a fila de cada WebSocket."""

    def __init__(self):
        self._ouvintes: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._trava = threading.Lock()

    def assinar(self, job_id: str, loop: asyncio.AbstractEventLoop, fila: asyncio.Queue) -> None:
        """Registra a fila. `publicar` a acorda a partir da thread do worker.

        job_id: job que esta conexão acompanha.
        loop: loop em que a fila é consumida.
        fila: recebe um token a cada mudança; o valor em si é relido do store.
        """
        with self._trava:
            self._ouvintes.setdefault(job_id, []).append((loop, fila))

    def sair(self, job_id: str, fila: asyncio.Queue) -> None:
        """Tira a fila quando o socket fecha.

        job_id: job da assinatura.
        fila: a mesma instância passada a `assinar`.
        """
        with self._trava:
            restantes = [par for par in self._ouvintes.get(job_id, []) if par[1] is not fila]
            if restantes:
                self._ouvintes[job_id] = restantes
            else:
                self._ouvintes.pop(job_id, None)

    def publicar(self, job_id: str) -> None:
        """Acorda quem ouve este job. Pode ser chamado fora do loop.

        job_id: job que mudou de etapa, progresso ou estado.
        """
        with self._trava:
            ouvintes = list(self._ouvintes.get(job_id, ()))
        for loop, fila in ouvintes:
            loop.call_soon_threadsafe(_acordar, fila)


def _acordar(fila: asyncio.Queue) -> None:
    """Põe um token na fila. Ignora fila fechada ou loop que já encerrou."""
    try:
        fila.put_nowait(True)
    except Exception:
        return


def criar_app(store, config: dict, modelos) -> FastAPI:
    """`modelos` expõe pronto, erro e mensagem. Os testes passam um dublê."""
    app = FastAPI(title="VibeDJ Stems", version=VERSAO)
    extras = list(config.get("origens", []))
    sala = Sala()
    store.ao_mudar = sala.publicar

    @app.middleware("http")
    async def cors(request, call_next):
        origem = request.headers.get("origin")
        if request.method == "OPTIONS":
            resposta = Response(status_code=204)
        else:
            resposta = await call_next(request)
        if origem_permitida(origem, extras):
            resposta.headers["Access-Control-Allow-Origin"] = origem
            resposta.headers["Vary"] = "Origin"
            resposta.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            resposta.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
            resposta.headers["Access-Control-Allow-Private-Network"] = "true"
        return resposta

    @app.get("/health")
    def health():
        if modelos.erro:
            status = "error"
        elif modelos.pronto.is_set():
            status = "ready"
        else:
            status = "loading"
        return {
            "status": status,
            "version": VERSAO,
            "provider": (config.get("provedores") or ["CPUExecutionProvider"])[0],
            "message": modelos.mensagem,
        }

    @app.post("/jobs", status_code=202)
    async def criar_job(file: UploadFile = File(...)):
        dados = await file.read()
        if not dados:
            raise HTTPException(400, "Arquivo vazio.")
        if len(dados) > config["upload_max"]:
            raise HTTPException(413, "Arquivo acima do limite de 200 MB.")
        return visao(store.enviar(dados, file.filename or "faixa"))

    @app.get("/jobs/{job_id}")
    def obter_job(job_id: str):
        job = store.obter(job_id)
        if not job:
            raise HTTPException(404, "Job não encontrado.")
        return visao(job)

    @app.websocket("/jobs/{job_id}/eventos")
    async def eventos(websocket: WebSocket, job_id: str):
        """Manda o estado atual e cada mudança até `concluido` ou `falha`."""
        origem = websocket.headers.get("origin")
        if (origem and not origem_permitida(origem, extras)) or not store.obter(job_id):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        fila: asyncio.Queue = asyncio.Queue()
        sala.assinar(job_id, asyncio.get_running_loop(), fila)
        try:
            enviado = None
            while True:
                atual = store.obter(job_id)
                if not atual:
                    await websocket.send_json({"tipo": "falha", "id": job_id, "state": "error", "erro": "Job não encontrado."})
                    return
                pacote = mensagem(atual)
                if pacote != enviado:
                    await websocket.send_json(pacote)
                    enviado = pacote
                if atual["state"] in ("done", "error"):
                    return
                await fila.get()
                while True:
                    try:
                        fila.get_nowait()
                    except asyncio.QueueEmpty:
                        break
        except WebSocketDisconnect:
            return
        finally:
            sala.sair(job_id, fila)
            if websocket.application_state == WebSocketState.CONNECTED:
                try:
                    await websocket.close()
                except Exception:
                    pass

    @app.get("/jobs/{job_id}/stems/{arquivo}")
    def obter_stem(job_id: str, arquivo: str):
        if arquivo not in _STEMS:
            raise HTTPException(404, "Stem não encontrado.")
        caminho = config["jobs"] / job_id / arquivo
        if not caminho.is_file():
            raise HTTPException(404, "Stem ainda não foi gravado.")
        return FileResponse(caminho, media_type="audio/wav", filename=arquivo)

    @app.delete("/jobs/{job_id}")
    def apagar_job(job_id: str):
        if not store.apagar(job_id):
            raise HTTPException(404, "Job não encontrado.")
        return {"id": job_id, "state": "deleted"}

    return app
