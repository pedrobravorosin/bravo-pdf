"""Motor de PDF do Bravo PDF, num processo separado do servidor.

Todo PDF é aberto, desenhado e gravado aqui, nunca no servidor. Assim, um
arquivo malformado (ou feito para atacar o leitor) só derruba este processo,
que não tem internet, tem memória limitada e é reiniciado pelo servidor.

Protocolo (entrada e saída padrão, binário):
  pedido:   uma linha JSON {"cmd", "args", "tam"} seguida de "tam" bytes
  resposta: linhas {"progresso": [feito, total]} (opcionais) e por fim
            {"ok": true, "res": ..., "tam": n} ou {"ok": false, "erro": ...},
            seguida de n bytes
Senhas chegam só por esse canal, nunca pela linha de comando.
"""
import base64
import io
import json
import os
import sys
import zipfile
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blindagem  # noqa: E402

blindagem.ativar()

import pypdfium2 as pdfium  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

Image.MAX_IMAGE_PIXELS = 120_000_000
MAX_PIXELS_RENDER = 40_000_000
SAIDA = sys.stdout.buffer
ENTRADA = sys.stdin.buffer


def limitar():
    try:
        import resource
    except ImportError:  # Windows: o servidor controla o tempo de cada pedido
        return
    for nome, valor in (("RLIMIT_AS", 6 * 1024 ** 3), ("RLIMIT_NOFILE", 256), ("RLIMIT_CORE", 0)):
        lim = getattr(resource, nome, None)
        if lim is None:
            continue
        try:
            resource.setrlimit(lim, (valor, valor))
        except (ValueError, OSError):
            pass  # o macOS não aceita RLIMIT_AS


class Docs:
    """Documentos abertos pelo PDFium (os mais recentes ficam na memória)."""

    def __init__(self, limite=6):
        self.cache = OrderedDict()
        self.limite = limite

    def get(self, info):
        chave = info["caminho"]
        pdf = self.cache.get(chave)
        if pdf is not None:
            self.cache.move_to_end(chave)
            return pdf
        try:
            pdf = pdfium.PdfDocument(chave, password=info.get("senha") or None)
        except pdfium.PdfiumError as e:
            if "password" in str(e).lower() or "senha" in str(e).lower():
                raise SenhaNecessaria() from None
            raise
        self.cache[chave] = pdf
        while len(self.cache) > self.limite:
            _, velho = self.cache.popitem(last=False)
            velho.close()
        return pdf

    def fechar(self, caminho):
        pdf = self.cache.pop(caminho, None)
        if pdf is not None:
            pdf.close()


class SenhaNecessaria(Exception):
    pass


DOCS = Docs()


def progresso(feito, total):
    SAIDA.write(json.dumps({"progresso": [feito, total]}).encode() + b"\n")
    SAIDA.flush()


# ---------------------------------------------------------------- comandos
def c_info(a, _):
    import pdf_assinar
    import pdf_formularios
    from pypdf import PdfReader
    info = a["doc"]
    pdf = DOCS.get(info)
    paginas = []
    for i in range(len(pdf)):
        page = pdf[i]
        w, h = page.get_size()
        paginas.append({"w": round(w, 2), "h": round(h, 2)})
        page.close()
    campos, assinaturas, titulo, erro_extra = [], [], "", ""
    try:
        r = PdfReader(info["caminho"], strict=False)
        if r.is_encrypted:
            r.decrypt(info.get("senha") or "")
        campos = pdf_formularios.listar(r)
        meta = r.metadata or {}
        titulo = str(meta.get("/Title") or "")[:300]
        if any(c["tipo"] == "assinatura" and c.get("assinado") for c in campos):
            assinaturas = pdf_assinar.conferir(info["caminho"], info.get("senha"))
    except Exception as e:  # noqa: BLE001  (o PDFium abriu; o resto é extra)
        erro_extra = str(e)[:200]
    tem_texto = False
    for i in range(min(len(pdf), 5)):
        page = pdf[i]
        tp = page.get_textpage()
        tem_texto = tem_texto or tp.count_chars() > 15
        tp.close()
        page.close()
    return {"paginas": paginas, "campos": [c for c in campos if c["tipo"] != "assinatura"], "assinaturas": assinaturas,
            "titulo": titulo, "tem_texto": tem_texto, "aviso": erro_extra}


def c_render(a, _):
    pdf = DOCS.get(a["doc"])
    i = int(a["p"])
    if not 0 <= i < len(pdf):
        raise ValueError("página inexistente")
    page = pdf[i]
    try:
        w, h = page.get_size()
        escala = min(max(float(a.get("escala", 1)), 0.05), 6)
        if w * h * escala * escala > MAX_PIXELS_RENDER:
            escala = (MAX_PIXELS_RENDER / (w * h)) ** 0.5
        img = page.render(scale=escala, may_draw_forms=False, draw_annots=True).to_pil()
    finally:
        page.close()
    buf = io.BytesIO()
    if a.get("fmt") == "jpeg":
        img.convert("RGB").save(buf, "JPEG", quality=82)
        return {"tipo": "image/jpeg"}, buf.getvalue()
    img.save(buf, "PNG", compress_level=1)
    return {"tipo": "image/png"}, buf.getvalue()


def c_objetos(a, _):
    import pdf_texto
    return pdf_texto.objetos_texto(DOCS.get(a["doc"]), int(a["p"]))


def c_buscar(a, _):
    import pdf_texto
    return pdf_texto.buscar(DOCS.get(a["doc"]), a.get("termo", ""))


def c_texto(a, _):
    import pdf_texto
    pdf = DOCS.get(a["doc"])
    partes = [f"--- Página {i + 1} ---\n{pdf_texto.texto_pagina(pdf, i)}" for i in range(len(pdf))]
    return {}, "\n\n".join(partes).replace("\r\n", "\n").encode("utf-8")


def c_editar_texto(a, _):
    import pdf_texto
    info = a["doc"]
    pdf_texto.editar(info["caminho"], info.get("senha"), a["destino"], int(a["p"]), a["edicoes"])
    return {"ok": True}


def c_ocr(a, _):
    import pdf_ocr
    ok, motivo = pdf_ocr.disponivel()
    if not ok:
        raise ValueError(motivo)
    info = a["doc"]
    pags = a.get("paginas")
    return pdf_ocr.reconhecer(info["caminho"], info.get("senha"), a["destino"],
                              [int(p) for p in pags] if pags is not None else None,
                              a.get("idiomas") or "por+eng", progresso=progresso, girar=a.get("girar", True))


def c_ocr_disponivel(a, _):
    import pdf_ocr
    ok, motivo = pdf_ocr.disponivel()
    return {"ok": ok, "motivo": motivo}


def c_imagem_para_pdf(a, dados):
    im = Image.open(io.BytesIO(dados))
    paginas = []
    try:
        n = getattr(im, "n_frames", 1)
    except Exception:  # noqa: BLE001
        n = 1
    for k in range(min(n, 500)):
        im.seek(k)
        f = ImageOps.exif_transpose(im.copy())
        if f.mode in ("RGBA", "LA", "P"):
            f = f.convert("RGBA")
            fundo = Image.new("RGB", f.size, "white")
            fundo.paste(f, mask=f.getchannel("A"))
            f = fundo
        elif f.mode not in ("RGB", "L", "CMYK"):
            f = f.convert("RGB")
        paginas.append(f)
    dpi = im.info.get("dpi", (150, 150))
    try:
        res = float(dpi[0]) if 50 <= float(dpi[0]) <= 1200 else 150.0
    except (TypeError, ValueError, IndexError):
        res = 150.0
    paginas[0].save(a["destino"], "PDF", save_all=True, append_images=paginas[1:], resolution=res, quality=92)
    return {"paginas": len(paginas)}


def _montar(a):
    import pdf_montar
    return pdf_montar.montar(a["docs"], a["projeto"], progresso)


def c_salvar(a, _):
    import pdf_assinar
    dados = _montar(a)
    assin = a.get("assinatura")
    if assin:
        imagem = None
        if assin.get("imagem"):
            import pdf_anotacoes
            imagem = pdf_anotacoes.imagem_de_dataurl(assin["imagem"])
        try:
            dados = pdf_assinar.assinar(dados, base64.b64decode(assin["pfx"]), assin.get("senha") or "",
                                        int(assin.get("pagina", 0)), assin.get("caixa"), assin.get("motivo") or "",
                                        assin.get("local") or "", assin.get("contato") or "", imagem)
        except pdf_assinar.ErroAssinatura as e:
            raise ValueError(str(e)) from None
    return {"tam_original": None}, dados


def c_certificado(a, _):
    import pdf_assinar
    try:
        _, cert, _ = pdf_assinar.carregar_certificado(base64.b64decode(a["pfx"]), a.get("senha") or "")
    except pdf_assinar.ErroAssinatura as e:
        raise ValueError(str(e)) from None
    return pdf_assinar.descrever(cert)


def c_dividir(a, _):
    import pdf_montar
    dados = _montar(a)
    partes = pdf_montar.dividir(dados, a["grupos"])
    base = a.get("nome") or "documento"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, (g, parte) in enumerate(zip(a["grupos"], partes)):
            ini, fim = int(g[0]) + 1, int(g[-1]) + 1
            nome = f"{base} - páginas {ini}-{fim}.pdf" if fim != ini else f"{base} - página {ini}.pdf"
            z.writestr(f"{i + 1:03d} {nome}", parte)
    return {}, buf.getvalue()


def c_imagens(a, _):
    dados = _montar(a)
    fmt = "PNG" if a.get("formato") == "png" else "JPEG"
    dpi = min(max(int(a.get("dpi") or 150), 36), 600)
    pdf = pdfium.PdfDocument(dados)
    base = a.get("nome") or "documento"
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for i in range(len(pdf)):
                page = pdf[i]
                img = page.render(scale=dpi / 72, may_draw_forms=False).to_pil().convert("RGB")
                page.close()
                b = io.BytesIO()
                img.save(b, fmt, **({"quality": 90} if fmt == "JPEG" else {"compress_level": 6}), dpi=(dpi, dpi))
                z.writestr(f"{base} - página {i + 1:03d}.{fmt.lower().replace('jpeg', 'jpg')}", b.getvalue())
                progresso(i + 1, len(pdf))
    finally:
        pdf.close()
    return {}, buf.getvalue()


def c_comparar(a, _):
    import pdf_comparar
    return pdf_comparar.comparar(a["a"], a["b"])


def c_fechar(a, _):
    DOCS.fechar(a["caminho"])
    return {"ok": True}


COMANDOS = {"info": c_info, "render": c_render, "objetos": c_objetos, "buscar": c_buscar, "texto": c_texto,
            "editar_texto": c_editar_texto, "ocr": c_ocr, "ocr_disponivel": c_ocr_disponivel,
            "imagem_para_pdf": c_imagem_para_pdf, "salvar": c_salvar, "certificado": c_certificado,
            "dividir": c_dividir, "imagens": c_imagens, "comparar": c_comparar, "fechar": c_fechar}


def responder(obj, dados=b""):
    obj["tam"] = len(dados)
    SAIDA.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
    if dados:
        SAIDA.write(dados)
    SAIDA.flush()


def main():
    limitar()
    os.environ["OMP_THREAD_LIMIT"] = os.environ.get("OMP_THREAD_LIMIT", "4")
    while True:
        linha = ENTRADA.readline(10_000_000)
        if not linha:
            return
        try:
            pedido = json.loads(linha)
            tam = int(pedido.get("tam", 0))
            dados = ENTRADA.read(tam) if tam else b""
        except (ValueError, TypeError):
            return  # canal corrompido: o servidor reinicia o motor
        f = COMANDOS.get(pedido.get("cmd"))
        try:
            if f is None:
                raise ValueError("comando desconhecido")
            res = f(pedido.get("args") or {}, dados)
            if isinstance(res, tuple):
                responder({"ok": True, "res": res[0]}, res[1])
            else:
                responder({"ok": True, "res": res})
        except SenhaNecessaria:
            responder({"ok": False, "erro": "Este PDF tem senha.", "senha": True})
        except MemoryError:
            responder({"ok": False, "erro": "O arquivo é grande demais para a memória disponível."})
        except Exception as e:  # noqa: BLE001
            msg = str(e) or e.__class__.__name__
            responder({"ok": False, "erro": msg[:400]})


if __name__ == "__main__":
    main()
