"""Fila de um worker, cache por sha256 e limpeza dos jobs antigos."""

import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

from vibedj_stems.audio_io import gravar_wav, ler_mix
from vibedj_stems.config import FONTE_CADEIRA
from vibedj_stems.separation.pipeline import separar_faixa

ROTULOS = {
    "mix": "Separando bateria, baixo e voz",
    "bateria": "Separando kick, clap e hi-hat",
    "gravando": "Gravando os stems",
    "pasta": "Escolha a pasta",
}

# Nomes que o Windows recusa mesmo com extensão. A pasta da faixa não pode usar esses.
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_INVALIDOS = '<>:"/\\|?*'


def nome_da_faixa(nome: str) -> str:
    """Título da pasta da faixa: o arquivo sem extensão e sem o que o Windows recusa no caminho.

    nome: arquivo enviado no upload, por exemplo "Faixa Demo.wav".
    """
    # Sem Path: no Windows "a:faixa.wav" seria lido como unidade, e o título perderia o "a".
    bruto = (nome or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = bruto.rsplit(".", 1)[0] if "." in bruto else bruto
    limpo = "".join(" " if (c in _INVALIDOS or ord(c) < 32) else c for c in base)
    limpo = " ".join(limpo.split()).rstrip(" .")[:120].rstrip(" .")
    if not limpo:
        return "faixa"
    if limpo.upper().split(".")[0] in _RESERVADOS:
        return f"{limpo}_"
    return limpo


def pasta_da_faixa(raiz: Path, titulo: str) -> Path:
    """Subpasta com o título da faixa dentro da pasta escolhida. Diretório já existente é reaproveitado.

    raiz: pasta confirmada na caixa.
    titulo: resultado de nome_da_faixa.
    """
    candidata = raiz / titulo
    if not candidata.exists() or candidata.is_dir():
        return candidata
    indice = 2
    while True:
        alternativa = raiz / f"{titulo} ({indice})"
        if not alternativa.exists() or alternativa.is_dir():
            return alternativa
        indice += 1


class JobStore:
    """Um job por vez. Dois ao mesmo tempo disputariam a CPU sem ficar mais rápidos."""

    def __init__(self, pasta: Path, separador, dias: int = 7, escolher_pasta=None, ao_mudar=None):
        """Fila um job por vez. `escolher_pasta` abre a caixa no fim; None deixa os WAV só no cache.

        pasta: diretório dos jobs em disco.
        separador: callable (mix, ao_avancar) que devolve as fontes.
        dias: prazo para apagar jobs velhos na abertura.
        escolher_pasta: callable sem argumentos. Devolve a pasta escolhida, ou None se cancelar.
        ao_mudar: callable (job_id) avisado a cada mudança visível. O WebSocket usa isso.
        """
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.separador = separador
        self.dias = dias
        self.escolher_pasta = escolher_pasta
        self.ao_mudar = ao_mudar
        self.jobs: dict[str, dict] = {}
        self.por_hash: dict[str, str] = {}
        self._fila: list[str] = []
        self._aviso = threading.Event()
        self._trava = threading.Lock()
        self.limpar()
        self._carregar_cache()
        self._worker = threading.Thread(target=self._rodar, name="vibedj-stems", daemon=True)
        self._worker.start()

    def enviar(self, dados: bytes, nome: str) -> dict:
        """Guarda o arquivo e devolve o job. O mesmo conteúdo reaproveita o job pronto ou em fila."""
        digest = hashlib.sha256(dados).hexdigest()
        with self._trava:
            existente = self.por_hash.get(digest)
            if existente and existente in self.jobs and (self.pasta / existente).is_dir():
                return self.jobs[existente]
            job_id = uuid.uuid4().hex[:12]
            destino = self.pasta / job_id
            destino.mkdir(parents=True)
            origem = destino / "entrada"
            origem.write_bytes(dados)
            job = {
                "id": job_id,
                "nome": Path(nome).name or "faixa",
                "sha256": digest,
                "state": "queued",
                "stage": "fila",
                "rotulo": "Na fila",
                "bloco": 0,
                "blocos": 0,
                "progress": 0.0,
                "erro": None,
                "stems": [],
                "destino": None,
                "criado": time.time(),
            }
            self.jobs[job_id] = job
            self.por_hash[digest] = job_id
            (destino / "job.json").write_text(json.dumps(self._publico(job), ensure_ascii=False), encoding="utf-8")
            self._fila.append(job_id)
            self._aviso.set()
            return job

    def obter(self, job_id: str) -> dict | None:
        with self._trava:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def apagar(self, job_id: str) -> bool:
        """Remove o job do disco e do cache. Não interrompe o que já está na CPU."""
        with self._trava:
            job = self.jobs.pop(job_id, None)
            if not job:
                return False
            if self.por_hash.get(job["sha256"]) == job_id:
                self.por_hash.pop(job["sha256"], None)
        shutil.rmtree(self.pasta / job_id, ignore_errors=True)
        return True

    def texto_andamento(self) -> str | None:
        """Frase curta para o tooltip enquanto um job ocupa a CPU."""
        with self._trava:
            for job in self.jobs.values():
                if job["state"] == "running":
                    return f"{job['rotulo']} · {round(job['progress'] * 100)}%"
        return None

    def limpar(self) -> None:
        """Apaga jobs mais velhos que o prazo. Roda na abertura."""
        limite = time.time() - self.dias * 86400
        if not self.pasta.is_dir():
            return
        for pasta in self.pasta.iterdir():
            if pasta.is_dir() and pasta.stat().st_mtime < limite:
                shutil.rmtree(pasta, ignore_errors=True)

    def _carregar_cache(self) -> None:
        for pasta in self.pasta.iterdir():
            manifesto = pasta / "manifest.json"
            if not manifesto.is_file():
                continue
            dados = json.loads(manifesto.read_text(encoding="utf-8"))
            job = {
                "id": pasta.name,
                "nome": dados.get("nome", "faixa"),
                "sha256": dados["sha256"],
                "state": "done",
                "stage": "done",
                "rotulo": "Pronto",
                "bloco": 1,
                "blocos": 1,
                "progress": 1.0,
                "erro": None,
                "stems": dados["stems"],
                "destino": dados.get("destino"),
                "criado": pasta.stat().st_mtime,
            }
            self.jobs[pasta.name] = job
            self.por_hash[dados["sha256"]] = pasta.name

    def _rodar(self) -> None:
        while True:
            self._aviso.wait()
            with self._trava:
                if not self._fila:
                    self._aviso.clear()
                    continue
                job_id = self._fila.pop(0)
                job = self.jobs.get(job_id)
            if not job or job["state"] == "done":
                continue
            self._processar(job)

    def _processar(self, job: dict) -> None:
        destino = self.pasta / job["id"]

        def ao_avancar(etapa, bloco, total, progresso):
            with self._trava:
                job["state"] = "running"
                job["stage"] = etapa
                job["rotulo"] = ROTULOS.get(etapa, etapa)
                job["bloco"] = bloco
                job["blocos"] = total
                job["progress"] = round(progresso, 4)
            self._avisar(job["id"])

        try:
            mix = ler_mix(destino / "entrada")
            fontes = self.separador(mix, ao_avancar)
            ao_avancar("gravando", 1, 1, 0.98)
            stems = []
            for fonte, audio in fontes.items():
                arquivo = f"{fonte}.wav"
                gravar_wav(destino / arquivo, audio)
                stems.append({
                    "fonte": fonte,
                    "cadeira": FONTE_CADEIRA.get(fonte),
                    "arquivo": arquivo,
                    "url": f"/jobs/{job['id']}/stems/{arquivo}",
                })
            destino_faixa = self._gravar_na_pasta_escolhida(job, destino, stems)
            manifesto = {"sha256": job["sha256"], "nome": job["nome"], "stems": stems, "destino": destino_faixa}
            (destino / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
            with self._trava:
                job["stems"] = stems
                job["destino"] = destino_faixa
                job["state"] = "done"
                job["stage"] = "done"
                job["rotulo"] = "Pronto"
                job["progress"] = 1.0
            self._avisar(job["id"])
        except Exception as err:
            with self._trava:
                job["state"] = "error"
                job["stage"] = "error"
                job["rotulo"] = "Falha"
                job["erro"] = str(err)
                if self.por_hash.get(job["sha256"]) == job["id"]:
                    self.por_hash.pop(job["sha256"], None)
            self._avisar(job["id"])

    def _gravar_na_pasta_escolhida(self, job: dict, origem: Path, stems: list[dict]) -> str | None:
        """Abre a caixa e copia os WAV para uma subpasta com o título da faixa.

        origem: pasta do job, onde os WAV já foram gravados.
        Devolve o caminho da subpasta, ou None se não há seletor ou se a pessoa cancelou.
        """
        if self.escolher_pasta is None:
            return None
        with self._trava:
            job["stage"] = "pasta"
            job["rotulo"] = ROTULOS["pasta"]
        self._avisar(job["id"])
        logging.info("Aguardando a pasta para %s.", job["nome"])
        raiz = self.escolher_pasta()
        if not raiz:
            logging.info("Caixa de pasta cancelada para %s.", job["nome"])
            return None
        pasta = pasta_da_faixa(Path(raiz), nome_da_faixa(job["nome"]))
        pasta.mkdir(parents=True, exist_ok=True)
        for item in stems:
            shutil.copy2(origem / item["arquivo"], pasta / item["arquivo"])
        logging.info("Stems de %s gravados em %s.", job["nome"], pasta)
        return str(pasta)

    def _avisar(self, job_id: str) -> None:
        """Acorda quem observa o job. A thread do worker não espera o navegador.

        job_id: id do job que acabou de mudar de etapa, progresso ou estado.
        """
        aviso = self.ao_mudar
        if not aviso:
            return
        try:
            aviso(job_id)
        except Exception:
            logging.exception("Falha ao avisar o andamento de %s.", job_id)

    @staticmethod
    def _publico(job: dict) -> dict:
        return {chave: job[chave] for chave in ("id", "nome", "state", "stage", "rotulo", "progress", "erro", "stems", "destino")}
