"""Formulários (AcroForm) e achatamento de anotações."""
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from pdf_desenho import Geo, acrescentar_ao_conteudo

TEXTO_MULTILINHA = 1 << 12
BOTAO_RADIO = 1 << 15
BOTAO_ACAO = 1 << 16
LISTA_COMBO = 1 << 17
SOMENTE_LEITURA = 1


def _herdado(d, chave):
    vistos = 0
    while d is not None and vistos < 50:
        if chave in d:
            return d[chave]
        d = d.get("/Parent")
        d = d.get_object() if d is not None else None
        vistos += 1
    return None


def nome_completo(w):
    partes, d, vistos = [], w, 0
    while d is not None and vistos < 50:
        if "/T" in d:
            partes.append(str(d["/T"]))
        d = d.get("/Parent")
        d = d.get_object() if d is not None else None
        vistos += 1
    return ".".join(reversed(partes))


def _estado_on(w):
    ap = w.get("/AP")
    n = ap.get_object().get("/N") if ap is not None else None
    n = n.get_object() if n is not None else None
    if isinstance(n, DictionaryObject):
        for k in n:
            if k != "/Off":
                return k
    return "/Yes"


def listar(reader):
    """Campos do formulário, com a posição de cada widget em coordenadas de tela."""
    campos = []
    if "/AcroForm" not in reader.trailer["/Root"]:
        return campos
    for pi, page in enumerate(reader.pages):
        annots = page.get("/Annots")
        if annots is None:
            continue
        geo = Geo.da_pagina(page)
        for ref in annots.get_object():
            w = ref.get_object()
            if not isinstance(w, DictionaryObject) or w.get("/Subtype") != "/Widget":
                continue
            ft = _herdado(w, "/FT")
            ff = int(_herdado(w, "/Ff") or 0)
            if int(w.get("/F", 0)) & 2:
                continue
            try:
                rect = geo.retangulo_tela([float(v) for v in w["/Rect"]])
            except (KeyError, ValueError, TypeError):
                continue
            nome = nome_completo(w)
            if not nome:
                continue
            v = _herdado(w, "/V")
            item = {"nome": nome, "pagina": pi, "x": rect[0], "y": rect[1], "w": rect[2] - rect[0], "h": rect[3] - rect[1],
                    "somente_leitura": bool(ff & SOMENTE_LEITURA)}
            if ft == "/Tx":
                item.update(tipo="texto", valor=str(v) if v is not None else "", multilinha=bool(ff & TEXTO_MULTILINHA))
                ml = _herdado(w, "/MaxLen")
                if ml is not None:
                    item["max"] = int(ml)
            elif ft == "/Btn":
                if ff & BOTAO_ACAO:
                    continue
                on = _estado_on(w)
                item.update(tipo="radio" if ff & BOTAO_RADIO else "caixa", on=on[1:], valor=str(v)[1:] if v else "Off")
            elif ft == "/Ch":
                opts = []
                for o in (_herdado(w, "/Opt") or []):
                    o = o.get_object() if hasattr(o, "get_object") else o
                    if isinstance(o, (list, ArrayObject)):
                        opts.append([str(o[0]), str(o[1])])
                    else:
                        opts.append([str(o), str(o)])
                if isinstance(v, ArrayObject):
                    v = v[0] if v else ""
                item.update(tipo="lista", valor=str(v) if v is not None else "", opcoes=opts, combo=bool(ff & LISTA_COMBO))
            elif ft == "/Sig":
                item.update(tipo="assinatura", assinado=v is not None)
            else:
                continue
            campos.append(item)
    return campos


def preencher(writer, valores):
    """Preenche os campos. valores: {nome completo: texto | 'Off' | nome do estado ligado}."""
    if not valores:
        return
    textos = {}
    for page in writer.pages:
        annots = page.get("/Annots")
        if annots is None:
            continue
        for ref in annots.get_object():
            w = ref.get_object()
            if not isinstance(w, DictionaryObject) or w.get("/Subtype") != "/Widget":
                continue
            nome = nome_completo(w)
            if nome not in valores:
                continue
            ft = _herdado(w, "/FT")
            ff = int(_herdado(w, "/Ff") or 0)
            if ff & SOMENTE_LEITURA:
                continue
            valor = valores[nome]
            if ft == "/Btn":
                on = _estado_on(w)
                ligado = str(valor) == on[1:]
                w[NameObject("/AS")] = NameObject(on if ligado else "/Off")
                campo = w if "/T" in w else w["/Parent"].get_object()
                if ligado or not (ff & BOTAO_RADIO):
                    campo[NameObject("/V")] = NameObject(on if ligado else "/Off")
            elif ft in ("/Tx", "/Ch"):
                textos[nome] = str(valor)[:20000]
    if textos:
        for page in writer.pages:
            try:
                writer.update_page_form_field_values(page, textos, auto_regenerate=False)
            except Exception:  # noqa: BLE001  (campo sem fonte, etc.: preenche o valor mesmo assim)
                _valor_cru(page, textos)
        writer.set_need_appearances_writer(True)


def _valor_cru(page, textos):
    for ref in page.get("/Annots") or []:
        w = ref.get_object()
        nome = nome_completo(w)
        if nome in textos:
            campo = w if "/T" in w else w["/Parent"].get_object()
            campo[NameObject("/V")] = TextStringObject(textos[nome])


def _aparencia(a):
    ap = a.get("/AP")
    if ap is None:
        return None
    n = ap.get_object().get("/N")
    if n is None:
        return None
    n = n.get_object()
    if isinstance(n, DictionaryObject) and "/BBox" not in n:
        estado = a.get("/AS")
        if estado is None or estado not in n:
            return None
        return n.raw_get(estado)
    return ap.get_object().raw_get("/N")


def achatar_pagina(writer, page, manter_links=True):
    """Incorpora ao conteúdo todas as anotações com aparência (e os campos de formulário)."""
    annots = page.get("/Annots")
    if annots is None:
        return set()
    sobra, desenhos, widgets = ArrayObject(), [], set()
    for ref in annots.get_object():
        a = ref.get_object()
        if not isinstance(a, DictionaryObject):
            continue
        sub = a.get("/Subtype")
        if sub == "/Link" and manter_links:
            sobra.append(ref)
            continue
        if sub == "/Popup":
            continue
        flags = int(a.get("/F", 0))
        if sub == "/Widget":
            widgets.add(id(a))
        if flags & (2 | 32):  # oculta / não visível
            continue
        ref_ap = _aparencia(a)
        if ref_ap is None:
            continue
        form = ref_ap.get_object()
        try:
            bb = [float(v) for v in form["/BBox"]]
            m = [float(v) for v in form.get("/Matrix", [1, 0, 0, 1, 0, 0])]
            r = [float(v) for v in a["/Rect"]]
        except (KeyError, ValueError, TypeError):
            continue
        cantos = [(bb[0], bb[1]), (bb[2], bb[1]), (bb[0], bb[3]), (bb[2], bb[3])]
        tx = [(m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]) for x, y in cantos]
        x0, y0 = min(p[0] for p in tx), min(p[1] for p in tx)
        x1, y1 = max(p[0] for p in tx), max(p[1] for p in tx)
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            continue
        rx0, ry0, rx1, ry1 = min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])
        sx, sy = (rx1 - rx0) / (x1 - x0), (ry1 - ry0) / (y1 - y0)
        desenhos.append((ref_ap, [sx, 0, 0, sy, rx0 - x0 * sx, ry0 - y0 * sy]))
    _desenhar_com_matriz(writer, page, desenhos)
    if sobra:
        page[NameObject("/Annots")] = sobra
    elif "/Annots" in page:
        del page["/Annots"]
    return widgets


def _desenhar_com_matriz(writer, page, desenhos):
    if not desenhos:
        return
    from pypdf.generic import DecodedStreamObject, FloatObject
    embrulhos = []
    for ref_ap, mat in desenhos:
        s = DecodedStreamObject()
        s.set_data(b"q /A Do Q")
        s.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                  NameObject("/BBox"): ArrayObject([FloatObject(v) for v in (-1e5, -1e5, 1e5, 1e5)]),
                  NameObject("/Matrix"): ArrayObject([FloatObject(round(v, 6)) for v in mat]),
                  NameObject("/Resources"): DictionaryObject({NameObject("/XObject"): DictionaryObject(
                      {NameObject("/A"): ref_ap if hasattr(ref_ap, "idnum") else writer._add_object(ref_ap)})})})
        embrulhos.append(writer._add_object(s))
    acrescentar_ao_conteudo(writer, page, embrulhos, "Ach")


def achatar_documento(writer):
    """Achata anotações e formulário de todas as páginas e remove o formulário."""
    for page in writer.pages:
        achatar_pagina(writer, page)
    raiz = writer._root_object
    if "/AcroForm" in raiz:
        del raiz["/AcroForm"]
