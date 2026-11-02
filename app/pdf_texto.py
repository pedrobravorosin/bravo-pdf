"""Texto do PDF com o PDFium: extrair, buscar e editar o texto original da página."""
import ctypes

import pypdfium2 as pdfium
import pypdfium2.raw as c

from pdf_desenho import Geo


def geo_pdfium(page):
    """Mesma geometria de pdf_desenho.Geo, a partir de uma página do PDFium."""
    m = page.get_mediabox()
    try:
        cb = page.get_cropbox()
    except Exception:  # noqa: BLE001
        cb = m
    caixa = (max(m[0], cb[0]), max(m[1], cb[1]), min(m[2], cb[2]), min(m[3], cb[3]))
    if caixa[2] - caixa[0] < 1 or caixa[3] - caixa[1] < 1:
        caixa = tuple(m)
    return Geo(caixa, page.get_rotation())


def _rect_tela(geo, l, b, r, t):
    x0, y0, x1, y1 = geo.retangulo_tela([l, b, r, t])
    return {"x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2)}


def texto_pagina(pdf, i):
    page = pdf[i]
    tp = page.get_textpage()
    try:
        return tp.get_text_bounded()
    finally:
        tp.close()
        page.close()


def buscar(pdf, termo, limite=2000):
    """Ocorrências do termo (sem diferenciar maiúsculas), com os retângulos em coordenadas de tela."""
    achados = []
    termo = str(termo)[:200]
    if not termo.strip():
        return achados
    for i in range(len(pdf)):
        page = pdf[i]
        geo = geo_pdfium(page)
        tp = page.get_textpage()
        try:
            busca = tp.search(termo, match_case=False, match_whole_word=False)
            while len(achados) < limite:
                r = busca.get_next()
                if not r:
                    break
                ini, n = r
                rects = []
                for k in range(tp.count_rects(ini, n)):
                    l, b, rr, t = tp.get_rect(k)
                    rects.append(_rect_tela(geo, l, b, rr, t))
                trecho = tp.get_text_range(max(0, ini - 30), min(n + 60, tp.count_chars() - max(0, ini - 30)))
                achados.append({"p": i, "rects": rects, "trecho": trecho.replace("\r", " ").replace("\n", " ")})
            busca.close()
        finally:
            tp.close()
            page.close()
        if len(achados) >= limite:
            break
    return achados


def _texto_obj(obj, tp):
    n = c.FPDFTextObj_GetText(obj, tp.raw, None, 0)
    if n <= 2:
        return ""
    buf = ctypes.create_string_buffer(n)
    c.FPDFTextObj_GetText(obj, tp.raw, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)), n)
    return buf.raw[:n - 2].decode("utf-16-le", "replace")


def _nome_fonte(obj):
    fonte = c.FPDFTextObj_GetFont(obj)
    if not fonte:
        return "", 0, 400, False
    nome = ""
    for fn in ("FPDFFont_GetBaseFontName", "FPDFFont_GetFontName", "FPDFFont_GetFamilyName"):
        f = getattr(c, fn, None)
        if f is None:
            continue
        try:
            n = f(fonte, None, 0)
            if n > 1:
                buf = ctypes.create_string_buffer(n)
                f(fonte, buf, n)
                nome = buf.value.decode("latin-1", "replace")
                break
        except Exception:  # noqa: BLE001
            continue
    flags = c.FPDFFont_GetFlags(fonte) if hasattr(c, "FPDFFont_GetFlags") else 0
    peso = c.FPDFFont_GetWeight(fonte) if hasattr(c, "FPDFFont_GetWeight") else 400
    return nome, flags, peso, bool(c.FPDFFont_GetIsEmbedded(fonte)) if hasattr(c, "FPDFFont_GetIsEmbedded") else False


def _matriz(obj):
    m = c.FS_MATRIX()
    if not c.FPDFPageObj_GetMatrix(obj, m):
        return [1, 0, 0, 1, 0, 0]
    return [m.a, m.b, m.c, m.d, m.e, m.f]


def _tamanho(obj):
    t = ctypes.c_float()
    return float(t.value) if c.FPDFTextObj_GetFontSize(obj, t) else 12.0


def _cor(obj):
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if c.FPDFPageObj_GetFillColor(obj, r, g, b, a):
        return r.value, g.value, b.value, a.value
    return 0, 0, 0, 255


def _familia(nome, flags, peso):
    n = nome.lower()
    mono = "courier" in n or "mono" in n or bool(flags & 1)
    serif = any(s in n for s in ("times", "serif", "georgia", "garamond", "cambria", "book")) and "sans" not in n
    if not mono and not serif and (flags & 2) and "sans" not in n and "arial" not in n and "helv" not in n:
        serif = True
    negrito = peso >= 600 or "bold" in n or "black" in n or "heavy" in n or "semibold" in n
    italico = "italic" in n or "oblique" in n or bool(flags & 64)
    if mono:
        base = {(False, False): "Courier", (True, False): "Courier-Bold", (False, True): "Courier-Oblique",
                (True, True): "Courier-BoldOblique"}
    elif serif:
        base = {(False, False): "Times-Roman", (True, False): "Times-Bold", (False, True): "Times-Italic",
                (True, True): "Times-BoldItalic"}
    else:
        base = {(False, False): "Helvetica", (True, False): "Helvetica-Bold", (False, True): "Helvetica-Oblique",
                (True, True): "Helvetica-BoldOblique"}
    return base[(negrito, italico)]


def objetos_texto(pdf, i):
    """Blocos de texto editáveis da página (objetos de texto do próprio conteúdo)."""
    page = pdf[i]
    geo = geo_pdfium(page)
    tp = page.get_textpage()
    saida = []
    try:
        for k in range(c.FPDFPage_CountObjects(page.raw)):
            obj = c.FPDFPage_GetObject(page.raw, k)
            if c.FPDFPageObj_GetType(obj) != c.FPDF_PAGEOBJ_TEXT:
                continue
            texto = _texto_obj(obj, tp)
            if not texto.strip():
                continue
            l, b, r, t = (ctypes.c_float() for _ in range(4))
            if not c.FPDFPageObj_GetBounds(obj, l, b, r, t):
                continue
            nome, flags, peso, _ = _nome_fonte(obj)
            m = _matriz(obj)
            escala = (m[2] ** 2 + m[3] ** 2) ** 0.5 or 1
            rgb = _cor(obj)
            saida.append({"id": k, "texto": texto, **_rect_tela(geo, l.value, b.value, r.value, t.value),
                          "tamanho": round(_tamanho(obj) * escala, 2), "fonte": _familia(nome, flags, peso),
                          "cor": "#%02x%02x%02x" % rgb[:3]})
    finally:
        tp.close()
        page.close()
    return saida


def editar(origem, senha, destino, pagina, edicoes):
    """Troca o texto de objetos da página. edicoes: [{"id": índice do objeto, "texto": novo}].

    Mantém posição, tamanho, cor e inclinação. Quando a fonte original (normalmente
    embutida só com as letras usadas) não tem todas as letras novas, usa a fonte
    padrão mais parecida (Helvetica, Times ou Courier).
    """
    pdf = pdfium.PdfDocument(_recursos_proprios(origem, senha, pagina))
    try:
        page = pdf[pagina]
        tp = page.get_textpage()
        # letras que cada fonte já desenha nesta página (fontes embutidas parciais só têm essas)
        letras = {}
        objs = []
        for k in range(c.FPDFPage_CountObjects(page.raw)):
            obj = c.FPDFPage_GetObject(page.raw, k)
            objs.append(obj)
            if c.FPDFPageObj_GetType(obj) == c.FPDF_PAGEOBJ_TEXT:
                f = c.FPDFTextObj_GetFont(obj)
                letras.setdefault(ctypes.cast(f, ctypes.c_void_p).value, set()).update(_texto_obj(obj, tp))
        trocas = []
        for e in edicoes:
            k = int(e["id"])
            if not 0 <= k < len(objs) or c.FPDFPageObj_GetType(objs[k]) != c.FPDF_PAGEOBJ_TEXT:
                raise ValueError("bloco de texto não encontrado (o documento mudou?)")
            trocas.append((objs[k], str(e.get("texto", ""))[:5000]))
        for obj, novo in trocas:
            f = c.FPDFTextObj_GetFont(obj)
            disponiveis = letras.get(ctypes.cast(f, ctypes.c_void_p).value, set())
            if novo == "":
                c.FPDFPage_RemoveObject(page.raw, obj)
                c.FPDFPageObj_Destroy(obj)
                continue
            if set(novo) - {" "} <= disponiveis:
                if c.FPDFText_SetText(obj, _wide(novo)):
                    continue
            nome, flags, peso, _ = _nome_fonte(obj)
            m = c.FS_MATRIX()
            c.FPDFPageObj_GetMatrix(obj, m)
            tam = _tamanho(obj)
            r, g, b, a = _cor(obj)
            novo_obj = c.FPDFPageObj_NewTextObj(pdf.raw, _familia(nome, flags, peso).encode(), ctypes.c_float(tam))
            if not novo_obj:
                raise ValueError("não consegui criar o texto")
            c.FPDFText_SetText(novo_obj, _wide(novo))
            c.FPDFPageObj_SetFillColor(novo_obj, r, g, b, a)
            c.FPDFPageObj_SetMatrix(novo_obj, m)
            c.FPDFPage_RemoveObject(page.raw, obj)
            c.FPDFPageObj_Destroy(obj)
            c.FPDFPage_InsertObject(page.raw, novo_obj)
        tp.close()
        if not c.FPDFPage_GenerateContent(page.raw):
            raise ValueError("não consegui gravar a página")
        page.close()
        pdf.save(destino)
    finally:
        pdf.close()


def _recursos_proprios(origem, senha, pagina):
    """Cópia do PDF em que a página tem recursos só dela.

    O PDFium regrava os recursos (fontes) da página editada; se forem
    compartilhados com outras páginas, elas mudariam junto.
    """
    import io

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject
    r = PdfReader(origem, strict=False)
    if r.is_encrypted:
        r.decrypt(senha or "")
    w = PdfWriter(clone_from=r)
    page = w.pages[pagina]
    res = page.get("/Resources")
    novo = DictionaryObject()
    if res is not None:
        for k, v in res.get_object().items():
            v = v.get_object()
            novo[NameObject(k)] = DictionaryObject(v) if isinstance(v, DictionaryObject) else v
    page[NameObject("/Resources")] = w._add_object(novo)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _wide(s):
    buf = ctypes.create_string_buffer(s.encode("utf-16-le") + b"\0\0")
    return ctypes.cast(buf, c.FPDF_WIDESTRING)  # o cast guarda referência ao buffer
