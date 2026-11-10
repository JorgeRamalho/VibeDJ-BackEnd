"""A caixa nativa existe e só aceita pasta. O teste não chama Show, então nada aparece na tela."""

from vibedj_stems.dialogo import _FOS_FORCEFILESYSTEM, _FOS_PATHMUSTEXIST, _FOS_PICKFOLDERS, _criar_seletor, _opcoes


def test_caixa_so_aceita_pasta_sem_abrir():
    seletor = _criar_seletor("Selecione a pasta")
    try:
        flags = _opcoes(seletor)
        assert flags & _FOS_PICKFOLDERS
        assert flags & _FOS_FORCEFILESYSTEM
        assert flags & _FOS_PATHMUSTEXIST
    finally:
        seletor.liberar()
