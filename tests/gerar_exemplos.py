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


PARAGRAFO = ("Este contrato foi gerado por um programa que escreve cada palavra separada, "
             "como fazem muitos editores de texto ao exportar PDF. O Bravo PDF precisa juntar "
             "as palavras em linhas e as linhas em parágrafos para editar tudo de uma vez.")


def paragrafo_letras():
    """Texto quebrado em pedaços: título letra por letra e parágrafo palavra por palavra."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonte = "Helvetica"
    ttf = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if ttf.exists():  # fonte embutida parcial, como num PDF exportado do Word
        pdfmetrics.registerFont(TTFont("DejaVu", str(ttf)))
        fonte = "DejaVu"
    c = canvas.Canvas(str(D / "paragrafo-letras.pdf"), pagesize=A4)
    x = 72
    c.setFont("Helvetica-Bold", 22)
    for letra in "Proposta comercial":
        c.drawString(x, 760, letra)
        x += pdfmetrics.stringWidth(letra, "Helvetica-Bold", 22)
    c.setFont(fonte, 11)
    largura, y, linha = 440, 720, []
    def escrever(palavras, y):
        x = 72
        for p in palavras:
            c.drawString(x, y, p)
            x += pdfmetrics.stringWidth(p + " ", fonte, 11)
    for p in PARAGRAFO.split():
        if pdfmetrics.stringWidth(" ".join(linha + [p]), fonte, 11) > largura:
            escrever(linha, y)
            y -= 15
            linha = []
        linha.append(p)
    escrever(linha, y)
    c.setFont("Helvetica", 11)
    c.drawString(72, y - 50, "Valor total: R$ 1.000,00")
    c.drawString(380, y - 50, "Prazo: 30 dias")
    c.drawCentredString(297.5, 120, "Assinatura do cliente")
    c.save()


if __name__ == "__main__":
    D.mkdir(exist_ok=True)
    texto()
    girado()
    formulario()
    paragrafo_letras()
    print("ok")
