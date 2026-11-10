"""Porta, pastas e origens permitidas do backend local."""

import json
import os
from pathlib import Path

from vibedj_stems import __version__

VERSAO = __version__
HOST = "127.0.0.1"
PORTA = 8777
TAXA = 44100
UPLOAD_MAX = 200 * 1024 * 1024
DIAS_JOB = 7
PROVEDORES = ["CPUExecutionProvider"]

# vocals/bass/other/drums vêm do HT-Demucs; kick/snare/cymbals/toms, do DrumSep.
# drums não entra em cadeira: a bateria fina já ocupa kick, clap, hat e perc.
FONTE_CADEIRA = {
    "vocals": "vocal",
    "bass": "bass",
    "other": "stab",
    "kick": "kick",
    "snare": "clap",
    "cymbals": "hat",
    "toms": "perc",
    "drums": None,
}

MODELOS = (
    {
        "id": "htdemucs",
        "arquivo": "htdemucs_fp16weights.onnx",
        "url": "https://huggingface.co/StemSplitio/htdemucs-onnx/resolve/main/htdemucs_fp16weights.onnx",
        "sha256": "d05c269d0178d2a72ad484b10b11dd370193fc923201c3b27a99f848745db70a",
    },
    {
        "id": "drumsep",
        "arquivo": "drumsep_v2.onnx",
        "url": "https://huggingface.co/gridshiftstudio/drumsep-onnx/resolve/main/drumsep_v2.onnx",
        "sha256": "980dd931849f16c06ce6112aa24217d9538ce897fe248fad7ef0113f58c238de",
    },
)


def pasta_dados() -> Path:
    """Pasta do usuário: modelos, jobs e o config editável."""
    base = os.environ.get("LOCALAPPDATA")
    raiz = Path(base) if base else Path.home() / "AppData" / "Local"
    return raiz / "VibeDJStems"


def carregar(pasta: Path | None = None) -> dict:
    """Lê config.json se existir. Origens extras e provedores ONNX são opcionais."""
    pasta = pasta or pasta_dados()
    config = {
        "versao": VERSAO,
        "host": HOST,
        "porta": PORTA,
        "pasta": pasta,
        "modelos": pasta / "models",
        "jobs": pasta / "jobs",
        "logs": pasta / "logs",
        "origens": [],
        "provedores": list(PROVEDORES),
        "upload_max": UPLOAD_MAX,
        "dias_job": DIAS_JOB,
    }
    arquivo = pasta / "config.json"
    if not arquivo.is_file():
        return config
    extra = json.loads(arquivo.read_text(encoding="utf-8"))
    if isinstance(extra.get("origens"), list):
        config["origens"] = [str(item) for item in extra["origens"]]
    if isinstance(extra.get("provedores"), list) and extra["provedores"]:
        config["provedores"] = [str(item) for item in extra["provedores"]]
    return config
