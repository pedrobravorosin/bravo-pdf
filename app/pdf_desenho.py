"""Desenho em PDF: geometria da página, fontes padrão, imagens e formulários XObject.

Tudo o que o Bravo PDF acrescenta a uma página (anotações, assinaturas, marca
d'água, numeração, texto do OCR) é desenhado em "coordenadas de tela": pontos
a partir do canto superior esquerdo da página como ela aparece (já com a
rotação própria do PDF), com y crescendo para baixo. A classe Geo converte
essas coordenadas para o espaço do PDF.
"""
import io
import math
import zlib

from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject,
                           NumberObject, StreamObject)

try:  # métricas das 14 fontes padrão (dados da Adobe distribuídos com o pypdf)
    from pypdf._codecs.core_font_metrics import CORE_FONT_METRICS
except ImportError:  # pragma: no cover
    CORE_FONT_METRICS = {}

FONTES = {
    ("helv", False, False): "Helvetica", ("helv", True, False): "Helvetica-Bold",
    ("helv", False, True): "Helvetica-Oblique", ("helv", True, True): "Helvetica-BoldOblique",
    ("times", False, False): "Times-Roman", ("times", True, False): "Times-Bold",
    ("times", False, True): "Times-Italic", ("times", True, True): "Times-BoldItalic",
    ("cour", False, False): "Courier", ("cour", True, False): "Courier-Bold",
    ("cour", False, True): "Courier-Oblique", ("cour", True, True): "Courier-BoldOblique",
}


def num(v):
    """Número curto para o fluxo de conteúdo."""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def cor(hexa, padrao=(0, 0, 0)):
    try:
        h = str(hexa).lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, TypeError):
        return padrao


def rg(c, contorno=False):
    r, g, b = c
    return f"{num(r)} {num(g)} {num(b)} {'RG' if contorno else 'rg'}"


def caixa_visivel(page):
    """CropBox limitada pela MediaBox (o que os leitores mostram)."""
    m = [float(v) for v in page.mediabox]
    try:  # lido sem a propriedade .cropbox, que grava a caixa na página (e muda o arquivo)
        cb = page.get("/CropBox")
        c = [float(v) for v in cb.get_object()] if cb is not None else m
        if len(c) != 4:
            c = m
    except Exception:  # noqa: BLE001
        c = m
    ml, mb, mr, mt = min(m[0], m[2]), min(m[1], m[3]), max(m[0], m[2]), max(m[1], m[3])
    cl, cb, cr, ct = min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])
    caixa = (max(ml, cl), max(mb, cb), min(mr, cr), min(mt, ct))
    if caixa[2] - caixa[0] < 1 or caixa[3] - caixa[1] < 1:
        caixa = (ml, mb, mr, mt)
    return caixa


class Geo:
    """Converte coordenadas de tela (pontos, origem no alto à esquerda) para o espaço do PDF."""

    def __init__(self, caixa, rotacao):
        self.l, self.b, self.r, self.t = caixa
        self.wu, self.hu = self.r - self.l, self.t - self.b
        self.rot = int(rotacao or 0) % 360
        if self.rot % 90:
            self.rot = 0
        self.W, self.H = (self.wu, self.hu) if self.rot in (0, 180) else (self.hu, self.wu)

    @classmethod
    def da_pagina(cls, page):
        return cls(caixa_visivel(page), page.get("/Rotate", 0) or 0)

    def para_pdf(self, x, y):
        w, h = self.wu, self.hu
        if self.rot == 0:
            ux, uy = x, y
        elif self.rot == 90:
            ux, uy = y, h - x
        elif self.rot == 180:
            ux, uy = w - x, h - y
        else:
            ux, uy = w - y, x
        return self.l + ux, self.t - uy

    def para_tela(self, px, py):
        w, h = self.wu, self.hu
        ux, uy = px - self.l, self.t - py
        if self.rot == 0:
            return ux, uy
        if self.rot == 90:
            return h - uy, ux
        if self.rot == 180:
            return w - ux, h - uy
        return uy, w - ux

    def matriz(self):
        e, f = self.para_pdf(0, 0)
        a, b = self.para_pdf(1, 0)
        c, d = self.para_pdf(0, 1)
        return [a - e, b - f, c - e, d - f, e, f]

    def retangulo_pdf(self, x0, y0, x1, y1):
        pts = [self.para_pdf(x, y) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return [min(xs), min(ys), max(xs), max(ys)]

    def retangulo_tela(self, r):
        pts = [self.para_tela(x, y) for x, y in ((r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3]))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return [min(xs), min(ys), max(xs), max(ys)]


def texto_pdf(s):
    """String literal do PDF em WinAnsi (português completo); caracteres sem equivalente viram '?'."""
    b = str(s).encode("cp1252", "replace")
    out = []
    for c in b:
        if c in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(c))
        elif 32 <= c < 127:
            out.append(chr(c))
        else:
            out.append(f"\\{c:03o}")
    return "(" + "".join(out) + ")"


def largura_texto(s, fonte, tamanho):
    m = CORE_FONT_METRICS.get(fonte)
    if not m:
        return len(s) * tamanho * (0.6 if fonte.startswith("Courier") else 0.5)
    w = m.character_widths
    padrao = w.get("default", 500)
    total = 0
    for ch in str(s):
        total += w.get(ch, padrao)
    return total * tamanho / 1000


def fonte_dict(nome):
    d = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                          NameObject("/BaseFont"): NameObject("/" + nome)})
    if not nome.startswith(("Symbol", "ZapfDingbats")):
        d[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
    return d


def imagem_xobject(writer, pil, qualidade=90):
    """Cria um XObject de imagem (com transparência quando houver) a partir de uma imagem Pillow."""
    im = pil
    if im.mode == "P":
        im = im.convert("RGBA")
    alfa = None
    if im.mode in ("RGBA", "LA"):
        alfa = im.getchannel("A")
        if alfa.getextrema() == (255, 255):
            alfa = None
        im = im.convert("RGB" if im.mode == "RGBA" else "L")
    elif im.mode not in ("RGB", "L", "CMYK"):
        im = im.convert("RGB")
    w, h = im.size
    espaco = {"RGB": "/DeviceRGB", "L": "/DeviceGray", "CMYK": "/DeviceCMYK"}[im.mode]
    foto = w * h > 250_000 and im.mode != "L" and alfa is None
    if foto:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=qualidade, optimize=True)
        dados, filtro = buf.getvalue(), "/DCTDecode"
    else:
        dados, filtro = zlib.compress(im.tobytes(), 9), "/FlateDecode"
    s = StreamObject()
    s._data = dados
    s.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
              NameObject("/Width"): NumberObject(w), NameObject("/Height"): NumberObject(h),
              NameObject("/ColorSpace"): NameObject(espaco), NameObject("/BitsPerComponent"): NumberObject(8),
              NameObject("/Filter"): NameObject(filtro)})
    if im.mode == "CMYK" and foto:
        s[NameObject("/Decode")] = ArrayObject([FloatObject(v) for v in (1, 0, 1, 0, 1, 0, 1, 0)])
    if alfa is not None:
        m = StreamObject()
        m._data = zlib.compress(alfa.tobytes(), 9)
        m.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                  NameObject("/Width"): NumberObject(w), NameObject("/Height"): NumberObject(h),
                  NameObject("/ColorSpace"): NameObject("/DeviceGray"), NameObject("/BitsPerComponent"): NumberObject(8),
                  NameObject("/Filter"): NameObject("/FlateDecode")})
        s[NameObject("/SMask")] = writer._add_object(m)
    return writer._add_object(s)


class Pincel:
    """Monta um fluxo de conteúdo em coordenadas de tela, com os recursos que ele usa."""

    def __init__(self, writer):
        self.writer = writer
        self.ops = []
        self.fontes = {}
        self.imagens = {}
        self.estados = {}

    def __iadd__(self, op):
        self.ops.append(op)
        return self

    def fonte(self, nome):
        if nome not in self.fontes:
            self.fontes[nome] = (f"F{len(self.fontes) + 1}", fonte_dict(nome))
        return self.fontes[nome][0]

    def imagem(self, pil):
        chave = f"Im{len(self.imagens) + 1}"
        self.imagens[chave] = imagem_xobject(self.writer, pil)
        return chave

    def opacidade(self, preenchimento=1.0, contorno=1.0, multiplicar=False):
        chave = (round(preenchimento, 3), round(contorno, 3), multiplicar)
        if chave not in self.estados:
            d = DictionaryObject({NameObject("/Type"): NameObject("/ExtGState"),
                                  NameObject("/ca"): FloatObject(chave[0]), NameObject("/CA"): FloatObject(chave[1])})
            if multiplicar:
                d[NameObject("/BM")] = NameObject("/Multiply")
            self.estados[chave] = (f"GS{len(self.estados) + 1}", d)
        return self.estados[chave][0]

    def texto(self, x, y_base, s, fonte, tamanho, c=(0, 0, 0), modo=0, escala_h=100, angulo=0):
        """Escreve uma linha com a linha de base em (x, y_base), na tela (glifos na posição certa).
        angulo: graus no sentido anti-horário, como se vê na tela."""
        f = self.fonte(fonte)
        tz = f" {num(escala_h)} Tz" if abs(escala_h - 100) > 0.01 else ""
        tr = f" {modo} Tr" if modo else ""
        ca, sa = math.cos(math.radians(angulo)), math.sin(math.radians(angulo))
        self.ops.append(f"BT /{f} {num(tamanho)} Tf{tz}{tr} {rg(c)} {num(ca)} {num(-sa)} {num(-sa)} {num(-ca)} "
                        f"{num(x)} {num(y_base)} Tm {texto_pdf(s)} Tj ET")

    def recursos(self):
        r = DictionaryObject()
        if self.fontes:
            r[NameObject("/Font")] = DictionaryObject({NameObject("/" + k): self.writer._add_object(d)
                                                       for k, d in self.fontes.values()})
        if self.imagens:
            r[NameObject("/XObject")] = DictionaryObject({NameObject("/" + k): v for k, v in self.imagens.items()})
        if self.estados:
            r[NameObject("/ExtGState")] = DictionaryObject({NameObject("/" + k): d for k, d in self.estados.values()})
        return r

    def conteudo(self):
        return "\n".join(self.ops).encode("latin-1")

    def formulario(self, geo, bbox):
        """XObject de formulário com este desenho, posicionado na página pela matriz da Geo."""
        s = StreamObject()
        s._data = zlib.compress(self.conteudo())
        s.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                  NameObject("/BBox"): ArrayObject([FloatObject(v) for v in bbox]),
                  NameObject("/Matrix"): ArrayObject([FloatObject(round(v, 6)) for v in geo.matriz()]),
                  NameObject("/Resources"): self.recursos(), NameObject("/Filter"): NameObject("/FlateDecode")})
        return self.writer._add_object(s)


def acrescentar_ao_conteudo(writer, page, xobjs, nome_base="Bv"):
    """Desenha XObjects de formulário por cima do conteúdo da página (isolando o conteúdo original)."""
    if not xobjs:
        return
    page_res = page.get("/Resources")
    page_res = page_res.get_object() if page_res is not None else DictionaryObject()
    page_res = DictionaryObject(page_res)  # cópia: recursos podem ser compartilhados entre páginas
    xo = page_res.get("/XObject")
    xo = DictionaryObject(xo.get_object()) if xo is not None else DictionaryObject()
    ops = []
    i = 0
    for ref in xobjs:
        while True:
            i += 1
            nome = f"/{nome_base}{i}"
            if nome not in xo:
                break
        xo[NameObject(nome)] = ref
        ops.append(f"q {nome} Do Q")
    page_res[NameObject("/XObject")] = xo
    page[NameObject("/Resources")] = page_res
    antes, depois = DecodedStreamObject(), DecodedStreamObject()
    antes.set_data(b"q\n")
    depois.set_data(("\nQ\n" + "\n".join(ops) + "\n").encode("latin-1"))
    atual = page.get("/Contents")
    partes = []
    if atual is not None:
        atual = atual.get_object()
        partes = list(atual) if isinstance(atual, ArrayObject) else [page.raw_get("/Contents")]
    page[NameObject("/Contents")] = ArrayObject([writer._add_object(antes), *partes, writer._add_object(depois)])
