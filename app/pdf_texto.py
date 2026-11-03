"""Texto do PDF com o PDFium: extrair, buscar e editar o texto original da página."""
import ctypes
import math

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


class _Pedaco:
    """Um objeto de texto do conteúdo da página, no sistema da linha de texto dele."""

    def __init__(self, k, obj, texto, m, bounds, tam, fonte):
        self.k, self.obj, self.texto, self.fonte = k, obj, texto, fonte
        self.m = m
        a, b, cc, d, e, f = m
        nu = math.hypot(a, b) or 1.0
        self.u = (a / nu, b / nu)                      # direção da escrita
        self.n = (-self.u[1], self.u[0])               # "para cima" da linha
        self.ang = round(math.degrees(math.atan2(b, a))) % 360
        self.escala = math.hypot(cc, d) or 1.0
        self.tam_pdf = tam
        self.s = tam * self.escala                     # corpo da letra no espaço da página
        self.base = e * self.n[0] + f * self.n[1]       # altura da linha de base
        l, bb, r, t = bounds
        proj = [x * self.u[0] + y * self.u[1] for x, y in ((l, bb), (r, bb), (l, t), (r, t))]
        x0 = e * self.u[0] + f * self.u[1]
        if self.ang % 90 == 0:
            self.ini, self.fim = min(proj), max(proj)
        else:  # caixa da página não acompanha a inclinação: usa a origem e a largura aproximada
            self.ini, self.fim = x0, x0 + max(proj) - min(proj)
        self.bounds = bounds


def _pedacos(page, tp):
    saida = []
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
        saida.append(_Pedaco(k, obj, texto, _matriz(obj), (l.value, b.value, r.value, t.value), _tamanho(obj),
                             ctypes.cast(c.FPDFTextObj_GetFont(obj), ctypes.c_void_p).value))
    return saida


def _linhas(pedacos):
    """Junta pedaços na mesma linha de base e mesma direção; separa colunas distantes."""
    grupos = {}
    for p in pedacos:
        grupos.setdefault(p.ang, []).append(p)
    linhas = []
    for lista in grupos.values():
        lista.sort(key=lambda p: (-p.base, p.ini))
        abertas = []
        for p in lista:
            alvo = None
            for ln in abertas:
                ref = ln[0]
                if abs(ref.base - p.base) <= 0.3 * max(ref.s, p.s) and 0.55 < p.s / ref.s < 1.8:
                    alvo = ln
                    break
            if alvo is None:
                abertas = [ln for ln in abertas if ln[0].base - p.base <= 2 * ln[0].s]
                alvo = []
                abertas.append(alvo)
                linhas.append(alvo)
            alvo.append(p)
    # dentro da linha: ordem de leitura e quebra em colunas quando o vão é grande
    saida = []
    for ln in linhas:
        ln.sort(key=lambda p: p.ini)
        atual = [ln[0]]
        for p in ln[1:]:
            fim = max(q.fim for q in atual)
            if p.ini - fim > 2.5 * max(p.s, atual[-1].s):
                saida.append(atual)
                atual = []
            atual.append(p)
        saida.append(atual)
    return saida


def _texto_linha(ln):
    partes = []
    fim = None
    for p in ln:
        if partes and fim is not None:
            vao = p.ini - fim
            if vao > 0.18 * p.s and not partes[-1].endswith((" ", "\t")) and not p.texto.startswith(" "):
                partes.append(" ")
        partes.append(p.texto)
        fim = p.fim if fim is None else max(fim, p.fim)
    return "".join(partes).rstrip()


class _Bloco:
    def __init__(self, linha):
        self.linhas = [linha]

    @property
    def pedacos(self):
        return [p for ln in self.linhas for p in ln]

    @property
    def ini(self):
        return min(p.ini for ln in self.linhas for p in ln)

    @property
    def fim(self):
        return max(p.fim for ln in self.linhas for p in ln)

    def corpo(self):
        """Corpo de letra, fonte e objeto que mais aparecem (por número de letras)."""
        pesos = {}
        for p in self.pedacos:
            pesos[(round(p.s, 1), p.fonte)] = pesos.get((round(p.s, 1), p.fonte), 0) + len(p.texto)
        s, fonte = max(pesos, key=pesos.get)
        modelo = max((p for p in self.pedacos if round(p.s, 1) == s and p.fonte == fonte), key=lambda p: len(p.texto))
        return modelo

    def entrelinha(self):
        bases = [ln[0].base for ln in self.linhas]
        difs = sorted(bases[i] - bases[i + 1] for i in range(len(bases) - 1))
        return difs[len(difs) // 2] if difs else self.corpo().s * 1.2

    def alinhamento(self):
        if len(self.linhas) < 2:
            return "esquerda"
        inis = [min(p.ini for p in ln) for ln in self.linhas]
        fins = [max(p.fim for p in ln) for ln in self.linhas]
        tol = self.corpo().s * 0.3
        if max(inis) - min(inis) <= tol:
            return "esquerda"
        meios = [(a + b) / 2 for a, b in zip(inis, fins)]
        if max(meios) - min(meios) <= tol:
            return "centro"
        if max(fins[:-1]) - min(fins[:-1]) <= tol and max(fins) - min(fins) <= tol:
            return "direita"
        return "esquerda"

    def texto(self):
        largura = self.fim - self.ini
        partes = []
        for i, ln in enumerate(self.linhas):
            t = _texto_linha(ln)
            if i:
                anterior = self.linhas[i - 1]
                cheia = max(p.fim for p in anterior) >= self.ini + largura - 3 * anterior[0].s
                partes.append(" " if cheia and len(self.linhas) > 1 else "\n")
            partes.append(t)
        return "".join(partes)


def _blocos(pedacos):
    """Linhas vizinhas, do mesmo tamanho e alinhadas, viram um parágrafo editável."""
    linhas = _linhas(pedacos)
    linhas.sort(key=lambda ln: (ln[0].ang, -ln[0].base, min(p.ini for p in ln)))
    blocos = []
    for ln in linhas:
        ref = max(ln, key=lambda p: len(p.texto))
        ini, fim = min(p.ini for p in ln), max(p.fim for p in ln)
        alvo = None
        for b in reversed(blocos):
            ult = b.linhas[-1]
            u = max(ult, key=lambda p: len(p.texto))
            if u.ang != ref.ang:
                continue
            dy = u.base - ref.base
            if dy <= 0:
                continue
            if dy > 1.75 * max(u.s, ref.s):
                continue
            if not 0.8 < ref.s / u.s < 1.25:
                continue
            if fim < b.ini or ini > b.fim:  # outra coluna
                continue
            if len(b.linhas) >= 2 and abs(dy - b.entrelinha()) > 0.35 * ref.s:
                continue
            alvo = b
            break
        if alvo is None:
            blocos.append(_Bloco(ln))
        else:
            alvo.linhas.append(ln)
    return blocos


def _fonte_real(tp, p):
    """Nome de fonte como está no PDF (o PDFium troca as 14 fontes padrão por substitutas)."""
    l, b, r, t = p.bounds
    k = c.FPDFText_GetCharIndexAtPos(tp.raw, l + min(r - l, p.s) * 0.4, (b + t) / 2, p.s * 0.5, p.s * 0.5)
    nome, flags, peso, _ = _nome_fonte(p.obj)
    if k is not None and k >= 0:
        fl = ctypes.c_int()
        n = c.FPDFText_GetFontInfo(tp.raw, k, None, 0, fl)
        if n > 1:
            buf = ctypes.create_string_buffer(n)
            c.FPDFText_GetFontInfo(tp.raw, k, buf, n, fl)
            nome = buf.value.decode("latin-1", "replace").split("+")[-1]
            flags = fl.value
            peso = c.FPDFText_GetFontWeight(tp.raw, k) or peso
    return nome, flags, peso


def objetos_texto(pdf, i):
    """Blocos de texto editáveis da página: parágrafos montados a partir dos objetos de texto."""
    page = pdf[i]
    geo = geo_pdfium(page)
    tp = page.get_textpage()
    saida = []
    try:
        for b in _blocos(_pedacos(page, tp)):
            ps = b.pedacos
            l = min(p.bounds[0] for p in ps)
            bb = min(p.bounds[1] for p in ps)
            r = max(p.bounds[2] for p in ps)
            t = max(p.bounds[3] for p in ps)
            mod = b.corpo()
            nome, flags, peso = _fonte_real(tp, mod)
            rgb = _cor(mod.obj)
            saida.append({"id": ps[0].k, "ids": sorted(p.k for p in ps), "texto": b.texto(),
                          **_rect_tela(geo, l, bb, r, t), "tamanho": round(mod.s, 2),
                          "fonte": _familia(nome, flags, peso), "cor": "#%02x%02x%02x" % rgb[:3],
                          "linhas": len(b.linhas), "alinhamento": b.alinhamento(),
                          "entrelinha": round(b.entrelinha(), 2)})
    finally:
        tp.close()
        page.close()
    return saida


def _largura(medidor, texto):
    if not texto:
        return 0.0
    c.FPDFText_SetText(medidor, _wide(texto))
    l, b, r, t = (ctypes.c_float() for _ in range(4))
    if not c.FPDFPageObj_GetBounds(medidor, l, b, r, t):
        return 0.0
    return r.value - l.value


def _quebrar(texto, largura, medir):
    """Quebra o texto em linhas que cabem na largura (respeitando as quebras de linha digitadas)."""
    linhas = []
    for par in texto.split("\n"):
        palavras = par.split(" ")
        atual = ""
        for w in palavras:
            tent = w if not atual else atual + " " + w
            if not atual or medir(tent) <= largura:
                atual = tent
            else:
                linhas.append(atual)
                atual = w
        linhas.append(atual)
    return linhas


def editar(origem, senha, destino, pagina, edicoes):
    """Troca o texto de blocos (parágrafos) da página.

    edicoes: [{"ids": [índices dos objetos do bloco], "texto": novo}] (ou {"id": k} de um objeto só).
    O texto novo é refeito no lugar do bloco: mesma posição, largura, entrelinha, alinhamento,
    corpo, cor e inclinação, quebrando as linhas de novo. Usa a fonte do próprio documento quando
    ela tem todas as letras; senão, a fonte padrão mais parecida (Helvetica, Times ou Courier).
    """
    pdf = pdfium.PdfDocument(_recursos_proprios(origem, senha, pagina))
    try:
        page = pdf[pagina]
        tp = page.get_textpage()
        pedacos = _pedacos(page, tp)
        letras = {}
        for p in pedacos:
            letras.setdefault(p.fonte, set()).update(p.texto)
        blocos = _blocos(pedacos)
        por_obj = {p.k: b for b in blocos for p in b.pedacos}
        tarefas = []
        for e in edicoes:
            ids = [int(k) for k in (e.get("ids") or [e.get("id")]) if k is not None]
            alvos = {id(por_obj[k]): por_obj[k] for k in ids if k in por_obj}
            if not alvos:
                raise ValueError("bloco de texto não encontrado (o documento mudou?)")
            novo = str(e.get("texto", ""))[:20000].replace("\r", "")
            for b in alvos.values():
                tarefas.append((b, novo))
                novo = ""  # se a edição pegou mais de um bloco, o texto fica no primeiro
        # tudo o que depende da página original é lido antes de mexer em qualquer objeto
        tarefas = [(b, novo, _fonte_real(tp, b.corpo()), b.texto()) for b, novo in tarefas]
        for b, novo, fonte, antigo in tarefas:
            if novo.strip() == antigo.strip():
                continue
            _refazer_bloco(pdf, page, b, novo, letras, fonte)
        tp.close()
        if not c.FPDFPage_GenerateContent(page.raw):
            raise ValueError("não consegui gravar a página")
        page.close()
        pdf.save(destino)
    finally:
        pdf.close()


def _refazer_bloco(pdf, page, b, novo, letras, fonte):
    mod = b.corpo()
    ps = b.pedacos
    # bloco de um objeto só e a fonte tem as letras: troca direto (preserva tudo)
    if len(ps) == 1 and "\n" not in novo and set(novo) - {" "} <= letras.get(mod.fonte, set()):
        if c.FPDFText_SetText(mod.obj, _wide(novo)):
            return
    def remover_antigos():
        for p in ps:
            c.FPDFPage_RemoveObject(page.raw, p.obj)
            c.FPDFPageObj_Destroy(p.obj)

    if not novo.strip():
        return remover_antigos()
    a, bb, cc, d, _, _ = mod.m
    r, g, bl, al = _cor(mod.obj)
    usar_original = set(novo) - {" ", "\n"} <= letras.get(mod.fonte, set())
    nome, flags, peso = fonte
    padrao = _familia(nome, flags, peso).encode()
    fonte_orig = c.FPDFTextObj_GetFont(mod.obj) if usar_original else None

    def criar():
        if fonte_orig:
            o = c.FPDFPageObj_CreateTextObj(pdf.raw, fonte_orig, ctypes.c_float(mod.tam_pdf))
            if o:
                return o
        o = c.FPDFPageObj_NewTextObj(pdf.raw, padrao, ctypes.c_float(mod.tam_pdf))
        if not o:
            raise ValueError("não consegui criar o texto")
        return o

    m0 = c.FS_MATRIX(a, bb, cc, d, 0, 0)
    medidor = criar()
    c.FPDFPageObj_SetMatrix(medidor, m0)
    try:
        medir = (lambda t: _largura(medidor, t))
        largura = b.fim - b.ini
        if len(b.linhas) == 1:
            largura = float("inf")  # uma linha só: cresce para o lado, como antes
        linhas = _quebrar(novo, largura, medir)
        alin = b.alinhamento()
        passo = b.entrelinha()
        base0 = b.linhas[0][0].base
        ini, fim = b.ini, b.fim
        u, n = mod.u, mod.n
        for i, t in enumerate(linhas):
            if not t.strip():
                continue
            w = medir(t)
            if alin == "centro":
                x = (ini + fim) / 2 - w / 2
            elif alin == "direita":
                x = fim - w
            else:
                x = ini
            y = base0 - i * passo
            o = criar()
            c.FPDFText_SetText(o, _wide(t))
            c.FPDFPageObj_SetFillColor(o, r, g, bl, al)
            c.FPDFPageObj_SetMatrix(o, c.FS_MATRIX(a, bb, cc, d, x * u[0] + y * n[0], x * u[1] + y * n[1]))
            c.FPDFPage_InsertObject(page.raw, o)
    finally:
        c.FPDFPageObj_Destroy(medidor)
    remover_antigos()  # só no fim: a fonte do texto novo pode ser a de um objeto antigo


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
