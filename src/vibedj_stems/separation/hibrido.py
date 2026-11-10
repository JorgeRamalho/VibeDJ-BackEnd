"""Espectrograma híbrido do DrumSep, porte de js/stem-separa.js.

Os parâmetros são os do HDemucs: NFFT 4096, hop 1024, Hann dividida pela raiz
da soma dos quadrados, e reflexão que não repete a amostra da borda.
"""

import numpy as np

NFFT = 4096
HOP = 1024
BINS = 2048
PAD = (HOP // 2) * 3


def quadros_hibridos(tamanho: int) -> int:
    """Quadros depois do recorte. 1_764_000 amostras viram 1723."""
    return math_ceil(tamanho / HOP)


def math_ceil(valor: float) -> int:
    return int(np.ceil(valor))


def magnitude_hibrida(esquerdo: np.ndarray, direito: np.ndarray) -> np.ndarray:
    """Tensor mag [4, 2048, quadros]: real e imag de cada canal, sem o bin de Nyquist."""
    if len(esquerdo) != len(direito):
        raise ValueError("Canais com durações diferentes.")
    quadros = quadros_hibridos(len(esquerdo))
    mag = np.empty((4, BINS, quadros), dtype=np.float32)
    for canal, sinal in ((0, esquerdo), (2, direito)):
        espec = spec_recortado(np.asarray(sinal, dtype=np.float32), quadros)
        mag[canal] = espec.real
        mag[canal + 1] = espec.imag
    return mag


def sintetizar(freq: np.ndarray, tempo: np.ndarray, amostras: int) -> np.ndarray:
    """Soma o ramo de frequência, já de volta ao tempo, com o ramo temporal.

    `freq` tem forma (fontes, 4, bins, quadros) e `tempo` (fontes, 2, amostras).
    Devolve (fontes, 2, amostras).
    """
    fontes, _, _, quadros = freq.shape
    saida = np.empty((fontes, 2, amostras), dtype=np.float32)
    for fonte in range(fontes):
        for canal in range(2):
            onda = ispec_recortado(freq[fonte, canal * 2], freq[fonte, canal * 2 + 1], amostras, quadros)
            saida[fonte, canal] = onda + tempo[fonte, canal, :amostras]
    return saida


def ida_e_volta(canal: np.ndarray) -> np.ndarray:
    """Ida e volta de um canal, para o teste conferir o recorte dos quadros."""
    sinal = np.asarray(canal, dtype=np.float32)
    quadros = quadros_hibridos(len(sinal))
    espec = spec_recortado(sinal, quadros)
    return ispec_recortado(espec.real, espec.imag, len(sinal), quadros)


def spec_recortado(canal: np.ndarray, quadros: int) -> np.ndarray:
    """STFT com a borda refletida e os dois quadros de cada ponta descartados."""
    direito = PAD + quadros * HOP - len(canal)
    preenchido = refletir(canal, PAD, direito)
    espec = transformar(preenchido)
    if espec.shape[1] != quadros + 4:
        raise ValueError(f"Quadros {espec.shape[1]} não batem com {quadros + 4}.")
    return espec[:BINS, 2 : 2 + quadros]


def ispec_recortado(real: np.ndarray, imag: np.ndarray, amostras: int, quadros: int) -> np.ndarray:
    """Inverso do recorte: devolve os dois quadros de borda e lê a partir do pad."""
    quadros_cheios = quadros + 4
    bins = BINS + 1
    cheio = np.zeros((bins, quadros_cheios), dtype=np.complex64)
    cheio[:BINS, 2 : 2 + quadros] = real.astype(np.float32) + 1j * imag.astype(np.float32)
    alvo = HOP * math_ceil(amostras / HOP) + 2 * PAD
    onda = inverter(cheio, alvo)
    return onda[PAD : PAD + amostras].astype(np.float32)


def transformar(sinal: np.ndarray) -> np.ndarray:
    """STFT complexa em (bins, quadros). O bin de Nyquist entra aqui e sai no recorte."""
    pad = NFFT // 2
    preenchido = refletir(sinal, pad, pad)
    quadros = 1 + (len(preenchido) - NFFT) // HOP
    janela = hann_normalizada(NFFT)
    inicio = np.arange(quadros) * HOP
    grade = inicio[:, None] + np.arange(NFFT)[None, :]
    quadros_janelados = preenchido[grade] * janela
    return np.fft.rfft(quadros_janelados, axis=1).astype(np.complex64).T


def inverter(espec: np.ndarray, tamanho: int) -> np.ndarray:
    """ISTFT com sobreposição e divisão pela soma dos quadrados da janela."""
    janela = hann_normalizada(NFFT)
    quadros = espec.shape[1]
    onda = np.fft.irfft(espec.T.astype(np.complex64), n=NFFT, axis=1).astype(np.float32)
    saida = np.zeros(tamanho + NFFT, dtype=np.float32)
    peso = np.zeros(saida.shape, dtype=np.float32)
    peso_janela = janela * janela
    for quadro in range(quadros):
        inicio = quadro * HOP - (NFFT // 2)
        fim = inicio + NFFT
        esquerdo = max(0, inicio)
        direito = min(len(saida), fim)
        if esquerdo >= direito:
            continue
        recorte = slice(esquerdo - inicio, direito - inicio)
        saida[esquerdo:direito] += onda[quadro, recorte] * janela[recorte]
        peso[esquerdo:direito] += peso_janela[recorte]
    util = np.divide(saida[:tamanho], peso[:tamanho], out=np.zeros(tamanho, dtype=np.float32), where=peso[:tamanho] > 1e-8)
    return util


def hann_normalizada(tamanho: int) -> np.ndarray:
    """Hann periódica dividida pela raiz da soma dos quadrados, como no front."""
    indice = np.arange(tamanho, dtype=np.float64)
    janela = 0.5 - 0.5 * np.cos((2 * np.pi * indice) / tamanho)
    return (janela / np.sqrt(np.sum(janela * janela))).astype(np.float32)


def refletir(sinal: np.ndarray, esquerda: int, direita: int) -> np.ndarray:
    """Reflexão sem repetir a borda, no mesmo sentido do pad reflect do PyTorch."""
    tamanho = len(sinal)
    posicao = np.arange(esquerda + tamanho + direita, dtype=np.int64) - esquerda
    for _ in range(8):
        negativo = posicao < 0
        alto = posicao >= tamanho
        if not negativo.any() and not alto.any():
            break
        posicao[negativo] = -posicao[negativo]
        posicao[alto] = 2 * tamanho - 2 - posicao[alto]
    return sinal[posicao]
