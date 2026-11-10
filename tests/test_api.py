"""Contrato HTTP com um separador que não carrega modelo."""

import io
import os
import threading
import time

import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from vibedj_stems.config import TAXA
from vibedj_stems.jobs import JobStore, nome_da_faixa, pasta_da_faixa
from vibedj_stems.server import criar_app, origem_permitida

FONTES = ("drums", "bass", "other", "vocals", "kick", "snare", "cymbals", "toms")


class ModelosProntos:
    def __init__(self):
        self.pronto = threading.Event()
        self.pronto.set()
        self.erro = None
        self.mensagem = "Pronto"


def separador_falso(mix, ao_avancar):
    ao_avancar("mix", 1, 1, 0.5)
    ao_avancar("bateria", 1, 1, 1.0)
    tom = np.zeros_like(mix)
    tom[:, 0] = 0.25
    return {fonte: tom.copy() for fonte in FONTES}


def wav_de_teste() -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros((TAXA // 2, 2), dtype=np.float32), TAXA, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def esperar(store, job_id):
    for _ in range(100):
        job = store.obter(job_id)
        if job["state"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError(store.obter(job_id))


def test_localhost_em_qualquer_porta_entra_e_origem_estranha_nao():
    assert origem_permitida("http://localhost:8888", [])
    assert origem_permitida("http://127.0.0.1:5500", [])
    assert origem_permitida("https://vibedj.netlify.app", ["https://vibedj.netlify.app"])
    assert not origem_permitida("https://evil.test", [])
    assert not origem_permitida(None, [])


def test_upload_progresso_stem_e_rede_privada(tmp_path):
    store = JobStore(tmp_path / "jobs", separador_falso, dias=7)
    config = {"jobs": tmp_path / "jobs", "upload_max": 1024 * 1024, "origens": ["https://vibedj.netlify.app"], "provedores": ["CPUExecutionProvider"]}
    cliente = TestClient(criar_app(store, config, ModelosProntos()))

    preflight = cliente.options(
        "/jobs",
        headers={
            "Origin": "http://127.0.0.1:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5500"
    assert preflight.headers["access-control-allow-private-network"] == "true"

    bloqueado = cliente.get("/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in bloqueado.headers

    saude = cliente.get("/health")
    assert saude.json()["status"] == "ready"

    resposta = cliente.post("/jobs", files={"file": ("faixa.wav", wav_de_teste(), "audio/wav")})
    assert resposta.status_code == 202
    job_id = resposta.json()["id"]
    pronto = esperar(store, job_id)
    assert pronto["state"] == "done"
    assert pronto["destino"] is None
    cadeiras = {item["fonte"]: item["cadeira"] for item in pronto["stems"]}
    assert cadeiras["vocals"] == "vocal"
    assert cadeiras["cymbals"] == "hat"
    assert cadeiras["drums"] is None

    stem = cliente.get(f"/jobs/{job_id}/stems/vocals.wav")
    assert stem.status_code == 200
    assert stem.headers["content-type"].startswith("audio/wav")
    assert stem.content[:4] == b"RIFF"

    de_novo = cliente.post("/jobs", files={"file": ("faixa.wav", wav_de_teste(), "audio/wav")})
    assert de_novo.json()["id"] == job_id

    assert cliente.delete(f"/jobs/{job_id}").json()["state"] == "deleted"
    assert cliente.get(f"/jobs/{job_id}").status_code == 404


def test_websocket_avisa_andamento_e_conclusao(tmp_path):
    liberar = threading.Event()

    def separador_pausado(mix, ao_avancar):
        ao_avancar("mix", 1, 2, 0.4)
        if not liberar.wait(5):
            raise TimeoutError("o teste não liberou o separador")
        ao_avancar("bateria", 2, 2, 0.9)
        tom = np.zeros_like(mix)
        tom[:, 0] = 0.25
        return {fonte: tom.copy() for fonte in FONTES}

    store = JobStore(tmp_path / "jobs", separador_pausado, dias=7)
    config = {"jobs": tmp_path / "jobs", "upload_max": 1024 * 1024, "origens": ["https://vibedj.netlify.app"], "provedores": ["CPUExecutionProvider"]}
    cliente = TestClient(criar_app(store, config, ModelosProntos()))
    resposta = cliente.post("/jobs", files={"file": ("faixa.wav", wav_de_teste(), "audio/wav")})
    job_id = resposta.json()["id"]

    with cliente.websocket_connect(f"/jobs/{job_id}/eventos") as socket:
        vistos = []
        while True:
            pacote = socket.receive_json()
            vistos.append(pacote)
            if pacote["tipo"] == "andamento" and pacote["progress"] >= 0.4:
                liberar.set()
            if pacote["tipo"] in ("concluido", "falha"):
                break

    assert any(item["tipo"] == "andamento" and item["progress"] >= 0.4 for item in vistos)
    assert vistos[-1]["tipo"] == "concluido"
    assert vistos[-1]["state"] == "done"
    assert vistos[-1]["progress"] == 1.0
    assert vistos[-1]["rotulo"] == "Pronto"
    assert any(item["fonte"] == "vocals" for item in vistos[-1]["stems"])

    with cliente.websocket_connect(f"/jobs/{job_id}/eventos") as socket:
        de_novo = socket.receive_json()
    assert de_novo["tipo"] == "concluido"
    assert de_novo["id"] == job_id


def test_websocket_recusa_origem_estranha_e_job_ausente(tmp_path):
    store = JobStore(tmp_path / "jobs", separador_falso, dias=7)
    config = {"jobs": tmp_path / "jobs", "upload_max": 1024 * 1024, "origens": [], "provedores": ["CPUExecutionProvider"]}
    cliente = TestClient(criar_app(store, config, ModelosProntos()))
    resposta = cliente.post("/jobs", files={"file": ("faixa.wav", wav_de_teste(), "audio/wav")})
    job_id = esperar(store, resposta.json()["id"])["id"]

    with pytest.raises(WebSocketDisconnect) as estranha:
        with cliente.websocket_connect(f"/jobs/{job_id}/eventos", headers={"origin": "https://evil.test"}) as socket:
            socket.receive_json()
    assert estranha.value.code == 1008

    with pytest.raises(WebSocketDisconnect) as ausente:
        with cliente.websocket_connect("/jobs/nao-existe/eventos") as socket:
            socket.receive_json()
    assert ausente.value.code == 1008


def test_nome_da_faixa_vira_pasta_valida():
    assert nome_da_faixa("Faixa Demo.mp3") == "Faixa Demo"
    assert nome_da_faixa("a:b?.wav") == "a b"
    assert nome_da_faixa("CON.wav") == "CON_"
    assert nome_da_faixa("...") == "faixa"


def test_ao_terminar_cria_a_pasta_da_faixa(tmp_path):
    escolhida = tmp_path / "musica"
    escolhida.mkdir()
    bloqueio = escolhida / "Minha Faixa"
    bloqueio.write_text("ocupado", encoding="utf-8")
    store = JobStore(tmp_path / "jobs", separador_falso, dias=7, escolher_pasta=lambda: escolhida)
    config = {"jobs": tmp_path / "jobs", "upload_max": 1024 * 1024, "origens": [], "provedores": ["CPUExecutionProvider"]}
    cliente = TestClient(criar_app(store, config, ModelosProntos()))

    resposta = cliente.post("/jobs", files={"file": ("Minha Faixa.wav", wav_de_teste(), "audio/wav")})
    pronto = esperar(store, resposta.json()["id"])
    destino = pasta_da_faixa(escolhida, "Minha Faixa")

    assert pronto["state"] == "done"
    assert pronto["destino"] == str(destino)
    assert destino.name == "Minha Faixa (2)"
    assert (destino / "vocals.wav").read_bytes()[:4] == b"RIFF"
    assert (destino / "kick.wav").is_file()


def test_cancelar_a_caixa_deixa_o_job_pronto(tmp_path):
    store = JobStore(tmp_path / "jobs", separador_falso, dias=7, escolher_pasta=lambda: None)
    config = {"jobs": tmp_path / "jobs", "upload_max": 1024 * 1024, "origens": [], "provedores": ["CPUExecutionProvider"]}
    cliente = TestClient(criar_app(store, config, ModelosProntos()))
    resposta = cliente.post("/jobs", files={"file": ("faixa.wav", wav_de_teste(), "audio/wav")})
    pronto = esperar(store, resposta.json()["id"])
    assert pronto["state"] == "done"
    assert pronto["destino"] is None
    assert cliente.get(f"/jobs/{pronto['id']}/stems/vocals.wav").status_code == 200


def test_job_velho_sai_na_abertura(tmp_path):
    velho = tmp_path / "jobs" / "velho"
    velho.mkdir(parents=True)
    os.utime(velho, (1, 1))
    JobStore(tmp_path / "jobs", separador_falso, dias=7)
    assert not velho.exists()
