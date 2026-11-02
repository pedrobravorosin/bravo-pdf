"""Marca d'água, numeração de páginas, cabeçalho e rodapé (incorporados à página)."""
import math
import time

from pdf_desenho import FONTES, Pincel, cor, largura_texto, num

POSICOES = {"sup-esq", "sup-centro", "sup-dir", "inf-esq", "inf-centro", "inf-dir"}


def _fonte(cfg, padrao_negrito=False):
    fam = cfg.get("fonte") if cfg.get("fonte") in ("helv", "times", "cour") else "helv"
    return FONTES[(fam, bool(cfg.get("negrito", padrao_negrito)), bool(cfg.get("italico")))]


def _tam(cfg, padrao):
    try:
        v = float(cfg.get("tamanho", padrao))
        return min(max(v, 4), 300) if math.isfinite(v) else padrao
    except (TypeError, ValueError):
        return padrao


def preencher_modelo(modelo, n, total, arquivo=""):
    return (str(modelo)[:300].replace("{n}", str(n)).replace("{total}", str(total))
            .replace("{data}", time.strftime("%d/%m/%Y")).replace("{arquivo}", arquivo))


def _linha(p, texto, onde, geo, fonte, tam, c, margem):
    larg = largura_texto(texto, fonte, tam)
    lado = onde.split("-")[1]
    x = margem if lado == "esq" else (geo.W - margem - larg if lado == "dir" else (geo.W - larg) / 2)
    y = margem + tam * 0.8 if onde.startswith("sup") else geo.H - margem
    p.texto(x, y, texto, fonte, tam, c)


def decorar(writer, page, geo, decor, indice, total, arquivo=""):
    """Devolve a lista de XObjects a incorporar nesta página (índice começa em 0)."""
    xobjs = []
    marca = decor.get("marca")
    if marca and _alvo(marca, indice) and (marca.get("texto") or "").strip():
        p = Pincel(writer)
        fonte, tam = _fonte(marca, True), _tam(marca, 60)
        op = min(max(float(marca.get("opacidade", 0.2) or 0.2), 0.03), 1)
        ang = float(marca.get("angulo", 45) or 0)
        p += f"/{p.opacidade(op, op)} gs"
        texto = str(marca["texto"])[:200]
        larg = largura_texto(texto, fonte, tam)
        if marca.get("ajustar", True):  # cabe na diagonal da página
            caber = math.hypot(geo.W, geo.H) * 0.8 if ang % 180 else geo.W * 0.9
            if larg > caber:
                tam *= caber / larg
                larg = caber
        a = math.radians(ang)
        u, v = (math.cos(a), -math.sin(a)), (-math.sin(a), -math.cos(a))
        cx, cy = geo.W / 2, geo.H / 2
        x = cx - larg / 2 * u[0] - 0.35 * tam * v[0]
        y = cy - larg / 2 * u[1] - 0.35 * tam * v[1]
        p.texto(x, y, texto, fonte, tam, cor(marca.get("cor"), (0.8, 0.1, 0.1)), angulo=ang)
        xobjs.append(p.formulario(geo, [0, 0, geo.W, geo.H]))

    for chave, padrao in (("cabecalho", "sup"), ("rodape", "inf")):
        cfg = decor.get(chave)
        if not cfg or not _alvo(cfg, indice):
            continue
        p = Pincel(writer)
        fonte, tam = _fonte(cfg), _tam(cfg, 9)
        c = cor(cfg.get("cor"), (0.3, 0.3, 0.3))
        margem = float(cfg.get("margem", 24) or 24)
        n = indice + int(cfg.get("inicio", 1) or 1)
        for lado in ("esq", "centro", "dir"):
            t = cfg.get(lado)
            if t:
                _linha(p, preencher_modelo(t, n, total, arquivo), f"{padrao}-{lado}", geo, fonte, tam, c, margem)
        if p.ops:
            xobjs.append(p.formulario(geo, [0, 0, geo.W, geo.H]))

    numer = decor.get("numeracao")
    if numer and _alvo(numer, indice):
        p = Pincel(writer)
        onde = numer.get("posicao") if numer.get("posicao") in POSICOES else "inf-centro"
        inicio = int(numer.get("inicio", 1) or 1)
        n = indice + inicio
        texto = preencher_modelo(numer.get("formato") or "{n}", n, total + inicio - 1, arquivo)
        _linha(p, texto, onde, geo, _fonte(numer), _tam(numer, 10), cor(numer.get("cor"), (0.2, 0.2, 0.2)),
               float(numer.get("margem", 28) or 28))
        xobjs.append(p.formulario(geo, [0, 0, geo.W, geo.H]))
    return xobjs


def _alvo(cfg, indice):
    alvo = cfg.get("paginas")
    if alvo is None:
        return True
    try:
        return indice in set(int(i) for i in alvo)
    except (TypeError, ValueError):
        return True


__all__ = ["decorar", "num"]
