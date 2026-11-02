"""Gera app/requirements.txt com versões fixas e hashes (sha256) de todos os wheels do PyPI.

As versões abaixo têm pacotes prontos para o Python 3.13 em Windows, macOS e Linux
(o tesserocr, só para macOS 15 ou mais novo).
Para atualizar, mude FIXAS, rode este script e rode os testes.
"""
import json
import urllib.request
from pathlib import Path

FIXAS = [
    ("pypdf", "6.21.4"),          # BSD-3: estrutura do PDF (montar, formulários, senha)
    ("pypdfium2", "4.30.0"),      # Apache-2.0/BSD-3 (PDFium do Chrome): ver, buscar, editar texto
    ("pillow", "11.3.0"),         # MIT-CMU: imagens
    ("cryptography", "50.0.2"),   # Apache-2.0/BSD: certificado digital e senha AES-256
    ("cffi", "2.0.0"),
    ("pycparser", "2.23"),
    ("asn1crypto", "1.5.1"),      # MIT: estrutura CMS da assinatura digital
    ("tesserocr", "2.12.0"),      # MIT (Tesseract 5, Apache-2.0, vai junto no pacote): OCR
]

linhas = ["# Gerado por ferramentas/gerar_requirements.py. Não edite à mão.",
          "# Instale com: pip install --require-hashes --only-binary=:all: -r requirements.txt"]
for nome, versao in FIXAS:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{nome}/{versao}/json") as r:
        d = json.load(r)
    hashes = sorted({u["digests"]["sha256"] for u in d["urls"] if u["packagetype"] == "bdist_wheel"})
    linhas.append(f"{nome}=={versao} \\")
    linhas += [f"    --hash=sha256:{h} \\" for h in hashes[:-1]] + [f"    --hash=sha256:{hashes[-1]}"]
destino = Path(__file__).resolve().parent.parent / "app" / "requirements.txt"
destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
print("Gerado", destino)
