"""Assinatura digital com certificado (PAdES, ETSI.CAdES.detached), sem internet.

- Certificado A1 (.pfx/.p12), como os da ICP-Brasil: a chave é lida na memória,
  usada e descartada; o arquivo e a senha não são guardados.
- A assinatura entra como atualização incremental: o conteúdo anterior do PDF
  fica intacto e qualquer mudança posterior é detectada pelos leitores.
- Também confere assinaturas existentes (integridade e quem assinou).

Usa só cryptography e asn1crypto (estruturas CMS).
"""
import binascii
import datetime
import hashlib
import io
import re

from asn1crypto import algos, cms, core
from asn1crypto import x509 as ax509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, ByteStringObject, DictionaryObject, FloatObject, NameObject,
                           NumberObject,
                           TextStringObject)

from pdf_desenho import FONTES, Geo, Pincel, caixa_visivel, largura_texto

TAM_ASSINATURA = 24576  # bytes reservados para o CMS (cabe cadeia de certificados longa)
MARCA_FAIXA = [1111111111, 2222222222, 3333333333]


# ---- ESS signing-certificate-v2 (RFC 5035), exigido pelo PAdES ----
class _IssuerSerial(core.Sequence):
    _fields = [("issuer", ax509.GeneralNames), ("serial_number", core.Integer)]


class _ESSCertIDv2(core.Sequence):
    _fields = [("hash_algorithm", algos.DigestAlgorithm, {"default": {"algorithm": "sha256"}}),
               ("cert_hash", core.OctetString), ("issuer_serial", _IssuerSerial, {"optional": True})]


class _ESSCertIDsv2(core.SequenceOf):
    _child_spec = _ESSCertIDv2


class _SigningCertificateV2(core.Sequence):
    _fields = [("certs", _ESSCertIDsv2)]


class _SetOfSigningCertificateV2(core.SetOf):
    _child_spec = _SigningCertificateV2


cms.CMSAttributeType._map.setdefault("1.2.840.113549.1.9.16.2.47", "signing_certificate_v2")
cms.CMSAttributeType._reverse_map = None
cms.CMSAttribute._oid_specs.setdefault("signing_certificate_v2", _SetOfSigningCertificateV2)


class ErroAssinatura(Exception):
    pass


def carregar_certificado(pfx, senha):
    try:
        chave, cert, cadeia = pkcs12.load_key_and_certificates(pfx, (senha or "").encode("utf-8"))
    except ValueError:
        raise ErroAssinatura("Senha do certificado incorreta ou arquivo inválido.") from None
    if chave is None or cert is None:
        raise ErroAssinatura("O arquivo não tem a chave privada do certificado.")
    if not isinstance(chave, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise ErroAssinatura("Tipo de chave não suportado (use RSA ou ECDSA).")
    return chave, cert, list(cadeia or [])


def _nome(cert):
    try:
        cn = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    except IndexError:
        cn = cert.subject.rfc4514_string()
    return str(cn)


def descrever(cert):
    cn = _nome(cert)
    nome, _, doc = cn.partition(":")  # padrão ICP-Brasil: "NOME:CPF" ou "EMPRESA:CNPJ"
    emissor = cert.issuer.rfc4514_string()
    agora = datetime.datetime.now(datetime.timezone.utc)
    return {"nome": nome.strip() or cn, "documento": _mascarar(doc.strip()), "emissor": emissor[:300],
            "icp_brasil": "ICP-Brasil" in emissor,
            "valido_de": cert.not_valid_before_utc.strftime("%d/%m/%Y"),
            "valido_ate": cert.not_valid_after_utc.strftime("%d/%m/%Y"),
            "vencido": not (cert.not_valid_before_utc <= agora <= cert.not_valid_after_utc)}


def _mascarar(doc):
    d = re.sub(r"\D", "", doc)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.***/****-{d[12:]}"
    return ""


def _aparencia(writer, geo, x, y, w, h, info, motivo, data, imagem=None):
    p = Pincel(writer)
    p += f"0.761 0.255 0.047 RG 0.8 w {x + 0.4:.2f} {y + 0.4:.2f} {w - 0.8:.2f} {h - 0.8:.2f} re S"
    col = x + 6
    if imagem is not None:
        lado = min(h - 8, w * 0.4)
        iw, ih = imagem.size
        esc = min(lado / ih, (w * 0.42) / iw)
        nome = p.imagem(imagem)
        dw, dh = iw * esc, ih * esc
        p += f"q {dw:.2f} 0 0 {-dh:.2f} {x + 5:.2f} {y + (h + dh) / 2:.2f} cm /{nome} Do Q"
        col = x + 10 + dw
    linhas = [("Assinado digitalmente por", False), (info["nome"], True)]
    if info.get("documento"):
        linhas.append((info["documento"], False))
    linhas.append((f"Data: {data}", False))
    if motivo:
        linhas.append((f"Motivo: {motivo}", False))
    largura = max(10, x + w - 4 - col)
    tam = min(h / (len(linhas) * 1.25 + 0.4), 10)
    for nome_l, neg in linhas:
        f = FONTES[("helv", neg, False)]
        if largura_texto(nome_l, f, tam) > largura:
            tam = max(3.5, tam * largura / largura_texto(nome_l, f, tam))
    yb = y + (h - len(linhas) * tam * 1.25) / 2 + tam
    for t, neg in linhas:
        p.texto(col, yb, t, FONTES[("helv", neg, False)], tam, (0.1, 0.1, 0.12))
        yb += tam * 1.25
    return p.formulario(geo, [x, y, x + w, y + h])


def assinar(pdf, pfx, senha_pfx, pagina=0, caixa=None, motivo="", local="", contato="", imagem=None):
    """Assina o PDF (bytes) e devolve os bytes assinados.
    caixa: {"x","y","w","h"} em coordenadas de tela da página, ou None para assinatura invisível."""
    chave, cert, cadeia = carregar_certificado(pfx, senha_pfx)
    info = descrever(cert)
    if info["vencido"]:
        raise ErroAssinatura(f"O certificado não está válido hoje (validade {info['valido_de']} a {info['valido_ate']}).")
    reader = PdfReader(io.BytesIO(pdf), strict=False)
    if reader.is_encrypted:
        raise ErroAssinatura("Para assinar digitalmente, salve o PDF sem senha.")
    writer = PdfWriter(io.BytesIO(pdf), incremental=True)
    # Números de objeto novos precisam ficar acima de todos os já usados no arquivo
    # (inclusive tabelas de referência em fluxo que não entram no /Size).
    maior = max((int(n) for n in re.findall(rb"(?<![0-9])(\d{1,8})\s+\d{1,5}\s+obj\b", pdf)), default=0)
    while len(writer._objects) < maior:
        writer._objects.append(None)  # vaga reservada: não é gravada
    if not 0 <= pagina < len(writer.pages):
        pagina = 0
    page = writer.pages[pagina]
    agora = datetime.datetime.now().astimezone()
    data_pdf = agora.strftime("D:%Y%m%d%H%M%S") + agora.strftime("%z")[:3] + "'" + agora.strftime("%z")[3:] + "'"

    v = DictionaryObject({
        NameObject("/Type"): NameObject("/Sig"), NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
        NameObject("/SubFilter"): NameObject("/ETSI.CAdES.detached"),
        NameObject("/ByteRange"): ArrayObject([NumberObject(0)] + [NumberObject(n) for n in MARCA_FAIXA]),
        NameObject("/Contents"): ByteStringObject(b"\0" * TAM_ASSINATURA),
        NameObject("/M"): TextStringObject(data_pdf), NameObject("/Name"): TextStringObject(info["nome"][:200])})
    for k, t in (("/Reason", motivo), ("/Location", local), ("/ContactInfo", contato)):
        if t:
            v[NameObject(k)] = TextStringObject(str(t)[:300])
    v_ref = writer._add_object(v)

    raiz = writer._root_object
    form = raiz.get("/AcroForm")
    if form is None:
        form = DictionaryObject({NameObject("/Fields"): ArrayObject()})
        raiz[NameObject("/AcroForm")] = writer._add_object(form)
    form = form.get_object()
    campos = form.get("/Fields")
    if campos is None:
        campos = ArrayObject()
        form[NameObject("/Fields")] = campos
    campos = campos.get_object()
    existentes = {str(f.get_object().get("/T")) for f in campos}
    n = 1
    while f"Assinatura{n}" in existentes:
        n += 1

    widget = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Sig"), NameObject("/T"): TextStringObject(f"Assinatura{n}"),
        NameObject("/V"): v_ref, NameObject("/F"): NumberObject(132), NameObject("/P"): page.indirect_reference})
    geo = Geo(caixa_visivel(page), page.get("/Rotate", 0) or 0)
    if caixa:
        x, y, w, h = (float(caixa[k]) for k in ("x", "y", "w", "h"))
        w, h = max(w, 40), max(h, 18)
        ap = _aparencia(writer, geo, x, y, w, h, info, motivo, agora.strftime("%d/%m/%Y %H:%M"), imagem)
        widget[NameObject("/Rect")] = ArrayObject([FloatObject(round(c, 3)) for c in geo.retangulo_pdf(x, y, x + w, y + h)])
        widget[NameObject("/AP")] = DictionaryObject({NameObject("/N"): ap})
    else:
        widget[NameObject("/Rect")] = ArrayObject([FloatObject(0)] * 4)
    w_ref = writer._add_object(widget)
    campos.append(w_ref)
    form[NameObject("/SigFlags")] = NumberObject(3)
    annots = page.get("/Annots")
    if annots is None:
        page[NameObject("/Annots")] = ArrayObject([w_ref])
    else:
        annots.get_object().append(w_ref)

    buf = io.BytesIO()
    writer.write(buf)
    dados = bytearray(buf.getvalue())
    return bytes(_preencher(dados, chave, cert, cadeia))


def _preencher(dados, chave, cert, cadeia):
    marca = re.compile(rb"/ByteRange\s*\[\s*0\s+1111111111\s+2222222222\s+3333333333\s*\]")
    m = None
    for m in marca.finditer(dados):
        pass
    if m is None:
        raise ErroAssinatura("falha interna ao preparar a assinatura")
    alvo = b"<" + b"0" * (TAM_ASSINATURA * 2) + b">"
    ini = bytes(dados).rfind(alvo)
    if ini < 0:
        raise ErroAssinatura("falha interna ao preparar a assinatura")
    fim = ini + len(alvo)
    faixa = [0, ini, fim, len(dados) - fim]
    texto = ("/ByteRange [" + " ".join(str(v) for v in faixa) + "]").encode()
    if len(texto) > m.end() - m.start():
        raise ErroAssinatura("falha interna ao preparar a assinatura")
    dados[m.start():m.end()] = texto.ljust(m.end() - m.start(), b" ")
    resumo = hashlib.sha256(bytes(dados[:ini]) + bytes(dados[fim:])).digest()
    assinatura = _cms(resumo, chave, cert, cadeia)
    hexa = binascii.hexlify(assinatura)
    if len(hexa) > TAM_ASSINATURA * 2:
        raise ErroAssinatura("certificado com cadeia grande demais")
    dados[ini + 1:ini + 1 + len(hexa)] = hexa
    return dados


def _cms(resumo, chave, cert, cadeia):
    der = cert.public_bytes(serialization.Encoding.DER)
    c_asn = ax509.Certificate.load(der)
    atributos = cms.CMSAttributes([
        cms.CMSAttribute({"type": "content_type", "values": ["data"]}),
        cms.CMSAttribute({"type": "message_digest", "values": [resumo]}),
        cms.CMSAttribute({"type": "signing_certificate_v2", "values": [{"certs": [{
            "cert_hash": hashlib.sha256(der).digest(),
            "issuer_serial": {"issuer": [ax509.GeneralName({"directory_name": c_asn.issuer})],
                              "serial_number": c_asn.serial_number}}]}]}),
    ])
    a_assinar = atributos.dump()
    if isinstance(chave, rsa.RSAPrivateKey):
        sig = chave.sign(a_assinar, padding.PKCS1v15(), hashes.SHA256())
        alg = {"algorithm": "rsassa_pkcs1v15"}
    else:
        sig = chave.sign(a_assinar, ec.ECDSA(hashes.SHA256()))
        alg = {"algorithm": "sha256_ecdsa"}
    outros = [ax509.Certificate.load(x.public_bytes(serialization.Encoding.DER)) for x in cadeia]
    signer = cms.SignerInfo({
        "version": "v1",
        "sid": cms.SignerIdentifier({"issuer_and_serial_number": {"issuer": c_asn.issuer,
                                                                  "serial_number": c_asn.serial_number}}),
        "digest_algorithm": {"algorithm": "sha256"}, "signed_attrs": atributos,
        "signature_algorithm": alg, "signature": sig})
    sd = cms.SignedData({"version": "v1", "digest_algorithms": [{"algorithm": "sha256"}],
                         "encap_content_info": {"content_type": "data"},
                         "certificates": [c_asn] + outros, "signer_infos": [signer]})
    return cms.ContentInfo({"content_type": "signed_data", "content": sd}).dump()


# ---------------------------------------------------------------- conferir assinaturas
def conferir(caminho, senha=None):
    """Lista as assinaturas digitais do PDF e confere a integridade de cada uma."""
    with open(caminho, "rb") as f:
        dados = f.read()
    reader = PdfReader(io.BytesIO(dados), strict=False)
    if reader.is_encrypted:
        reader.decrypt(senha or "")
    saida = []
    form = reader.trailer["/Root"].get("/AcroForm")
    if form is None:
        return saida
    pilha = list(form.get_object().get("/Fields") or [])
    vistos = 0
    while pilha and vistos < 5000:
        vistos += 1
        f = pilha.pop(0).get_object()
        pilha.extend(f.get("/Kids") or [])
        if f.get("/FT") != "/Sig" or "/V" not in f:
            continue
        v = f["/V"].get_object()
        item = {"campo": str(f.get("/T", "")), "nome": str(v.get("/Name", "")), "motivo": str(v.get("/Reason", "")),
                "data": _data_pdf(str(v.get("/M", ""))), "integra": False, "documento_todo": False}
        try:
            faixa = [int(n) for n in v["/ByteRange"]]
            conteudo = bytes(v["/Contents"])
            assinado = dados[faixa[0]:faixa[0] + faixa[1]] + dados[faixa[2]:faixa[2] + faixa[3]]
            item.update(_verificar(conteudo, assinado))
            item["documento_todo"] = faixa[2] + faixa[3] >= len(dados.rstrip(b"\r\n\0 ")) - 2
        except Exception as e:  # noqa: BLE001
            item["erro"] = str(e)[:200]
        saida.append(item)
    return saida


def _data_pdf(s):
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", s)
    if not m:
        return ""
    return f"{m[3]}/{m[2]}/{m[1]}" + (f" {m[4]}:{m[5]}" if m[4] and m[5] else "")


def _verificar(conteudo, assinado):
    ci = cms.ContentInfo.load(conteudo.rstrip(b"\0") if conteudo.endswith(b"\0\0") else conteudo, strict=False)
    sd = ci["content"]
    si = sd["signer_infos"][0]
    alg_resumo = si["digest_algorithm"]["algorithm"].native
    h = hashlib.new({"sha1": "sha1", "sha256": "sha256", "sha384": "sha384", "sha512": "sha512"}[alg_resumo])
    h.update(assinado)
    resumo = h.digest()
    sid = si["sid"].chosen
    cert = None
    for c in sd["certificates"]:
        c = c.chosen
        if isinstance(sid, cms.IssuerAndSerialNumber):
            if c.serial_number == sid["serial_number"].native and c.issuer == sid["issuer"]:
                cert = c
                break
        elif c.key_identifier == sid.native:
            cert = c
            break
    if cert is None:
        return {"integra": False, "erro": "certificado do assinante não está no arquivo"}
    xc = x509.load_der_x509_certificate(cert.dump())
    info = descrever(xc)
    ok_resumo = True
    attrs = si["signed_attrs"]
    if attrs.native is not None and len(attrs):
        md = [a["values"][0].native for a in attrs if a["type"].native == "message_digest"]
        ok_resumo = bool(md) and md[0] == resumo
        dados_sig = attrs.untag().dump()
        dados_sig = b"\x31" + dados_sig[1:]
    else:
        dados_sig = assinado
    sig = si["signature"].native
    alg_hash = getattr(hashes, alg_resumo.upper())()
    pub = xc.public_key()
    try:
        if isinstance(pub, rsa.RSAPublicKey):
            if si["signature_algorithm"]["algorithm"].native == "rsassa_pss":
                pub.verify(sig, dados_sig, padding.PSS(padding.MGF1(alg_hash), padding.PSS.AUTO), alg_hash)
            else:
                pub.verify(sig, dados_sig, padding.PKCS1v15(), alg_hash)
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(sig, dados_sig, ec.ECDSA(alg_hash))
        else:
            return {"integra": False, "erro": "algoritmo não suportado", **_resumo(info)}
        ok_sig = True
    except Exception:  # noqa: BLE001
        ok_sig = False
    return {"integra": ok_resumo and ok_sig, **_resumo(info)}


def _resumo(info):
    return {"assinante": info["nome"], "documento_assinante": info["documento"], "emissor": info["emissor"],
            "icp_brasil": info["icp_brasil"], "valido_ate": info["valido_ate"]}
