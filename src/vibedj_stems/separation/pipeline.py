"""As duas passagens: HT-Demucs na mix e DrumSep só no stem de bateria."""

from vibedj_stems.separation.demucs import separar_mix
from vibedj_stems.separation.drumsep import separar_bateria


def separar_faixa(mix, modelos, ao_avancar):
    """Devolve as oito fontes. `ao_avancar(etapa, bloco, total, progresso)` recebe 0..1 no total."""

    def avanco_mix(bloco, total):
        ao_avancar("mix", bloco, total, bloco / total * 0.55)

    mix_separada = separar_mix(mix, modelos.exigir("htdemucs"), avanco_mix)

    def avanco_bateria(bloco, total):
        ao_avancar("bateria", bloco, total, 0.55 + bloco / total * 0.45)

    bateria = separar_bateria(mix_separada["drums"], modelos.exigir("drumsep"), avanco_bateria)
    return {**mix_separada, **bateria}
