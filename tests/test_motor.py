"""Testes do motor de PDF (sem interface). Rode: python -m unittest discover tests

Usa só os PDFs inventados de tests/exemplos. O certificado de teste é criado na hora,
na memória, e não é gravado em lugar nenhum.
"""
import datetime
import io
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
EX = AQUI / "exemplos"
sys.path.insert(0, str(AQUI.parent / "app"))

import pypdfium2 as pdfium  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

import pdf_assinar  # noqa: E402
import pdf_comparar  # noqa: E402
import pdf_montar  # noqa: E402
import pdf_ocr  # noqa: E402
import pdf_texto  # noqa: E402

TEXTO = str(EX / "texto-3-paginas.pdf")
GIRADO = str(EX / "paisagem-girada.pdf")
LETRAS = str(EX / "paragrafo-letras.pdf")
FORM = str(EX / "formulario.pdf")
SEGREDO = "123.456.789-00"


def texto_de(dados):
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(dados)).pages)


def certificado_teste(senha=b"1234"):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
                      x509.NameAttribute(NameOID.COMMON_NAME, "PESSOA DE TESTE:00000000000")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(k.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(agora - datetime.timedelta(days=1))
            .not_valid_after(agora + datetime.timedelta(days=30))
            .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
            .sign(k, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"teste", k, cert, None,
                                                 serialization.BestAvailableEncryption(senha))


class TestMontar(unittest.TestCase):
    def test_juntar_girar_anotar_e_decorar(self):
        docs = {"a": {"caminho": TEXTO}, "g": {"caminho": GIRADO}}
        itens = [{"tipo": "retangulo", "x": 50, "y": 50, "w": 100, "h": 60, "cor": "#ff0000", "espessura": 2},
                 {"tipo": "texto", "x": 100, "y": 300, "w": 300, "h": 40, "linhas": ["Olá, ação!"], "tamanho": 14},
                 {"tipo": "nota", "x": 500, "y": 50, "texto": "comentário"}]
        proj = {"paginas": [{"doc": "g", "p": 0, "itens": itens}, {"doc": "a", "p": 2, "rot": 90},
                            {"doc": "branco", "w": 595, "h": 842}, {"doc": "a", "p": 0}],
                "decor": {"numeracao": {"formato": "Página {n} de {total}", "posicao": "inf-dir"},
                          "marca": {"texto": "CONFIDENCIAL"}},
                "opcoes": {}}
        r = PdfReader(io.BytesIO(pdf_montar.montar(docs, proj)))
        self.assertEqual(len(r.pages), 4)
        self.assertEqual(r.pages[1].rotation % 360, 90)
        tipos = [a.get_object()["/Subtype"] for a in r.pages[0].get("/Annots") or []]
        self.assertIn("/Square", tipos)
        self.assertIn("/FreeText", tipos)
        self.assertIn("Página 4 de 4", r.pages[3].extract_text())
        self.assertIn("CONFIDENCIAL", r.pages[2].extract_text())
        self.assertIn("Página 3", r.pages[1].extract_text())

    def test_incorporar_tira_as_anotacoes_soltas(self):
        docs = {"a": {"caminho": TEXTO}}
        proj = {"paginas": [{"doc": "a", "p": 0, "itens": [{"tipo": "texto", "x": 100, "y": 300, "w": 300, "h": 40,
                                                          "linhas": ["fixo no papel"], "tamanho": 12}]}],
                "opcoes": {"incorporar": True}}
        r = PdfReader(io.BytesIO(pdf_montar.montar(docs, proj)))
        self.assertFalse(r.pages[0].get("/Annots"))
        self.assertIn("fixo no papel", r.pages[0].extract_text())

    def test_tarja_apaga_de_verdade(self):
        docs = {"a": {"caminho": TEXTO}}
        proj = {"paginas": [{"doc": "a", "p": 0, "tarjas": [{"x": 60, "y": 100, "w": 480, "h": 30}]},
                            {"doc": "a", "p": 1}],
                "opcoes": {}}
        dados = pdf_montar.montar(docs, proj)
        self.assertNotIn(SEGREDO, texto_de(dados).split("Página 2")[0])
        # nem no conteúdo bruto da página tarjada (nada escondido por baixo da caixa preta)
        r = PdfReader(io.BytesIO(dados))
        self.assertEqual(r.pages[0].extract_text().strip(), "")
        self.assertIn(SEGREDO, r.pages[1].extract_text())  # página sem tarja continua igual
        self.assertNotIn(b"/Author", dados)

    def test_formulario(self):
        docs = {"f": {"caminho": FORM}}
        proj = {"paginas": [{"doc": "f", "p": 0}],
                "campos": {"f": {"nome": "Maria José", "aceito": "Yes", "plano": "completo", "estado": "MG"}},
                "opcoes": {}}
        campos = PdfReader(io.BytesIO(pdf_montar.montar(docs, proj))).get_fields()
        self.assertEqual(campos["nome"]["/V"], "Maria José")
        self.assertEqual(campos["aceito"]["/V"], "/Yes")
        self.assertEqual(campos["plano"]["/V"], "/completo")
        self.assertEqual(campos["estado"]["/V"], "MG")

    def test_senha_aes256(self):
        docs = {"a": {"caminho": TEXTO}}
        dados = pdf_montar.montar(docs, {"paginas": [{"doc": "a", "p": 0}], "opcoes": {"senha": "s3gr3d0"}})
        r = PdfReader(io.BytesIO(dados))
        self.assertTrue(r.is_encrypted)
        self.assertNotIn(SEGREDO.encode(), dados)
        self.assertTrue(r.decrypt("s3gr3d0"))
        self.assertIn(SEGREDO, r.pages[0].extract_text())

    def test_comprimir_e_dividir(self):
        docs = {"a": {"caminho": TEXTO}}
        proj = {"paginas": [{"doc": "a", "p": i} for i in range(3)], "opcoes": {"comprimir": "forte"}}
        dados = pdf_montar.montar(docs, proj)
        partes = pdf_montar.dividir(dados, [[0], [1, 2]])
        self.assertEqual([len(PdfReader(io.BytesIO(p)).pages) for p in partes], [1, 2])


class TestTexto(unittest.TestCase):
    def test_buscar(self):
        pdf = pdfium.PdfDocument(TEXTO)
        achados = pdf_texto.buscar(pdf, "secreto")
        self.assertEqual(len(achados), 3)
        self.assertTrue(all(a["rects"] for a in achados))

    def test_editar_texto_original(self):
        pdf = pdfium.PdfDocument(TEXTO)
        objs = pdf_texto.objetos_texto(pdf, 0)
        alvo = next(o for o in objs if "Texto comum" in o["texto"])
        pdf.close()
        with tempfile.TemporaryDirectory() as d:
            destino = str(Path(d) / "ed.pdf")
            pdf_texto.editar(TEXTO, None, destino, 0, [{"id": alvo["id"], "texto": "Linha nova, com acentuação"}])
            t = PdfReader(destino).pages[0].extract_text()
        self.assertIn("Linha nova, com acentuação", t)
        self.assertNotIn("Texto comum", t)

    def test_texto_em_pedacos_vira_paragrafo(self):
        pdf = pdfium.PdfDocument(LETRAS)
        blocos = pdf_texto.objetos_texto(pdf, 0)
        pdf.close()
        textos = [b["texto"] for b in blocos]
        self.assertEqual(textos[0], "Proposta comercial")  # título escrito letra por letra
        self.assertGreater(len(blocos[0]["ids"]), 10)
        self.assertTrue(textos[1].startswith("Este contrato foi gerado"))  # parágrafo palavra por palavra
        self.assertEqual(blocos[1]["linhas"], 4)
        self.assertNotIn("\n", textos[1])
        self.assertIn("Valor total: R$ 1.000,00", textos)  # colunas separadas continuam separadas
        self.assertIn("Prazo: 30 dias", textos)

    def test_editar_paragrafo_inteiro(self):
        pdf = pdfium.PdfDocument(LETRAS)
        blocos = pdf_texto.objetos_texto(pdf, 0)
        pdf.close()
        longo = "Texto refeito pelo Bravo PDF com acentuação: " + "palavra " * 40
        with tempfile.TemporaryDirectory() as d:
            destino = str(Path(d) / "ed.pdf")
            pdf_texto.editar(LETRAS, None, destino, 0, [{"ids": blocos[1]["ids"], "texto": longo.strip()},
                                                        {"ids": blocos[0]["ids"], "texto": "Proposta técnica"}])
            pdf = pdfium.PdfDocument(destino)
            novos = pdf_texto.objetos_texto(pdf, 0)
            pdf.close()
        self.assertEqual(novos[0]["texto"], "Proposta técnica")
        par = next(b for b in novos if b["texto"].startswith("Texto refeito"))
        self.assertGreaterEqual(par["linhas"], 3)  # quebrou em linhas de novo
        self.assertLessEqual(par["x"] + par["w"], blocos[1]["x"] + blocos[1]["w"] + 2)  # dentro da largura original
        self.assertAlmostEqual(par["x"], blocos[1]["x"], delta=2)
        self.assertIn("Prazo: 30 dias", [b["texto"] for b in novos])


class TestComparar(unittest.TestCase):
    def test_acha_a_mudanca(self):
        with tempfile.TemporaryDirectory() as d:
            novo = str(Path(d) / "novo.pdf")
            pdf = pdfium.PdfDocument(TEXTO)
            alvo = next(o for o in pdf_texto.objetos_texto(pdf, 1) if "Texto comum" in o["texto"])
            pdf.close()
            pdf_texto.editar(TEXTO, None, novo, 1, [{"id": alvo["id"], "texto": "Texto diferente"}])
            res = pdf_comparar.comparar({"caminho": TEXTO}, {"caminho": novo})
        self.assertTrue(res["mudancas"])
        self.assertGreater(res["semelhanca"], 0.8)

    def test_iguais(self):
        res = pdf_comparar.comparar({"caminho": TEXTO}, {"caminho": TEXTO})
        self.assertEqual(res["mudancas"], [])


@unittest.skipUnless(pdf_ocr.disponivel()[0], "OCR indisponível neste computador")
class TestOCR(unittest.TestCase):
    def test_pagina_escaneada_vira_pesquisavel(self):
        img = pdfium.PdfDocument(TEXTO)[0].render(scale=200 / 72).to_pil().convert("L")
        with tempfile.TemporaryDirectory() as d:
            scan, saida = Path(d) / "scan.pdf", Path(d) / "ocr.pdf"
            img.save(scan, "PDF", resolution=200)
            self.assertEqual(PdfReader(scan).pages[0].extract_text().strip(), "")
            pdf_ocr.reconhecer(str(scan), None, str(saida))
            t = PdfReader(saida).pages[0].extract_text()
        self.assertIn("secreto", t)
        self.assertIn("Contrato", t)


class TestAssinaturaDigital(unittest.TestCase):
    def test_assina_confere_e_detecta_alteracao(self):
        pfx = certificado_teste()
        with self.assertRaises(Exception):
            pdf_assinar.carregar_certificado(pfx, "errada")
        original = Path(TEXTO).read_bytes()
        assinado = pdf_assinar.assinar(original, pfx, "1234", pagina=0,
                                       caixa={"x": 340, "y": 740, "w": 220, "h": 64}, motivo="Teste", local="Recife")
        self.assertTrue(assinado.startswith(original))  # atualização incremental: o original fica intacto
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.pdf"
            p.write_bytes(assinado)
            res = pdf_assinar.conferir(str(p))
            self.assertEqual(len(res), 1)
            self.assertTrue(res[0]["integra"])
            self.assertTrue(res[0]["documento_todo"])
            # segunda assinatura por cima da primeira: as duas continuam íntegras
            p.write_bytes(pdf_assinar.assinar(assinado, pfx, "1234"))
            res = pdf_assinar.conferir(str(p))
            self.assertEqual([r["integra"] for r in res], [True, True])
            # um byte mudado dentro da parte assinada: a assinatura acusa
            ruim = bytearray(assinado)
            i = ruim.index(b"Contrato")
            ruim[i] = ord("K")
            p.write_bytes(bytes(ruim))
            res = pdf_assinar.conferir(str(p))
            self.assertFalse(res[0]["integra"])


class TestDocumentoComSenha(unittest.TestCase):
    def test_abre_com_senha(self):
        w = PdfWriter(clone_from=TEXTO)
        w.encrypt("abc", algorithm="AES-256")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.pdf"
            with open(p, "wb") as f:
                w.write(f)
            with self.assertRaises(pdf_montar.ErroProjeto):
                pdf_montar.montar({"a": {"caminho": str(p), "senha": "x"}}, {"paginas": [{"doc": "a", "p": 0}], "opcoes": {}})
            dados = pdf_montar.montar({"a": {"caminho": str(p), "senha": "abc"}}, {"paginas": [{"doc": "a", "p": 0}], "opcoes": {}})
        self.assertIn("Página 1", texto_de(dados))


if __name__ == "__main__":
    unittest.main()
