"""Soma de blocos em fluxo, com a janela trapezoidal do HT-Demucs."""

import math

import numpy as np

# O fade segue linspace(0, 1, overlap), como o infer.py do HT-Demucs e stem-separa.js.
def janela_trapezio(segmento: int, sobreposicao: int) -> np.ndarray:
    """Sobe no início, vale 1 no meio e desce no fim. Sem sobreposição, vale 1."""
    janela = np.ones(segmento, dtype=np.float32)
    if sobreposicao <= 0:
        return janela
    rampa = np.linspace(0, 1, sobreposicao, dtype=np.float32)
    janela[:sobreposicao] = rampa
    janela[-sobreposicao:] = rampa[::-1]
    return janela


def separar_em_blocos(mix, segmento, sobreposicao, inferir):
    """Corta a mix em blocos com contexto de silêncio nas pontas e soma em fluxo.

    `mix` tem forma (amostras, 2). `inferir(bloco, indice, total)` recebe o bloco
    em (2, segmento) e devolve (fontes, 2, segmento). O resultado cobre só as
    amostras reais, já sem o silêncio das pontas.
    """
    total = len(mix)
    passo = segmento - sobreposicao
    if passo <= 0:
        raise ValueError("Sobreposição maior ou igual ao bloco.")
    silencio = np.zeros((sobreposicao, 2), dtype=np.float32)
    bruto = np.concatenate([silencio, np.asarray(mix, dtype=np.float32), silencio])
    blocos = max(1, math.ceil((len(bruto) - sobreposicao) / passo))
    falta = blocos * passo + sobreposicao - len(bruto)
    if falta > 0:
        bruto = np.concatenate([bruto, np.zeros((falta, 2), dtype=np.float32)])
    janela = janela_trapezio(segmento, sobreposicao)
    saida = None
    peso = np.zeros(len(bruto), dtype=np.float32)
    for indice in range(blocos):
        inicio = indice * passo
        bloco = np.ascontiguousarray(bruto[inicio : inicio + segmento].T)
        partes = np.asarray(inferir(bloco, indice, blocos), dtype=np.float32)
        if saida is None:
            saida = np.zeros((partes.shape[0], 2, len(bruto)), dtype=np.float32)
        saida[:, :, inicio : inicio + segmento] += partes * janela
        peso[inicio : inicio + segmento] += janela
    saida /= np.maximum(peso, 1e-8)
    return saida[:, :, sobreposicao : sobreposicao + total]
