"""Ícone na bandeja: o estado no tooltip e Sair no menu."""

from PIL import Image, ImageDraw
import pystray


def criar_icone(texto, ao_abrir, ao_sair):
    """`texto` é lido quando o tooltip atualiza e quando o menu abre."""
    imagem = Image.new("RGB", (64, 64), "#141414")
    desenho = ImageDraw.Draw(imagem)
    desenho.rounded_rectangle((6, 6, 58, 58), radius=14, fill="#1f6f4a")
    desenho.polygon([(26, 18), (26, 46), (48, 32)], fill="#f4f1e8")
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: texto(), None, enabled=False),
        pystray.MenuItem("Abrir pasta de stems", lambda icon, item: ao_abrir()),
        pystray.MenuItem("Sair", lambda icon, item: ao_sair(icon)),
    )
    return pystray.Icon("VibeDJ Stems", imagem, texto(), menu)
