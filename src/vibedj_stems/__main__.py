"""Sobe o HTTP, aquece os modelos e fica na bandeja até o Sair."""

import logging
import os
import socket
import threading
from pathlib import Path

import uvicorn

from vibedj_stems.config import carregar
from vibedj_stems.dialogo import escolher_pasta
from vibedj_stems.jobs import JobStore
from vibedj_stems.models import Modelos
from vibedj_stems.separation.pipeline import separar_faixa
from vibedj_stems.server import criar_app
from vibedj_stems.tray import criar_icone


def porta_livre(host: str, porta: int) -> bool:
    """A segunda abertura encontra a porta ocupada e sai, em vez de subir outra fila."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soquete:
        try:
            soquete.bind((host, porta))
        except OSError:
            return False
    return True


def main() -> None:
    config = carregar()
    for chave in ("modelos", "jobs", "logs"):
        Path(config[chave]).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=config["logs"] / "vibedj-stems.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    if not porta_livre(config["host"], config["porta"]):
        logging.error("Já existe um VibeDJ Stems em %s:%s.", config["host"], config["porta"])
        return

    modelos = Modelos(config["modelos"], config["provedores"])
    store = JobStore(
        config["jobs"],
        lambda mix, ao_avancar: separar_faixa(mix, modelos, ao_avancar),
        config["dias_job"],
        escolher_pasta=escolher_pasta,
    )
    app = criar_app(store, config, modelos)
    servidor = uvicorn.Server(
        uvicorn.Config(app, host=config["host"], port=config["porta"], log_config=None, access_log=False)
    )
    servidor.install_signal_handlers = lambda: None
    threading.Thread(target=servidor.run, name="vibedj-http", daemon=True).start()
    threading.Thread(target=modelos.carregar, name="vibedj-modelos", daemon=True).start()
    logging.info("Escutando em http://%s:%s", config["host"], config["porta"])

    def texto() -> str:
        return store.texto_andamento() or f"VibeDJ Stems · {modelos.mensagem}"

    def ao_abrir() -> None:
        os.startfile(config["jobs"])

    def ao_sair(icon) -> None:
        logging.info("Encerrando.")
        servidor.should_exit = True
        icon.stop()

    icone = criar_icone(texto, ao_abrir, ao_sair)
    parar = threading.Event()

    def atualizar_tooltip() -> None:
        while not parar.is_set():
            icone.title = texto()
            parar.wait(1)

    threading.Thread(target=atualizar_tooltip, name="vibedj-tooltip", daemon=True).start()
    icone.run()
    parar.set()


if __name__ == "__main__":
    main()
