"""HT-Demucs em blocos de 7,8 s, com sobreposição de um quarto."""

from vibedj_stems.separation.overlap import separar_em_blocos

FONTES = ("drums", "bass", "other", "vocals")
SEGMENTO = 343980
SOBREPOSICAO = SEGMENTO // 4


def separar_mix(mix, sessao, ao_avancar):
    """Separa a mix inteira. `ao_avancar(bloco, total)` informa o progresso.

    Devolve um dict fonte → áudio (amostras, 2), na ordem drums, bass, other, vocals.
    """

    def inferir(bloco, indice, total):
        ao_avancar(indice + 1, total)
        saida = sessao.run(["stems"], {"mix": bloco[None, :, :]})[0]
        return saida[0]

    partes = separar_em_blocos(mix, SEGMENTO, SOBREPOSICAO, inferir)
    return {fonte: np_transpor(partes[indice]) for indice, fonte in enumerate(FONTES)}


def np_transpor(canal_primeiro):
    """(2, amostras) → (amostras, 2), que é o layout do soundfile."""
    return canal_primeiro.T.copy()
