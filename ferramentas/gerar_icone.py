"""Ícones da família Bravo (Bravo Finance, Bravo PDF e os próximos apps).

Todos os apps da família usam a mesma base: um "squircle" (cantos contínuos, como
os ícones do macOS e do iOS) na cor da marca, com um leve degradê, e um símbolo
geométrico branco com um ponto na cor de destaque. Só o símbolo muda de app para app.

Uso: python ferramentas/gerar_icone.py   (precisa de Pillow)
Gera app/icone/bravo-pdf.{png,ico,icns}, bravo-pdf-256.png e favicon.png.
Base igual à do Bravo Finance; o símbolo do Bravo PDF é uma folha com a dobra na cor de destaque.
As cores vêm de PALETA, no topo: troque ali para seguir a identidade visual.
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

PALETA = {  # cores da paleta BestMap: tinta, papel e o laranja do logo
    "base": (14, 14, 14),         # ink #0E0E0E
    "base_clara": (46, 46, 43),   # #2E2E2B, ponta clara do degradê
    "destaque": (194, 65, 12),    # brand-mark #C2410C
    "simbolo": (245, 245, 242),   # paper #F5F5F2
}
S = 2048
DEST = Path(__file__).resolve().parent.parent / "app" / "icone"


def squircle(lado, n=5.0, pontos=720):
    """Polígono de uma superelipse |x|^n + |y|^n = 1, ocupando lado×lado."""
    r = lado / 2
    pts = []
    for i in range(pontos):
        t = 2 * math.pi * i / pontos
        c, s = math.cos(t), math.sin(t)
        x = math.copysign(abs(c) ** (2 / n), c)
        y = math.copysign(abs(s) ** (2 / n), s)
        pts.append((r + r * x, r + r * y))
    return pts


def base(paleta):
    m = int(S * 0.098)  # margem padrão dos ícones de app do macOS
    lado = S - 2 * m
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).polygon([(x + m, y + m) for x, y in squircle(lado)], fill=255)

    # degradê radial: mais claro no alto à esquerda
    g = Image.new("L", (256, 256))
    px = g.load()
    for y in range(256):
        for x in range(256):
            d = math.hypot(x - 40, y - 20) / 330
            px[x, y] = int(255 * min(1, d))
    g = g.resize((S, S), Image.BICUBIC)
    fundo = Image.composite(Image.new("RGB", (S, S), paleta["base"]), Image.new("RGB", (S, S), paleta["base_clara"]), g)

    icone = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sombra = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sombra).polygon([(x + m, y + m + S * 0.012) for x, y in squircle(lado)], fill=90)
    icone.paste((0, 0, 0, 255), (0, 0), sombra.filter(ImageFilter.GaussianBlur(S * 0.016)))
    icone.paste(fundo, (0, 0), mascara)
    # filete de luz na borda de cima
    borda = Image.new("L", (S, S), 0)
    ImageDraw.Draw(borda).polygon([(x + m, y + m) for x, y in squircle(lado)], outline=70, width=int(S * 0.004))
    luz = Image.new("L", (S, S), 0)
    ImageDraw.Draw(luz).rectangle((0, 0, S, S * 0.5), fill=255)
    icone.paste((255, 255, 255, 255), (0, 0), Image.composite(borda, Image.new("L", (S, S), 0), luz.filter(ImageFilter.GaussianBlur(S * 0.1))))
    return icone, m, lado


def simbolo_finance(d, m, lado, paleta):
    """Gráfico de rosca: anel branco com uma fatia na cor de destaque."""
    cx = cy = m + lado / 2
    r = lado * 0.27
    w = int(lado * 0.115)
    caixa = (cx - r, cy - r, cx + r, cy + r)
    folga = 42  # graus entre as fatias (as pontas redondas ocupam ~30)
    # PIL mede ângulos a partir das 3h, no sentido horário; -90 = meio-dia
    d.arc(caixa, -90 + folga / 2, 20 - folga / 2, fill=(*paleta["destaque"], 255), width=w)
    d.arc(caixa, 20 + folga / 2, 150 - folga / 2, fill=(*paleta["simbolo"], 170), width=w)
    d.arc(caixa, 150 + folga / 2, 270 - folga / 2, fill=(*paleta["simbolo"], 255), width=w)
    # pontas arredondadas
    for ang, cor in ((-90 + folga / 2, paleta["destaque"]), (20 - folga / 2, paleta["destaque"]),
                     (20 + folga / 2, paleta["simbolo"] + (170,)), (150 - folga / 2, paleta["simbolo"] + (170,)),
                     (150 + folga / 2, paleta["simbolo"]), (270 - folga / 2, paleta["simbolo"])):
        rr = r - w / 2
        x, y = cx + rr * math.cos(math.radians(ang)), cy + rr * math.sin(math.radians(ang))
        c = cor if len(cor) == 4 else (*cor, 255)
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=c)


def simbolo_pdf(d, m, lado, paleta):
    """Folha de papel com o canto dobrado na cor de destaque e linhas de texto."""
    cx = m + lado / 2
    w, h = lado * 0.42, lado * 0.54
    x0, y0 = cx - w / 2, m + lado / 2 - h / 2
    x1, y1 = x0 + w, y0 + h
    dobra = w * 0.34
    raio = lado * 0.035
    papel = (*paleta["simbolo"], 255)
    # folha: retângulo arredondado sem o canto de cima à direita
    d.rounded_rectangle((x0, y0, x1, y1), raio, fill=papel)
    d.polygon([(x1 - dobra, y0 - 1), (x1 + 1, y0 - 1), (x1 + 1, y0 + dobra)], fill=(0, 0, 0, 0))
    d.rectangle((x1 - dobra - raio, y0, x1 - dobra, y0 + raio), fill=papel)
    d.rectangle((x1 - raio, y0 + dobra, x1, y0 + dobra + raio), fill=papel)
    # dobra
    d.polygon([(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)], fill=(*paleta["destaque"], 255))
    # linhas de texto
    esp = lado * 0.042
    cinza = (142, 142, 135, 255)  # #8E8E87, cinza da paleta
    for i, frac in enumerate((0.62, 0.78, 0.70, 0.46)):
        yy = y0 + h * 0.42 + i * esp * 2.0
        d.rounded_rectangle((x0 + w * 0.16, yy, x0 + w * 0.16 + w * 0.68 * frac / 0.78, yy + esp), esp / 2, fill=cinza)


def desenhar(simbolo=simbolo_pdf, paleta=PALETA):
    icone, m, lado = base(paleta)
    camada = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    simbolo(ImageDraw.Draw(camada), m, lado, paleta)
    icone = Image.alpha_composite(icone, camada)
    return icone.resize((1024, 1024), Image.LANCZOS)


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    img = desenhar()
    img.save(DEST / "bravo-pdf.png")
    img.resize((256, 256), Image.LANCZOS).save(DEST / "bravo-pdf-256.png")
    img.resize((64, 64), Image.LANCZOS).save(DEST / "favicon.png")
    img.save(DEST / "bravo-pdf.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(DEST / "bravo-pdf.icns")
    print("Ícones em", DEST)


if __name__ == "__main__":
    main()
