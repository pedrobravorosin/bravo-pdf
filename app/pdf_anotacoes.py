"""Anotações do Bravo PDF: viram anotações PDF de verdade (editáveis em outros leitores)
ou são incorporadas ao conteúdo da página (fixas).

Cada item chega do app em coordenadas de tela (ver pdf_desenho.Geo):
  {"tipo": "marca"|"sublinhado"|"tachado"|"retangulo"|"elipse"|"linha"|"seta"|"caneta"|
           "texto"|"nota"|"carimbo"|"imagem"|"assinatura"|"corretivo",
   "x", "y", "w", "h", "cor", "preenchimento", "espessura", "opacidade", "pontos", "tracos",
   "linhas", "fonte", "tamanho", "negrito", "italico", "fundo", "texto", "imagem", "fixo"}
"""
import base64
import io
import math
import secrets
import time

from pypdf.generic import (ArrayObject, BooleanObject, DictionaryObject, FloatObject, NameObject, NumberObject, TextStringObject)

from pdf_desenho import FONTES, Pincel, cor, num, rg

SEMPRE_FIXOS = {"assinatura", "corretivo"}
K = 0.5523  # curva de Bézier para elipses
MAX_IMAGEM = 25 * 1024 * 1024


def _f(d, k, padrao=0.0, minimo=None, maximo=None):
    try:
        v = float(d.get(k, padrao))
        if not math.isfinite(v):
            v = padrao
    except (TypeError, ValueError):
        v = padrao
    if minimo is not None:
        v = max(minimo, v)
    if maximo is not None:
        v = min(maximo, v)
    return v


def _pontos(lista, limite=20000):
    out = []
    for p in (lista or [])[:limite]:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            out.append((x, y))
    return out


def imagem_de_dataurl(texto):
    from PIL import Image, ImageOps
    if not isinstance(texto, str) or "," not in texto:
        raise ValueError("imagem inválida")
    cab, dados = texto.split(",", 1)
    if not cab.startswith("data:image/") or ";base64" not in cab:
        raise ValueError("imagem inválida")
    bruto = base64.b64decode(dados, validate=False)
    if len(bruto) > MAX_IMAGEM:
        raise ValueError("imagem grande demais")
    Image.MAX_IMAGE_PIXELS = 60_000_000
    im = Image.open(io.BytesIO(bruto))
    im.load()
    return ImageOps.exif_transpose(im)


def _elipse(x, y, w, h):
    cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
    ox, oy = rx * K, ry * K
    return (f"{num(cx + rx)} {num(cy)} m "
            f"{num(cx + rx)} {num(cy + oy)} {num(cx + ox)} {num(cy + ry)} {num(cx)} {num(cy + ry)} c "
            f"{num(cx - ox)} {num(cy + ry)} {num(cx - rx)} {num(cy + oy)} {num(cx - rx)} {num(cy)} c "
            f"{num(cx - rx)} {num(cy - oy)} {num(cx - ox)} {num(cy - ry)} {num(cx)} {num(cy - ry)} c "
            f"{num(cx + ox)} {num(cy - ry)} {num(cx + rx)} {num(cy - oy)} {num(cx + rx)} {num(cy)} c h")


def _seta(p0, p1, esp):
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    tam = max(8, esp * 4)
    a1 = (p1[0] - tam * math.cos(ang - 0.45), p1[1] - tam * math.sin(ang - 0.45))
    a2 = (p1[0] - tam * math.cos(ang + 0.45), p1[1] - tam * math.sin(ang + 0.45))
    return f"{num(a1[0])} {num(a1[1])} m {num(p1[0])} {num(p1[1])} l {num(a2[0])} {num(a2[1])} l S"


def _quad(geo, x, y, w, h):
    pts = [geo.para_pdf(*p) for p in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))]
    return ArrayObject([FloatObject(round(v, 3)) for p in pts for v in p])


def desenhar(writer, geo, a):
    """Desenha um item. Devolve (xobject, bbox em tela, subtipo, extras do dicionário da anotação)."""
    tipo = a.get("tipo")
    p = Pincel(writer)
    x, y = _f(a, "x"), _f(a, "y")
    w, h = _f(a, "w", 0, 0, 20000), _f(a, "h", 0, 0, 20000)
    c = cor(a.get("cor"), (0.85, 0.15, 0.15))
    esp = _f(a, "espessura", 2, 0.25, 72)
    opac = _f(a, "opacidade", 1, 0.05, 1)
    extras = {}
    folga = esp
    if opac < 1 and tipo != "marca":
        p += f"/{p.opacidade(opac, opac)} gs"

    if tipo == "marca":
        cm = cor(a.get("cor"), (1, 0.83, 0))
        p += f"/{p.opacidade(_f(a, 'opacidade', 0.45, 0.05, 1), 1, True)} gs {rg(cm)}"
        p += f"{num(x)} {num(y)} {num(w)} {num(h)} re f"
        sub, folga, c = "/Highlight", 0, cm
        extras["/QuadPoints"] = _quad(geo, x, y, w, h)
    elif tipo in ("sublinhado", "tachado"):
        yy = y + h - esp / 2 if tipo == "sublinhado" else y + h * 0.55
        p += f"{rg(c, True)} {num(esp)} w {num(x)} {num(yy)} m {num(x + w)} {num(yy)} l S"
        sub = "/Underline" if tipo == "sublinhado" else "/StrikeOut"
        extras["/QuadPoints"] = _quad(geo, x, y, w, h)
    elif tipo in ("retangulo", "elipse", "corretivo"):
        if tipo == "corretivo":
            fundo, borda = cor(a.get("cor"), (1, 1, 1)), None
            folga = 0
        else:
            fundo = cor(a["preenchimento"]) if a.get("preenchimento") else None
            borda = c
        caminho = _elipse(x, y, w, h) if tipo == "elipse" else f"{num(x)} {num(y)} {num(w)} {num(h)} re"
        op = "B" if fundo and borda else ("f" if fundo else "S")
        p += " ".join(filter(None, [rg(fundo) if fundo else "", rg(borda, True) if borda else "",
                                     f"{num(esp)} w" if borda else "", caminho, op]))
        sub = "/Circle" if tipo == "elipse" else "/Square"
        if borda:
            extras["/BS"] = DictionaryObject({NameObject("/W"): FloatObject(esp)})
        if fundo and tipo != "corretivo":
            extras["/IC"] = ArrayObject([FloatObject(v) for v in fundo])
    elif tipo in ("linha", "seta"):
        pts = _pontos(a.get("pontos"), 2)
        if len(pts) < 2:
            return None
        (x0, y0), (x1, y1) = pts
        p += f"{rg(c, True)} {num(esp)} w 1 J 1 j {num(x0)} {num(y0)} m {num(x1)} {num(y1)} l S"
        if tipo == "seta":
            p += _seta(pts[0], pts[1], esp)
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        folga = esp + (max(8, esp * 4) if tipo == "seta" else 0)
        sub = "/Line"
        q0, q1 = geo.para_pdf(x0, y0), geo.para_pdf(x1, y1)
        extras["/L"] = ArrayObject([FloatObject(round(v, 3)) for v in (*q0, *q1)])
        extras["/BS"] = DictionaryObject({NameObject("/W"): FloatObject(esp)})
        if tipo == "seta":
            extras["/LE"] = ArrayObject([NameObject("/None"), NameObject("/OpenArrow")])
    elif tipo == "caneta":
        tracos = [_pontos(t, 5000) for t in (a.get("tracos") or [])[:500]]
        tracos = [t for t in tracos if t]
        if not tracos:
            return None
        p += f"{rg(c, True)} {num(esp)} w 1 J 1 j"
        tinta = ArrayObject()
        for t in tracos:
            seg = [f"{num(t[0][0])} {num(t[0][1])} m"] + [f"{num(px)} {num(py)} l" for px, py in t[1:]]
            if len(t) == 1:
                seg.append(f"{num(t[0][0] + 0.01)} {num(t[0][1])} l")
            p += " ".join(seg) + " S"
            tinta.append(ArrayObject([FloatObject(round(v, 3)) for pt in t for v in geo.para_pdf(*pt)]))
        xs = [pt[0] for t in tracos for pt in t]
        ys = [pt[1] for t in tracos for pt in t]
        x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        sub = "/Ink"
        extras["/InkList"] = tinta
        extras["/BS"] = DictionaryObject({NameObject("/W"): FloatObject(esp)})
    elif tipo in ("texto", "carimbo"):
        linhas = [str(s)[:2000] for s in (a.get("linhas") or [str(a.get("texto") or "")])][:500]
        fam = a.get("fonte") if a.get("fonte") in ("helv", "times", "cour") else "helv"
        negrito = bool(a.get("negrito")) or tipo == "carimbo"
        fonte = FONTES[(fam, negrito, bool(a.get("italico")))]
        tam = _f(a, "tamanho", 14, 4, 400)
        pad = 4 if tipo == "carimbo" else 2
        if tipo == "carimbo":
            p += f"{rg(c, True)} {num(max(esp, 2))} w {num(x + 1)} {num(y + 1)} {num(w - 2)} {num(h - 2)} re S"
        elif a.get("fundo"):
            p += f"{rg(cor(a['fundo']))} {num(x)} {num(y)} {num(w)} {num(h)} re f"
        if a.get("borda") and tipo == "texto":
            p += f"{rg(c, True)} 1 w {num(x)} {num(y)} {num(w)} {num(h)} re S"
        p += f"q {num(x)} {num(y)} {num(w)} {num(h)} re W n"
        for i, linha in enumerate(linhas):
            p.texto(x + pad, y + pad + tam * (0.94 + 1.2 * i), linha, fonte, tam, c)
        p += "Q"
        folga = 2
        sub = "/FreeText"
        extras["/Contents"] = TextStringObject("\n".join(linhas))
        extras["/DA"] = TextStringObject(f"/Helv {num(tam)} Tf {rg(c)}")
    elif tipo == "nota":
        w = h = 20.0
        cn = cor(a.get("cor"), (1, 0.83, 0))
        p += (f"{rg(cn)} 0.35 0.3 0.1 RG 1 w {num(x + 1)} {num(y + 1)} 18 15 re B "
              f"{num(x + 5)} {num(y + 16)} m {num(x + 5)} {num(y + 20)} l {num(x + 10)} {num(y + 16)} l h B "
              f"0.35 0.3 0.1 RG 1 w {num(x + 4)} {num(y + 5.5)} m {num(x + 16)} {num(y + 5.5)} l "
              f"{num(x + 4)} {num(y + 9)} m {num(x + 16)} {num(y + 9)} l {num(x + 4)} {num(y + 12.5)} m "
              f"{num(x + 12)} {num(y + 12.5)} l S")
        sub, c, folga = "/Text", cn, 1
        extras["/Contents"] = TextStringObject(str(a.get("texto") or "")[:20000])
        extras["/Name"] = NameObject("/Comment")
        extras["/Open"] = BooleanObject(False)
    elif tipo in ("imagem", "assinatura"):
        im = imagem_de_dataurl(a.get("imagem"))
        if w <= 0 or h <= 0:
            return None
        nome = p.imagem(im)
        p += f"q {num(w)} 0 0 {num(-h)} {num(x)} {num(y + h)} cm /{nome} Do Q"
        sub, folga = "/Stamp", 0
    else:
        return None

    bbox = [x - folga, y - folga, x + w + folga, y + h + folga]
    if bbox[2] - bbox[0] < 1:
        bbox[2] = bbox[0] + 1
    if bbox[3] - bbox[1] < 1:
        bbox[3] = bbox[1] + 1
    extras.setdefault("/C", ArrayObject([FloatObject(v) for v in c]))
    if opac < 1:
        extras["/CA"] = FloatObject(opac)
    return p.formulario(geo, bbox), bbox, sub, extras


def aplicar(writer, page, geo, itens, incorporar=False, autor=""):
    """Acrescenta os itens à página. Devolve quantos foram aplicados."""
    from pdf_desenho import acrescentar_ao_conteudo
    fixos, anots = [], []
    agora = time.strftime("D:%Y%m%d%H%M%S")
    for a in itens:
        if not isinstance(a, dict) or a.get("tipo") in (None, "tarja", "edicao"):
            continue
        r = desenhar(writer, geo, a)
        if r is None:
            continue
        xo, bbox, sub, extras = r
        if incorporar or a.get("fixo") or a.get("tipo") in SEMPRE_FIXOS:
            fixos.append(xo)
            continue
        d = DictionaryObject({NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject(sub),
                              NameObject("/Rect"): ArrayObject([FloatObject(round(v, 3)) for v in geo.retangulo_pdf(*bbox)]),
                              NameObject("/F"): NumberObject(4),
                              NameObject("/NM"): TextStringObject("bravo-" + secrets.token_hex(8)),
                              NameObject("/M"): TextStringObject(agora),
                              NameObject("/AP"): DictionaryObject({NameObject("/N"): xo})})
        if autor:
            d[NameObject("/T")] = TextStringObject(autor[:100])
        for k, v in extras.items():
            d[NameObject(k)] = v
        anots.append(writer._add_object(d))
    acrescentar_ao_conteudo(writer, page, fixos)
    if anots:
        atual = page.get("/Annots")
        lista = ArrayObject(list(atual.get_object()) if atual is not None else [])
        lista.extend(anots)
        page[NameObject("/Annots")] = lista
    return len(fixos) + len(anots)
