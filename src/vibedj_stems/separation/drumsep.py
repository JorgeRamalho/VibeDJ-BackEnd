"""DrumSep v2 sobre o stem de bateria. A janela é de 40 s e o passo é de 20 s."""

from vibedj_stems.separation.hibrido import magnitude_hibrida, sintetizar
from vibedj_stems.separation.overlap import separar_em_blocos

FONTES = ("kick", "snare", "cymbals", "toms")
SEGMENTO = 1764000
PASSO = 882000
SOBREPOSICAO = SEGMENTO - PASSO


def separar_bateria(bateria, sessao, ao_avancar):
    """Recebe o stem drums em (amostras, 2) e devolve kick, snare, cymbals e toms."""

    def inferir(bloco, indice, total):
        ao_avancar(indice + 1, total)
        mag = magnitude_hibrida(bloco[0], bloco[1])
        freq, tempo = sessao.run(
            ["freq_out", "time_out"],
            {"mix": bloco[None, :, :], "mag": mag[None, :, :, :]},
        )
        return sintetizar(freq[0], tempo[0], SEGMENTO)

    partes = separar_em_blocos(bateria, SEGMENTO, SOBREPOSICAO, inferir)
    return {fonte: partes[indice].T.copy() for indice, fonte in enumerate(FONTES)}
