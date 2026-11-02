"""OCR offline (Tesseract, embutido no app): torna PDFs escaneados pesquisáveis.

O texto reconhecido entra como camada invisível por cima da imagem da página,
na posição de cada palavra: dá para buscar, selecionar e copiar, e a aparência
da página não muda. Nada sai do computador: os modelos de idioma vêm no app.
"""
import os
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject

from pdf_desenho import Geo, Pincel, acrescentar_ao_conteudo, caixa_visivel, largura_texto

TESSDATA = Path(os.environ.get("BRAVO_TESSDATA") or Path(__file__).resolve().parent / "tessdata")
IDIOMAS = {"por": "Português", "eng": "Inglês"}
FONTE = "Helvetica"


def disponivel():
    try:
        import tesserocr  # noqa: F401
    except Exception as e:  # noqa: BLE001  (ex.: macOS antigo sem a biblioteca)
        return False, f"OCR indisponível neste computador ({str(e)[:120]})"
    if not (TESSDATA / "por.traineddata").exists():
        return False, "OCR indisponível: modelos de idioma não encontrados"
    return True, ""


def precisa_ocr(pdf, i):
    page = pdf[i]
    tp = page.get_textpage()
    try:
        return tp.count_chars() < 15
    finally:
        tp.close()
        page.close()


def _orientacao(api, img):
    """Graus (horário) para deixar a página em pé, segundo o Tesseract; 0 se não tiver certeza."""
    try:
        api.SetImage(img)
        d = api.DetectOrientationScript()
    except Exception:  # noqa: BLE001
        return 0
    if not d or d.get("orient_conf", 0) < 2.0:
        return 0
    return (360 - int(d.get("orient_deg", 0))) % 360  # o Tesseract informa no sentido anti-horário


def reconhecer(origem, senha, destino, paginas=None, idiomas="por+eng", dpi=300, progresso=None, girar=True):
    from tesserocr import RIL, PyTessBaseAPI, iterate_level
    langs = "+".join(i for i in str(idiomas).split("+") if i in IDIOMAS) or "por"
    pdf = pdfium.PdfDocument(origem, password=senha or None)
    reader = PdfReader(origem, strict=False)
    if reader.is_encrypted:
        reader.decrypt(senha or "")
    writer = PdfWriter(clone_from=reader)
    if paginas is None:
        paginas = [i for i in range(len(pdf)) if precisa_ocr(pdf, i)]
    escala = dpi / 72
    palavras_total = 0
    try:
        with PyTessBaseAPI(path=str(TESSDATA) + os.sep, lang=langs) as api, \
                PyTessBaseAPI(path=str(TESSDATA) + os.sep, lang="osd", psm=0) as osd:
            for n, i in enumerate(paginas):
                page_w = writer.pages[i]
                r0 = int(page_w.get("/Rotate", 0) or 0) % 360
                pagina = pdf[i]
                img = pagina.render(scale=escala, grayscale=True).to_pil()
                extra = _orientacao(osd, img) if girar else 0
                if extra:
                    img = pagina.render(scale=escala, rotation=extra, grayscale=True).to_pil()
                    r0 = (r0 + extra) % 360
                    page_w[NameObject("/Rotate")] = NumberObject(r0)
                pagina.close()
                geo = Geo(caixa_visivel(page_w), r0)
                api.SetImage(img)
                api.Recognize()
                p = Pincel(writer)
                p_palavras = _palavras(api, RIL, iterate_level, escala)
                for (x0, x1, y_base, tam, texto) in p_palavras:
                    larg = largura_texto(texto, FONTE, tam)
                    if larg <= 0:
                        continue
                    p.texto(x0, y_base, texto, FONTE, tam, modo=3, escala_h=max(10, min(1000, 100 * (x1 - x0) / larg)))
                    palavras_total += 1
                if p.ops:
                    acrescentar_ao_conteudo(writer, page_w, [p.formulario(geo, [0, 0, geo.W, geo.H])], "Ocr")
                if progresso:
                    progresso(n + 1, len(paginas))
    finally:
        pdf.close()
    writer.add_metadata({"/Producer": "Bravo PDF (OCR)"})
    with open(destino, "wb") as f:
        writer.write(f)
    return {"paginas": len(paginas), "palavras": palavras_total}


def _palavras(api, RIL, iterate_level, escala):
    """(x0, x1, linha de base, tamanho, texto) de cada palavra, em pontos na tela."""
    saida = []
    linha_atual = None
    it = api.GetIterator()
    if it is None:
        return saida
    for w in iterate_level(it, RIL.WORD):
        texto = (w.GetUTF8Text(RIL.WORD) or "").strip()
        if not texto:
            continue
        bb = w.BoundingBox(RIL.WORD)
        if not bb:
            continue
        if w.IsAtBeginningOf(RIL.TEXTLINE) or linha_atual is None:
            lb = w.BoundingBox(RIL.TEXTLINE) or bb
            base = w.Baseline(RIL.TEXTLINE)
            altura = (lb[3] - lb[1]) / escala
            y_base = ((base[0][1] + base[1][1]) / 2 / escala) if base else (lb[3] / escala - altura * 0.2)
            linha_atual = (y_base, max(altura * 0.8, 2))
        saida.append((bb[0] / escala, bb[2] / escala, linha_atual[0], linha_atual[1], texto))
    return saida
