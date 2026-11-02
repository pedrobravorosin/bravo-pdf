"""Monta o PDF final a partir do projeto do app.

Projeto (vindo da interface):
  {"paginas": [{"doc": id | "branco", "p": índice, "rot": 0|90|180|270, "w", "h" (só branco),
                "itens": [anotações...], "tarjas": [{"x","y","w","h"}...]}],
   "campos": {doc: {nome: valor}},
   "decor": {"marca": {...}, "numeracao": {...}, "cabecalho": {...}, "rodape": {...}},
   "opcoes": {"incorporar": bool, "comprimir": "nao"|"leve"|"media"|"forte", "senha": str,
              "limpar_metadados": bool, "titulo": str, "autor": str, "nome": str}}
docs: {id: {"caminho": str, "senha": str|None}}
"""
import io
import math

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject, StreamObject,
                           TextStringObject)

import pdf_anotacoes
import pdf_formularios
import pdf_paginas
from pdf_desenho import Geo, acrescentar_ao_conteudo, caixa_visivel

DPI_TARJA = 200
NIVEIS = {"leve": (2600, 85), "media": (1700, 70), "forte": (1150, 52)}


class ErroProjeto(Exception):
    pass


def abrir_leitor(info):
    r = PdfReader(info["caminho"], strict=False)
    if r.is_encrypted:
        if not r.decrypt(info.get("senha") or ""):
            raise ErroProjeto("senha incorreta")
    return r


def _leitores(docs, projeto):
    usados = {pg["doc"] for pg in projeto["paginas"] if pg.get("doc") != "branco"}
    campos = projeto.get("campos") or {}
    leitores = {}
    for d in usados:
        if d not in docs:
            raise ErroProjeto("documento não está aberto")
        r = abrir_leitor(docs[d])
        if campos.get(d):
            w = PdfWriter(clone_from=r)
            pdf_formularios.preencher(w, campos[d])
            buf = io.BytesIO()
            w.write(buf)
            r = PdfReader(buf, strict=False)
        leitores[d] = r
    return leitores


def _em_ordem(projeto, leitores):
    pgs = projeto["paginas"]
    if len(leitores) != 1 or any(pg.get("doc") == "branco" for pg in pgs):
        return None
    d = next(iter(leitores))
    if [pg["p"] for pg in pgs] == list(range(len(leitores[d].pages))):
        return d
    return None


def _rot(v):
    try:
        r = int(v) % 360
    except (TypeError, ValueError):
        return 0
    return r if r in (0, 90, 180, 270) else 0


def montar(docs, projeto, progresso=None):
    pgs = projeto.get("paginas") or []
    if not pgs:
        raise ErroProjeto("nenhuma página")
    opc = projeto.get("opcoes") or {}
    decor = projeto.get("decor") or {}
    leitores = _leitores(docs, projeto)

    unico = _em_ordem(projeto, leitores)
    if unico:
        writer = PdfWriter(clone_from=leitores[unico])
    else:
        writer = PdfWriter()
        i = 0
        while i < len(pgs):  # junta sequências seguidas do mesmo documento numa só cópia
            pg = pgs[i]
            if pg.get("doc") == "branco":
                w = min(max(float(pg.get("w") or 595.28), 36), 14400)
                h = min(max(float(pg.get("h") or 841.89), 36), 14400)
                writer.add_blank_page(w, h)
                i += 1
                continue
            r = leitores[pg["doc"]]
            idx = [pg["p"]]
            while i + len(idx) < len(pgs) and pgs[i + len(idx)].get("doc") == pg["doc"]:
                idx.append(pgs[i + len(idx)]["p"])
            for p in idx:
                if not (0 <= int(p) < len(r.pages)):
                    raise ErroProjeto("página inexistente")
            writer.append(r, pages=[int(p) for p in idx], import_outline=False)
            i += len(idx)
    if len(writer.pages) != len(pgs):
        raise ErroProjeto("falha ao montar as páginas")

    total = len(pgs)
    incorporar = bool(opc.get("incorporar"))
    autor = str(opc.get("autor") or "")[:100]
    finais, tarjas = [], {}
    for k, (page, pg) in enumerate(zip(writer.pages, pgs)):
        r0 = _rot(page.get("/Rotate", 0))
        if r0 != page.get("/Rotate", 0):
            page[NameObject("/Rotate")] = NumberObject(r0)
        geo = Geo(caixa_visivel(page), r0)
        itens = pg.get("itens") or []
        if itens:
            pdf_anotacoes.aplicar(writer, page, geo, itens, incorporar, autor)
        rot_final = (r0 + _rot(pg.get("rot"))) % 360
        if decor:
            xos = pdf_paginas.decorar(writer, page, Geo(caixa_visivel(page), rot_final), decor, k, total,
                                      str(opc.get("nome") or ""))
            acrescentar_ao_conteudo(writer, page, xos, "Dc")
        if pg.get("tarjas"):
            tarjas[k] = pg["tarjas"]
        finais.append(rot_final)
        if progresso:
            progresso(k + 1, total)

    if incorporar:
        pdf_formularios.achatar_documento(writer)

    if tarjas:
        writer = _aplicar_tarjas(writer, tarjas, finais)
    for k, page in enumerate(writer.pages):
        if k not in tarjas:
            page[NameObject("/Rotate")] = NumberObject(finais[k])

    _metadados(writer, opc, limpar=bool(opc.get("limpar_metadados")) or bool(tarjas))
    nivel = opc.get("comprimir")
    if nivel in NIVEIS:
        comprimir(writer, nivel)
    writer.compress_identical_objects(remove_duplicates=nivel in NIVEIS, remove_unreferenced=True)
    senha = str(opc.get("senha") or "")
    if senha:
        writer.encrypt(user_password=senha, owner_password=None, algorithm="AES-256")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _metadados(writer, opc, limpar):
    raiz = writer._root_object
    if limpar:
        if "/Metadata" in raiz:
            del raiz["/Metadata"]
        info = writer._info
        if info is not None:
            obj = info.get_object()
            for k in list(obj.keys()):
                del obj[k]
        for page in writer.pages:
            for k in ("/PieceInfo", "/Metadata", "/Thumb"):
                if k in page:
                    del page[k]
    meta = {"/Producer": "Bravo PDF"}
    if opc.get("titulo"):
        meta["/Title"] = str(opc["titulo"])[:500]
    if opc.get("autor") and not limpar:
        meta["/Author"] = str(opc["autor"])[:200]
    writer.add_metadata(meta)


# ---------------------------------------------------------------- tarja definitiva
def _aplicar_tarjas(writer, tarjas, finais):
    """Páginas com tarja viram imagem: o que estava sob a tarja deixa de existir no arquivo."""
    import pypdfium2 as pdfium
    from PIL import ImageDraw

    for k in tarjas:  # tudo da página entra na imagem: anotações e campos também
        pdf_formularios.achatar_pagina(writer, writer.pages[k], manter_links=False)
    buf = io.BytesIO()
    writer.write(buf)
    dados = buf.getvalue()
    pdf = pdfium.PdfDocument(dados)
    novo = PdfWriter(clone_from=PdfReader(io.BytesIO(dados), strict=False))
    escala = DPI_TARJA / 72
    removidos = set()
    for k, lista in tarjas.items():
        pagina = pdf[k]
        img = pagina.render(scale=escala, draw_annots=True, may_draw_forms=False).to_pil().convert("RGB")
        pagina.close()
        d = ImageDraw.Draw(img)
        for t in lista:
            try:
                x, y, w, h = (float(t[c]) for c in ("x", "y", "w", "h"))
            except (KeyError, TypeError, ValueError):
                continue
            if not all(map(math.isfinite, (x, y, w, h))):
                continue
            d.rectangle([math.floor(x * escala), math.floor(y * escala),
                         math.ceil((x + w) * escala), math.ceil((y + h) * escala)], fill=(0, 0, 0))
        page = novo.pages[k]
        geo = Geo.da_pagina(page)
        for ref in page.get("/Annots") or []:
            removidos.add(id(ref.get_object()))
        _trocar_por_imagem(novo, page, img, geo.W, geo.H, _rot(finais[k] - geo.rot))
    pdf.close()
    _remover_campos_orfaos(novo)
    return novo


def _trocar_por_imagem(writer, page, img, W, H, rot):
    from pdf_desenho import imagem_xobject
    ref = imagem_xobject(writer, img, qualidade=88)
    s = StreamObject()
    s._data = f"q {W:.3f} 0 0 {H:.3f} 0 0 cm /Img Do Q".encode()
    for k in ("/Annots", "/Contents", "/Resources", "/CropBox", "/BleedBox", "/TrimBox", "/ArtBox",
              "/Group", "/PieceInfo", "/Thumb", "/StructParents", "/Tabs", "/AA", "/B", "/Metadata"):
        if k in page:
            del page[k]
    page[NameObject("/MediaBox")] = ArrayObject([FloatObject(0), FloatObject(0), FloatObject(W), FloatObject(H)])
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Img"): ref})})
    page[NameObject("/Contents")] = writer._add_object(s)
    page[NameObject("/Rotate")] = NumberObject(rot % 360)


def _remover_campos_orfaos(writer):
    """Tira do formulário os campos cujos widgets não estão mais em nenhuma página."""
    raiz = writer._root_object
    if "/AcroForm" not in raiz:
        return
    vivos = set()
    for page in writer.pages:
        for ref in page.get("/Annots") or []:
            vivos.add(id(ref.get_object()))

    def tem_widget_vivo(campo, prof=0):
        if prof > 30:
            return False
        if id(campo) in vivos:
            return True
        return any(tem_widget_vivo(k.get_object(), prof + 1) for k in campo.get("/Kids") or [])

    form = raiz["/AcroForm"].get_object()
    campos = ArrayObject([f for f in form.get("/Fields") or [] if tem_widget_vivo(f.get_object())])
    if campos:
        form[NameObject("/Fields")] = campos
    else:
        del raiz["/AcroForm"]
    # A estrutura de acessibilidade pode repetir o texto das páginas: some junto.
    if "/StructTreeRoot" in raiz:
        del raiz["/StructTreeRoot"]
    if "/MarkInfo" in raiz:
        del raiz["/MarkInfo"]


# ---------------------------------------------------------------- compressão
def comprimir(writer, nivel):
    from PIL import Image
    lado_max, qualidade = NIVEIS[nivel]
    feitos = set()
    for page in writer.pages:
        try:
            page.compress_content_streams(level=9)
        except Exception:  # noqa: BLE001
            pass
        res = page.get("/Resources")
        xo = res.get_object().get("/XObject") if res is not None else None
        if xo is None:
            continue
        for nome in list(xo.get_object().keys()):
            ref = xo.get_object().raw_get(nome)
            if not hasattr(ref, "idnum") or ref.idnum in feitos:
                continue
            feitos.add(ref.idnum)
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Image" or obj.get("/ImageMask") or int(obj.get("/BitsPerComponent", 8)) != 8:
                continue
            try:
                original = len(obj._data)
                from pypdf.generic._image_xobject import _xobj_to_image
                _, _, im = _xobj_to_image(obj)
            except Exception:  # noqa: BLE001
                continue
            if im.mode not in ("RGB", "L", "CMYK"):
                if im.mode in ("RGBA", "LA", "P", "1"):
                    im = im.convert("RGB")
                else:
                    continue
            if max(im.size) > lado_max:
                im.thumbnail((lado_max, lado_max), Image.LANCZOS)
            novo = io.BytesIO()
            if im.mode == "CMYK":
                im = im.convert("RGB")
            im.save(novo, "JPEG", quality=qualidade, optimize=True, progressive=False)
            dados = novo.getvalue()
            if len(dados) >= original * 0.9:
                continue
            s = StreamObject()
            s._data = dados
            s.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                      NameObject("/Width"): NumberObject(im.size[0]), NameObject("/Height"): NumberObject(im.size[1]),
                      NameObject("/ColorSpace"): NameObject("/DeviceGray" if im.mode == "L" else "/DeviceRGB"),
                      NameObject("/BitsPerComponent"): NumberObject(8), NameObject("/Filter"): NameObject("/DCTDecode")})
            for k in ("/SMask", "/Interpolate", "/Intent"):
                if k in obj:
                    s[NameObject(k)] = obj.raw_get(k)
            writer._objects[ref.idnum - 1] = s
            s.indirect_reference = ref


def dividir(dados, grupos):
    """grupos: listas de índices de página. Devolve uma lista de PDFs (bytes)."""
    r = PdfReader(io.BytesIO(dados), strict=False)
    saida = []
    for g in grupos:
        w = PdfWriter()
        w.append(r, pages=[int(i) for i in g], import_outline=False)
        w.add_metadata({"/Producer": "Bravo PDF"})
        buf = io.BytesIO()
        w.write(buf)
        saida.append(buf.getvalue())
    return saida


__all__ = ["montar", "dividir", "comprimir", "ErroProjeto", "TextStringObject"]
