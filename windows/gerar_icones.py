"""Gera windows/cronograma.ico e windows/atualizar.ico (precisa do Pillow: pip install pillow).

Os .ico já estão no repositório; só rode de novo se quiser mudar o desenho.
"""
from pathlib import Path

from PIL import Image, ImageDraw

PASTA = Path(__file__).resolve().parent
TAM = 256
AZUL, BRANCO, LARANJA, VERDE = (31, 78, 140), (255, 255, 255), (242, 153, 46), (46, 160, 90)


def base() -> Image.Image:
    img = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, 248, 248), radius=44, fill=AZUL)
    # barras de Gantt em escada
    barras = [(40, 52, 128), (80, 100, 176), (112, 148, 208), (64, 196, 150)]
    for x0, y, x1 in barras:
        d.rounded_rectangle((x0, y, x1, y + 28), radius=8, fill=BRANCO)
    d.rounded_rectangle((150, 196, 216, 224), radius=8, fill=LARANJA)  # o marco final
    return img


def atualizar() -> Image.Image:
    img = base()
    d = ImageDraw.Draw(img)
    d.ellipse((136, 136, 252, 252), fill=VERDE, outline=BRANCO, width=8)
    # seta para baixo (baixar a versão nova)
    d.polygon([(194, 226), (162, 188), (182, 188), (182, 156), (206, 156), (206, 188), (226, 188)], fill=BRANCO)
    return img


TAMANHOS = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
base().save(PASTA / "cronograma.ico", sizes=TAMANHOS)
atualizar().save(PASTA / "atualizar.ico", sizes=TAMANHOS)
print("ícones gerados")
