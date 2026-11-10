"""Separa uma faixa com o pacote e imprime tempo e o nível do vocal contra a mix."""

import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from vibedj_stems.audio_io import gravar_wav, ler_mix
from vibedj_stems.models import Modelos
from vibedj_stems.separation.pipeline import separar_faixa


def main() -> None:
    entrada = Path(sys.argv[1])
    saida = Path(sys.argv[2])
    modelos = Modelos(Path(sys.argv[3]), ["CPUExecutionProvider"])
    inicio = time.time()
    modelos.carregar()
    if modelos.erro:
        raise SystemExit(modelos.erro)
    aberto = time.time() - inicio
    mix = ler_mix(entrada)
    marcas = []

    def ao_avancar(etapa, bloco, total, progresso):
        if bloco == 1 or bloco == total:
            marcas.append((time.time() - inicio, etapa, bloco, total, progresso))
            print(f"{etapa} {bloco}/{total} {progresso:.0%} {time.time() - inicio:.0f}s", flush=True)

    t0 = time.time()
    fontes = separar_faixa(mix, modelos, ao_avancar)
    separacao = time.time() - t0
    saida.mkdir(parents=True, exist_ok=True)
    for fonte, audio in fontes.items():
        gravar_wav(saida / f"{fonte}.wav", audio)
    voz = fontes["vocals"].mean(axis=1)
    bruto = mix.mean(axis=1)
    print(f"sessões {aberto:.0f}s  separação {separacao:.0f}s  vocal {nivel(voz):.1f} dBFS  mix {nivel(bruto):.1f} dBFS")
    if len(sys.argv) > 4:
        referencia, taxa = sf.read(sys.argv[4], dtype="float32")
        n = min(len(referencia), len(fontes["vocals"]))
        erro = np.sum((fontes["vocals"][:n] - referencia[:n]) ** 2)
        sinal = np.sum(referencia[:n] ** 2)
        print(f"vocal contra referência: {10 * np.log10(sinal / max(erro, 1e-20)):.1f} dB")


def nivel(sinal) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(sinal**2)) + 1e-12))


if __name__ == "__main__":
    main()
