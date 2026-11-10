"""A soma em fluxo de um modelo identidade devolve a mix."""

import numpy as np

from vibedj_stems.separation.overlap import separar_em_blocos


def test_modelo_identidade_reconstroi_a_mix():
    mix = np.random.default_rng(0).standard_normal((50000, 2)).astype(np.float32) * 0.1

    def inferir(bloco, indice, total):
        return bloco[None, :, :]

    saida = separar_em_blocos(mix, 8000, 2000, inferir)[0].T
    assert saida.shape == mix.shape
    assert np.max(np.abs(saida - mix)) < 1e-5
