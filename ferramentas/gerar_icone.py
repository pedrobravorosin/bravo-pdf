"""Gera o ícone do Bravo PDF (PNG, ICO e ICNS) em app/icone/.

Uso: python ferramentas/gerar_icone.py   (precisa de Pillow e da fonte Inter ExtraBold)
Mesma família visual do Bravo Finance: fundo azul-petróleo, letra branca e detalhe dourado.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2048
DEST = Path(__file__).resolve().parent.parent / "app" / "icone"
FONTE = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"


def gradiente(w, h, c1, c2):
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(w):
            t = (x + y) / (w + h - 2)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
    return g


def desenhar():
    m = int(S * 0.098)
    lado = S - 2 * m
    raio = int(lado * 0.225)
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((m, m, m + lado, m + lado), raio, fill=255)
    fundo = gradiente(256, 256, (14, 23, 48), (21, 74, 140)).resize((S, S), Image.BICUBIC)
    brilho = Image.new("L", (S, S), 0)
    ImageDraw.Draw(brilho).ellipse((-S * 0.2, -S * 0.9, S * 1.2, S * 0.35), fill=34)
    brilho = brilho.filter(ImageFilter.GaussianBlur(S * 0.12))
    fundo = Image.composite(Image.new("RGB", (S, S), (255, 255, 255)), fundo, brilho)

    icone = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sombra = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sombra).rounded_rectangle((m, m + S * 0.012, m + lado, m + lado + S * 0.012), raio, fill=110)
    sombra = sombra.filter(ImageFilter.GaussianBlur(S * 0.018))
    icone.paste((0, 0, 0, 255), (0, 0), sombra)
    icone.paste(fundo, (0, 0), mascara)

    d = ImageDraw.Draw(icone)
    # folha de papel com canto dobrado
    x0, y0 = m + lado * 0.24, m + lado * 0.16
    x1, y1 = m + lado * 0.76, m + lado * 0.84
    dobra = lado * 0.14
    folha_sombra = Image.new("L", (S, S), 0)
    ImageDraw.Draw(folha_sombra).polygon([(x0, y0 + 18), (x1 - dobra, y0 + 18), (x1, y0 + dobra + 18), (x1, y1 + 18), (x0, y1 + 18)], fill=90)
    folha_sombra = folha_sombra.filter(ImageFilter.GaussianBlur(S * 0.015))
    icone.paste((0, 0, 0, 255), (0, 0), folha_sombra)
    d.polygon([(x0, y0), (x1 - dobra, y0), (x1, y0 + dobra), (x1, y1), (x0, y1)], fill=(250, 250, 248, 255))
    d.polygon([(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)], fill=(205, 214, 228, 255))
    # "B" azul na folha
    fonte = ImageFont.truetype(FONTE, int(lado * 0.42))
    d.text(((x0 + x1) / 2 - lado * 0.01, y0 + (y1 - y0) * 0.43), "B", font=fonte, fill=(21, 74, 140, 255), anchor="mm")
    # traço dourado de caneta (assinatura) embaixo
    ouro = (244, 196, 92, 255)
    w = int(lado * 0.04)
    pts = [(x0 + lado * 0.06, y1 - lado * 0.13), (x0 + lado * 0.16, y1 - lado * 0.19), (x0 + lado * 0.24, y1 - lado * 0.12),
           (x0 + lado * 0.33, y1 - lado * 0.17), (x1 - lado * 0.06, y1 - lado * 0.15)]
    d.line(pts, fill=ouro, width=w, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2), fill=ouro)
    return icone.resize((1024, 1024), Image.LANCZOS)


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    img = desenhar()
    img.save(DEST / "bravo-pdf.png")
    img.resize((256, 256), Image.LANCZOS).save(DEST / "bravo-pdf-256.png")
    img.resize((64, 64), Image.LANCZOS).save(DEST / "favicon.png")
    img.save(DEST / "bravo-pdf.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(DEST / "bravo-pdf.icns")
    print("ok")


if __name__ == "__main__":
    main()
