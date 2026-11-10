"""Download, conferência e sessões quentes dos dois ONNX."""

import hashlib
import threading
import urllib.request
from pathlib import Path

import onnxruntime as ort

from vibedj_stems.config import MODELOS


class Modelos:
    """As duas sessões ficam abertas enquanto o processo vive."""

    def __init__(self, pasta: Path, provedores: list[str]):
        self.pasta = Path(pasta)
        self.provedores = provedores
        self.sessoes: dict[str, ort.InferenceSession] = {}
        self.pronto = threading.Event()
        self.erro: str | None = None
        self.mensagem = "Carregando modelos…"

    def carregar(self) -> None:
        """Baixa o que faltar, confere o sha256 e abre as sessões. Roda fora da thread do ícone."""
        try:
            self.pasta.mkdir(parents=True, exist_ok=True)
            opcoes = ort.SessionOptions()
            opcoes.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            for spec in MODELOS:
                self.mensagem = f"Preparando {spec['id']}…"
                caminho = self.garantir_arquivo(spec)
                self.mensagem = f"Abrindo {spec['id']}…"
                self.sessoes[spec["id"]] = ort.InferenceSession(str(caminho), opcoes, providers=self.provedores)
            self.mensagem = "Pronto"
        except Exception as err:
            self.erro = str(err)
            self.mensagem = "Falha ao carregar os modelos"
        finally:
            self.pronto.set()

    def garantir_arquivo(self, spec: dict) -> Path:
        """Usa o arquivo local quando o hash confere. Senão baixa de novo."""
        destino = self.pasta / spec["arquivo"]
        if destino.is_file() and sha256_arquivo(destino) == spec["sha256"]:
            return destino
        parcial = destino.with_suffix(destino.suffix + ".parcial")
        urllib.request.urlretrieve(spec["url"], parcial)
        if sha256_arquivo(parcial) != spec["sha256"]:
            parcial.unlink(missing_ok=True)
            raise RuntimeError(f"O download de {spec['id']} não confere com o hash esperado.")
        parcial.replace(destino)
        return destino

    def exigir(self, modelo: str):
        """Espera o aquecimento e devolve a sessão. Falha com a mensagem do carregamento."""
        self.pronto.wait()
        if self.erro:
            raise RuntimeError(self.erro)
        return self.sessoes[modelo]


def sha256_arquivo(caminho: Path) -> str:
    """Hash do arquivo em blocos, para os modelos de centenas de MB."""
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(1 << 20):
            digest.update(bloco)
    return digest.hexdigest()
