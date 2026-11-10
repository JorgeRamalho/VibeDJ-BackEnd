"""O espectrograma híbrido reconstrói um seno."""

import numpy as np

from vibedj_stems.separation.hibrido import ida_e_volta, quadros_hibridos

TAXA = 44100


def seno(amostras: int) -> np.ndarray:
    tempo = np.arange(amostras, dtype=np.float64) / TAXA
    return (0.5 * np.sin(2 * np.pi * 440 * tempo)).astype(np.float32)


def test_um_bloco_de_bateria_tem_1723_quadros():
    assert quadros_hibridos(1_764_000) == 1723


def test_ida_e_volta_preserva_um_seno():
    sinal = seno(TAXA * 2)
    volta = ida_e_volta(sinal)
    assert volta.shape == sinal.shape
    miolo = slice(TAXA // 2, -TAXA // 2)
    erro = np.sum((volta[miolo] - sinal[miolo]) ** 2)
    energia = np.sum(sinal[miolo] ** 2)
    assert erro / energia < 1e-4
