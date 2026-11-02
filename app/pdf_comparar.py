"""Comparar dois PDFs: diferenças de texto (palavra a palavra) e diferenças visuais por página."""
import difflib

import pypdfium2 as pdfium
from PIL import ImageChops, ImageFilter

from pdf_texto import geo_pdfium

MAX_PALAVRAS = 300_000


def palavras(pdf):
    """[(texto, página, retângulo em tela)] de todas as palavras do documento."""
    saida = []
    for i in range(len(pdf)):
        page = pdf[i]
        geo = geo_pdfium(page)
        # A ordem de leitura do PDFium muda com o /Rotate; sem ele, a mesma página girada
        # dá a mesma sequência de palavras (as caixas não mudam: ficam no espaço da página).
        rot = page.get_rotation()
        if rot:
            page.set_rotation(0)
        tp = page.get_textpage()
        if rot:
            page.set_rotation(rot)
        try:
            n = tp.count_chars()
            texto = tp.get_text_range(0, n) if n else ""
            atual, caixa = [], None
            for k, ch in enumerate(texto[:n]):
                if ch.isspace() or ch == "￾":
                    if atual:
                        saida.append(("".join(atual), i, caixa))
                    atual, caixa = [], None
                    continue
                try:
                    l, b, r, t = tp.get_charbox(k)
                except Exception:  # noqa: BLE001
                    continue
                x0, y0, x1, y1 = geo.retangulo_tela([l, b, r, t])
                caixa = [x0, y0, x1, y1] if caixa is None else [min(caixa[0], x0), min(caixa[1], y0),
                                                                  max(caixa[2], x1), max(caixa[3], y1)]
                atual.append(ch)
            if atual:
                saida.append(("".join(atual), i, caixa))
        finally:
            tp.close()
            page.close()
        if len(saida) > MAX_PALAVRAS:
            break
    return saida


def _juntar(itens):
    """Agrupa retângulos de palavras seguidas da mesma linha."""
    por_pagina = {}
    for _, p, c in itens:
        if c is None:
            continue
        lst = por_pagina.setdefault(p, [])
        if lst and abs(lst[-1][1] - c[1]) < 2 and abs(lst[-1][3] - c[3]) < 2 and c[0] - lst[-1][2] < 12:
            u = lst[-1]
            lst[-1] = [min(u[0], c[0]), min(u[1], c[1]), max(u[2], c[2]), max(u[3], c[3])]
        else:
            lst.append(list(c))
    return [{"p": p, "x": round(c[0], 2), "y": round(c[1], 2), "w": round(c[2] - c[0], 2), "h": round(c[3] - c[1], 2)}
            for p, lst in por_pagina.items() for c in lst]


def comparar_texto(pdf_a, pdf_b):
    wa, wb = palavras(pdf_a), palavras(pdf_b)
    sm = difflib.SequenceMatcher(a=[w[0] for w in wa], b=[w[0] for w in wb], autojunk=False)
    mudancas = []
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            continue
        tipo = {"replace": "alterado", "delete": "removido", "insert": "adicionado"}[op]
        mudancas.append({
            "tipo": tipo,
            "antes": " ".join(w[0] for w in wa[a0:a1])[:500], "depois": " ".join(w[0] for w in wb[b0:b1])[:500],
            "pa": wa[a0][1] if a1 > a0 else (wa[a0 - 1][1] if a0 else 0),
            "pb": wb[b0][1] if b1 > b0 else (wb[b0 - 1][1] if b0 else 0),
            "rects_a": _juntar(wa[a0:a1]), "rects_b": _juntar(wb[b0:b1])})
        if len(mudancas) >= 3000:
            break
    return mudancas, round(sm.ratio() * 100, 1) if (wa or wb) else 100.0


def comparar_visual(pdf_a, pdf_b, dpi=60):
    saida = []
    escala = dpi / 72
    for i in range(min(len(pdf_a), len(pdf_b))):
        pa, pb = pdf_a[i], pdf_b[i]
        ia = pa.render(scale=escala, grayscale=True).to_pil().convert("L")
        ib = pb.render(scale=escala, grayscale=True).to_pil().convert("L")
        pa.close()
        pb.close()
        if ia.size != ib.size:
            ib = ib.resize(ia.size)
        dif = ImageChops.difference(ia, ib).point(lambda v: 255 if v > 40 else 0)
        dif = dif.filter(ImageFilter.MaxFilter(5))
        caixa = dif.getbbox()
        pct = sum(dif.histogram()[255:]) / (dif.size[0] * dif.size[1]) * 100
        regioes = []
        if caixa:
            # regiões em grade, para destacar só onde mudou
            gx, gy = 12, 16
            cw, ch = dif.size[0] / gx, dif.size[1] / gy
            for yy in range(gy):
                for xx in range(gx):
                    sub = dif.crop((int(xx * cw), int(yy * ch), int((xx + 1) * cw), int((yy + 1) * ch)))
                    if sub.getbbox():
                        b = sub.getbbox()
                        regioes.append({"x": round((xx * cw + b[0]) / escala, 1), "y": round((yy * ch + b[1]) / escala, 1),
                                        "w": round((b[2] - b[0]) / escala, 1), "h": round((b[3] - b[1]) / escala, 1)})
        saida.append({"p": i, "diferenca": round(pct, 2), "regioes": regioes[:200]})
    return saida


def comparar(info_a, info_b):
    pdf_a = pdfium.PdfDocument(info_a["caminho"], password=info_a.get("senha") or None)
    pdf_b = pdfium.PdfDocument(info_b["caminho"], password=info_b.get("senha") or None)
    try:
        mudancas, semelhanca = comparar_texto(pdf_a, pdf_b)
        return {"paginas_a": len(pdf_a), "paginas_b": len(pdf_b), "semelhanca": semelhanca,
                "mudancas": mudancas, "visual": comparar_visual(pdf_a, pdf_b)}
    finally:
        pdf_a.close()
        pdf_b.close()
