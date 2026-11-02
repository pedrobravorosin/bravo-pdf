"""Gera os PDFs de exemplo usados nos testes (conteúdo inventado).

Uso: python tests/gerar_exemplos.py   (precisa do reportlab só para gerar; o app não usa)
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

D = Path(__file__).resolve().parent / "exemplos"


def texto():
    c = canvas.Canvas(str(D / "texto-3-paginas.pdf"), pagesize=A4)
    c.setTitle("Contrato de exemplo")
    c.setAuthor("Fulano de Tal")
    for i in range(1, 4):
        c.setFont("Helvetica-Bold", 20)
        c.drawString(72, 760, f"Página {i} - Contrato de exemplo")
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, "Cláusula: o número secreto é 123.456.789-00 e não deve vazar.")
        c.drawString(72, 700, "Texto comum de ação, atenção e coração para testar acentos.")
        c.rect(72, 500, 200, 100)
        c.showPage()
    c.save()


def girado():
    c = canvas.Canvas(str(D / "paisagem-girada.pdf"), pagesize=landscape(A4))
    c.setFont("Helvetica", 14)
    c.drawString(72, 500, "Página em paisagem")
    c.showPage()
    c.save()
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(D / "paisagem-girada.pdf")
    w = PdfWriter(clone_from=r)
    w.pages[0].rotate(90)
    w.write(D / "paisagem-girada.pdf")


def formulario():
    c = canvas.Canvas(str(D / "formulario.pdf"), pagesize=A4)
    f = c.acroForm
    c.setFont("Helvetica", 12)
    c.drawString(72, 760, "Nome:")
    f.textfield(name="nome", x=140, y=750, width=300, height=20, borderWidth=1)
    c.drawString(72, 720, "Aceito os termos:")
    f.checkbox(name="aceito", x=200, y=715, size=16, buttonStyle="check")
    c.drawString(72, 680, "Plano:")
    f.radio(name="plano", value="basico", x=140, y=675, selected=True, size=14)
    f.radio(name="plano", value="completo", x=240, y=675, selected=False, size=14)
    c.drawString(72, 640, "Estado:")
    f.choice(name="estado", x=140, y=630, width=120, height=20, options=["SP", "RJ", "MG"], value="SP")
    c.showPage()
    c.save()


if __name__ == "__main__":
    D.mkdir(exist_ok=True)
    texto()
    girado()
    formulario()
    print("ok")
