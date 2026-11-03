#!/usr/bin/env python3
"""Servidor local do Bravo PDF.

Segurança (a mesma do Bravo Finance):
- Escuta só em 127.0.0.1, numa porta livre escolhida a cada abertura.
- Sem internet: o bloqueio de rede (blindagem.py) recusa qualquer conexão para
  fora do computador, e a página não carrega nada de fora (CSP).
- Chave por sessão: quem abre o app recebe uma chave de uso único e troca por um
  cookie de sessão. Sem ele, nada é entregue, nem para outros programas ou
  usuários do mesmo computador.
- Os PDFs são abertos e gravados pelo motor (motor.py), num processo separado,
  sem internet e com memória limitada. O servidor nunca interpreta um PDF.
- Os documentos abertos ficam numa pasta temporária só do usuário, apagada ao fechar.

Uso pelo app: python -I -s server.py --janela
  Escreve "BRAVO-PDF <porta> <chave>" e desliga quando a entrada padrão fecha.
  Pela entrada padrão, o app pode mandar "ABRIR <caminho>" (abrir com dois cliques).
"""
import base64
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import blindagem  # noqa: E402

blindagem.ativar()

NOME = "Bravo PDF"
VERSAO = "0.0.0"


def pasta_padrao():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / NOME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "bravo-pdf"


DATA = Path(os.environ.get("BRAVO_DADOS") or pasta_padrao())
SESSAO_DIR = DATA / "sessao"
ENTRADA_DIR = DATA / "entrada"  # pedidos de "abrir arquivo" de uma segunda abertura do app
PREFS = DATA / "preferencias.json"
PUBLIC = BASE / "public"
FAVICON = BASE / "icone" / "favicon.png"
MAX_ARQUIVO = 500 * 1024 * 1024
MAX_JSON = 120 * 1024 * 1024
LOCK = threading.Lock()
ULTIMO_USO = time.monotonic()
PORT = 0
CHAVE_ENTRADA = secrets.token_urlsafe(32)
SESSAO = secrets.token_urlsafe(32)
ENTRADA_USADA = False
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; font-src 'self'; worker-src 'none'; object-src 'none'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")
IMAGENS = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*", b"RIFF")
PROGRESSO = {}  # tarefa -> [feito, total]
PENDENTES = []  # documentos abertos fora da janela (dois cliques), à espera da página


# ---------------------------------------------------------------- motor
class Motor:
    """Um processo motor.py; reiniciado se travar, cair ou passar do tempo."""

    def __init__(self, nome):
        self.nome = nome
        self.proc = None
        self.lock = threading.Lock()

    def _ligar(self):
        extra = {"creationflags": 0x08000000} if os.name == "nt" else {}
        python = sys.executable
        if os.name == "nt" and python.lower().endswith("pythonw.exe"):
            python = python[:-5] + ".exe"
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG",
                                                             "LOCALAPPDATA", "USERPROFILE", "BRAVO_TESSDATA")}
        env["OMP_THREAD_LIMIT"] = "4"
        self.proc = subprocess.Popen([python, "-I", "-s", str(BASE / "motor.py")], cwd=str(BASE), env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **extra)

    def parar(self):
        p, self.proc = self.proc, None
        if p is not None:
            try:
                p.kill()
                p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass

    def pedir(self, cmd, args=None, dados=b"", tempo=120, tarefa=None):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._ligar()
            proc = self.proc
            relogio = threading.Timer(tempo, self.parar)
            relogio.start()
            try:
                cab = json.dumps({"cmd": cmd, "args": args or {}, "tam": len(dados)}, ensure_ascii=False).encode()
                proc.stdin.write(cab + b"\n")
                if dados:
                    proc.stdin.write(dados)
                proc.stdin.flush()
                while True:
                    linha = proc.stdout.readline(50_000_000)
                    if not linha:
                        raise ErroMotor("A operação demorou demais ou o arquivo travou o leitor. Tente de novo.")
                    r = json.loads(linha)
                    if "progresso" in r:
                        if tarefa:
                            PROGRESSO[tarefa] = r["progresso"]
                        continue
                    corpo = proc.stdout.read(int(r.get("tam", 0))) if r.get("tam") else b""
                    return r, corpo
            except (OSError, ValueError) as e:
                self.parar()
                raise ErroMotor("O leitor de PDF parou de forma inesperada. Tente de novo.") from e
            finally:
                relogio.cancel()
                if tarefa:
                    PROGRESSO.pop(tarefa, None)


class ErroMotor(Exception):
    pass


VISUAL = Motor("visual")    # desenhar páginas, buscar
TRABALHO = Motor("trabalho")  # salvar, OCR, comparar, converter


def motor_ok(motor, cmd, args=None, dados=b"", tempo=120, tarefa=None):
    r, corpo = motor.pedir(cmd, args, dados, tempo, tarefa)
    if not r.get("ok"):
        raise ErroPedido(401 if r.get("senha") else 422, r.get("erro") or "falhou", r.get("senha", False))
    return r.get("res"), corpo


class ErroPedido(Exception):
    def __init__(self, codigo, msg, senha=False):
        super().__init__(msg)
        self.codigo, self.msg, self.senha = codigo, msg, senha


# ---------------------------------------------------------------- documentos da sessão
DOCS = {}  # id -> {"caminho", "senha", "nome"}


def preparar_pastas():
    for d in (DATA, ENTRADA_DIR):
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
    shutil.rmtree(SESSAO_DIR, ignore_errors=True)  # restos de uma sessão que não fechou direito
    SESSAO_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def novo_arquivo(sufixo=".pdf"):
    did = secrets.token_hex(8)
    return did, SESSAO_DIR / f"{did}{sufixo}"


def gravar_privado(caminho, dados):
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(dados)


def nome_limpo(nome):
    nome = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", str(nome or "")).strip()[:180]
    return nome or "documento.pdf"


def abrir_bytes(dados, nome, senha=None):
    """Registra um arquivo (PDF ou imagem) na sessão e devolve o resumo para a página."""
    if dados.startswith(IMAGENS) or (dados[:4] == b"RIFF" and dados[8:12] == b"WEBP"):
        did, destino = novo_arquivo()
        _, img = novo_arquivo(".img")
        gravar_privado(img, dados)
        try:
            motor_ok(TRABALHO, "imagem_para_pdf", {"destino": str(destino)}, dados, tempo=180)
        finally:
            img.unlink(missing_ok=True)
        nome = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", nome_limpo(nome)) + ".pdf"
    elif b"%PDF" in dados[:1024]:
        did, destino = novo_arquivo()
        gravar_privado(destino, dados)
    else:
        raise ErroPedido(400, "Este arquivo não é um PDF nem uma imagem.")
    return registrar(did, destino, nome_limpo(nome), senha)


def registrar(did, caminho, nome, senha):
    info = {"caminho": str(caminho), "senha": senha}
    try:
        res, _ = motor_ok(VISUAL, "info", {"doc": info}, tempo=120)
    except ErroPedido:
        Path(caminho).unlink(missing_ok=True)
        raise
    with LOCK:
        DOCS[did] = {**info, "nome": nome}
    return {"id": did, "nome": nome, "protegido": bool(senha), **res}


def doc(did):
    d = DOCS.get(str(did))
    if d is None:
        raise ErroPedido(404, "Documento não está aberto.")
    return d


def doc_motor(did):
    d = doc(did)
    return {"caminho": d["caminho"], "senha": d["senha"]}


def nova_versao(did, cmd, args, tempo, tarefa=None):
    """Operações que mudam o documento (editar texto, OCR) criam uma versão nova; a antiga continua
    disponível para desfazer."""
    d = doc(did)
    nid, destino = novo_arquivo()
    res, _ = motor_ok(TRABALHO, cmd, {**args, "doc": doc_motor(did), "destino": str(destino)}, tempo=tempo,
                      tarefa=tarefa)
    resumo = registrar(nid, destino, d["nome"], None)  # a cópia nova sai sem senha (só existe na sessão)
    return {**resumo, "resultado": res, "origem": did}


def abrir_caminho(caminho):
    """Pedido de abrir um arquivo do computador (dois cliques ou "Abrir com")."""
    p = Path(caminho)
    try:
        if not p.is_file() or p.stat().st_size > MAX_ARQUIVO:
            return
        dados = p.read_bytes()
    except OSError:
        return
    try:
        resumo = abrir_bytes(dados, p.name)
    except ErroPedido as e:
        resumo = {"erro": e.msg, "senha": e.senha, "nome": p.name}
        if e.senha:  # guarda os bytes para a página perguntar a senha
            did, destino = novo_arquivo()
            gravar_privado(destino, dados)
            resumo["pendente"] = did
            with LOCK:
                DOCS[did] = {"caminho": str(destino), "senha": None, "nome": nome_limpo(p.name), "trancado": True}
    with LOCK:
        PENDENTES.append(resumo)


PAGINA_SEM_ACESSO = """<!doctype html><meta charset="utf-8"><title>Bravo PDF</title>
<body style="font:16px system-ui;margin:0;display:flex;height:100vh;align-items:center;justify-content:center;color:#555">
<p>Abra o Bravo PDF pelo ícone do aplicativo.</p></body>"""


def ler_prefs():
    try:
        d = json.loads(PREFS.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def gravar_json(path, obj):
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(path)


def docs_do_projeto(projeto):
    usados = {str(p.get("doc")) for p in projeto.get("paginas") or [] if p.get("doc") != "branco"}
    return {d: doc_motor(d) for d in usados}


class H(BaseHTTPRequestHandler):
    server_version = "BravoPDF"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # não registra URLs nem nomes de arquivos
        pass

    # ---- verificações
    def _host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def _sessao_ok(self):
        try:
            c = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return False
        m = c.get("bp")
        return m is not None and hmac.compare_digest(m.value.encode(), SESSAO.encode())

    def _mesma_origem(self):
        origem = self.headers.get("Origin")
        if origem is not None and origem not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return False
        return self.headers.get("Sec-Fetch-Site") in (None, "same-origin")

    def _liberado(self, gravar=False):
        global ULTIMO_USO
        if not (self._host_ok() and self._sessao_ok()):
            return False
        if gravar and not (self._mesma_origem() and self.headers.get("X-Bravo") == "1"):
            return False
        ULTIMO_USO = time.monotonic()
        return True

    def _corpo(self, maximo):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n <= 0 or n > maximo:
            raise ErroPedido(413, f"Arquivo vazio ou grande demais (máximo {maximo // 1024 // 1024} MB).")
        return self.rfile.read(n)

    def _json(self, maximo=MAX_JSON):
        try:
            d = json.loads(self._corpo(maximo))
        except ValueError:
            raise ErroPedido(400, "pedido inválido") from None
        if not isinstance(d, dict):
            raise ErroPedido(400, "pedido inválido")
        return d

    # ---- respostas
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _err(self, code, msg, **extra):
        self._send(code, {"erro": msg, **extra})

    def _negado(self):
        if self.command == "GET" and not urlparse(self.path).path.startswith("/api/"):
            return self._send(403, PAGINA_SEM_ACESSO, "text/html; charset=utf-8")
        return self._err(403, "não permitido")

    def _executar(self, f):
        try:
            f()
        except ErroPedido as e:
            self._err(e.codigo, e.msg, senha=e.senha)
        except ErroMotor as e:
            self._err(503, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001  (sem detalhes: podem conter caminhos)
            try:
                self._err(500, "Erro inesperado. Tente de novo.")
            except OSError:
                pass

    # ---- GET
    def do_GET(self):
        global ENTRADA_USADA
        if not self._host_ok():
            return self._err(403, "não permitido")
        u = urlparse(self.path)
        if u.path == "/entrar":
            chave = (parse_qs(u.query).get("t") or [""])[0]
            with LOCK:
                valida = not ENTRADA_USADA and hmac.compare_digest(chave.encode(), CHAVE_ENTRADA.encode())
                if valida:
                    ENTRADA_USADA = True
            if not valida:
                return self._negado()
            return self._send(303, b"", "text/plain", {
                "Location": "/", "Set-Cookie": f"bp={SESSAO}; HttpOnly; SameSite=Strict; Path=/"})
        if not self._liberado():
            return self._negado()
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        self._executar(lambda: self._get(u.path, q))

    def _get(self, p, q):
        if p == "/api/estado":
            res, _ = motor_ok(TRABALHO, "ocr_disponivel", tempo=60)
            return self._send(200, {"versao": VERSAO, "ocr": res, "preferencias": ler_prefs(),
                                    "sistema": "mac" if sys.platform == "darwin" else ("windows" if os.name == "nt" else "linux")})
        if p == "/api/pagina":
            fmt = "jpeg" if q.get("fmt") == "jpeg" else "png"
            res, corpo = motor_ok(VISUAL, "render", {"doc": doc_motor(q.get("doc")), "p": int(q.get("p", 0)),
                                                     "escala": float(q.get("escala", 1)), "fmt": fmt}, tempo=90)
            return self._send(200, corpo, res["tipo"], {"Cache-Control": "private, max-age=600"})
        if p == "/api/objetos":
            res, _ = motor_ok(VISUAL, "objetos", {"doc": doc_motor(q.get("doc")), "p": int(q.get("p", 0))})
            return self._send(200, res)
        if p == "/api/buscar":
            res, _ = motor_ok(VISUAL, "buscar", {"doc": doc_motor(q.get("doc")), "termo": q.get("termo", "")[:200]})
            return self._send(200, res)
        if p == "/api/progresso":
            return self._send(200, {"progresso": PROGRESSO.get(q.get("tarefa", ""))})
        if p == "/api/pendentes":
            with LOCK:
                lista = PENDENTES[:]
                PENDENTES.clear()
            return self._send(200, lista)
        if p == "/favicon.png":
            return self._send(200, FAVICON.read_bytes(), "image/png")
        rel = "index.html" if p in ("", "/") else p.lstrip("/")
        f = (PUBLIC / rel).resolve()
        if PUBLIC.resolve() not in f.parents or not f.is_file() or f.suffix not in TYPES:
            return self._err(404, "não encontrado")
        self._send(200, f.read_bytes(), TYPES[f.suffix])

    def do_HEAD(self):
        return self._err(405, "não permitido")

    # ---- POST
    def do_POST(self):
        if not self._liberado(gravar=True):
            return self._negado()
        self._executar(lambda: self._post(urlparse(self.path).path))

    def _post(self, p):
        if p == "/api/abrir":
            dados = self._corpo(MAX_ARQUIVO)
            nome = unquote(self.headers.get("X-Nome", ""))[:300]
            senha = unquote(self.headers.get("X-Senha", ""))[:300] or None  # só na memória, nunca gravada
            return self._send(200, abrir_bytes(dados, nome, senha))
        if p == "/api/destrancar":  # senha de um PDF aberto por dois cliques
            d = self._json(10_000)
            info = doc(d.get("doc"))
            res = registrar(secrets.token_hex(8), info["caminho"], info["nome"], str(d.get("senha") or "")[:300])
            with LOCK:
                DOCS.pop(str(d.get("doc")), None)
            return self._send(200, res)
        d = self._json()
        tarefa = str(d.get("tarefa") or "")[:40] or None
        if p == "/api/editar-texto":
            return self._send(200, nova_versao(d.get("doc"), "editar_texto",
                                               {"p": int(d.get("p", 0)), "edicoes": d.get("edicoes") or []}, 180))
        if p == "/api/ocr":
            args = {"paginas": d.get("paginas"), "idiomas": d.get("idiomas") or "por+eng", "girar": d.get("girar", True)}
            return self._send(200, nova_versao(d.get("doc"), "ocr", args, 3600, tarefa))
        if p == "/api/salvar":
            projeto = d.get("projeto") or {}
            args = {"docs": docs_do_projeto(projeto), "projeto": projeto, "assinatura": d.get("assinatura")}
            _, corpo = motor_ok(TRABALHO, "salvar", args, tempo=1800, tarefa=tarefa)
            return self._send(200, corpo, "application/pdf")
        if p == "/api/exportar":
            projeto = d.get("projeto") or {}
            tipo = d.get("tipo")
            base = {"docs": docs_do_projeto(projeto), "projeto": projeto, "nome": nome_limpo(d.get("nome"))[:120]}
            if tipo == "dividir":
                grupos = [[int(i) for i in g] for g in (d.get("grupos") or []) if g][:2000]
                if not grupos:
                    raise ErroPedido(400, "Nenhuma parte para gerar.")
                _, corpo = motor_ok(TRABALHO, "dividir", {**base, "grupos": grupos}, tempo=1800, tarefa=tarefa)
                return self._send(200, corpo, "application/zip")
            if tipo == "imagens":
                _, corpo = motor_ok(TRABALHO, "imagens", {**base, "formato": d.get("formato"), "dpi": d.get("dpi")},
                                    tempo=3600, tarefa=tarefa)
                return self._send(200, corpo, "application/zip")
            if tipo == "texto":
                _, corpo = motor_ok(TRABALHO, "texto", {"doc": doc_motor(d.get("doc"))}, tempo=600)
                return self._send(200, corpo, "text/plain; charset=utf-8")
            raise ErroPedido(400, "tipo inválido")
        if p == "/api/comparar":
            res, _ = motor_ok(TRABALHO, "comparar", {"a": doc_motor(d.get("a")), "b": doc_motor(d.get("b"))}, tempo=900)
            return self._send(200, res)
        if p == "/api/certificado":
            try:
                base64.b64decode(str(d.get("pfx") or ""), validate=True)
            except ValueError:
                raise ErroPedido(400, "arquivo de certificado inválido") from None
            res, _ = motor_ok(TRABALHO, "certificado", {"pfx": d.get("pfx"), "senha": d.get("senha")}, tempo=60)
            return self._send(200, res)
        raise ErroPedido(404, "não encontrado")

    # ---- PUT / DELETE
    def do_PUT(self):
        if not self._liberado(gravar=True):
            return self._negado()

        def put():
            if urlparse(self.path).path != "/api/preferencias":
                raise ErroPedido(404, "não encontrado")
            d = self._json(3_000_000)
            with LOCK:
                gravar_json(PREFS, d)
            self._send(200, {"ok": True})
        self._executar(put)

    def do_DELETE(self):
        if not self._liberado(gravar=True):
            return self._negado()
        m = re.fullmatch(r"/api/doc/([0-9a-f]{16})", urlparse(self.path).path)
        if not m:
            return self._err(404, "não encontrado")
        with LOCK:
            d = DOCS.pop(m.group(1), None)
        if d:
            for motor in (VISUAL, TRABALHO):
                try:
                    motor.pedir("fechar", {"caminho": d["caminho"]}, tempo=20)
                except ErroMotor:
                    pass
            Path(d["caminho"]).unlink(missing_ok=True)
        self._send(200, {"ok": True})


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32


def trava_instancia():
    f = os.fdopen(os.open(DATA / ".em-uso", os.O_RDWR | os.O_CREAT, 0o600), "r+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def vigia_entrada(srv):
    """Modo janela: desliga quando o app fecha a entrada padrão; atende "ABRIR <caminho>"."""
    try:
        for linha in sys.stdin.buffer:
            texto = linha.decode("utf-8", "replace").rstrip("\r\n")
            if texto.startswith("ABRIR "):
                threading.Thread(target=abrir_caminho, args=(texto[6:],), daemon=True).start()
    except (OSError, ValueError, AttributeError):
        pass
    srv.shutdown()


def vigia_caixa():
    """Arquivos pedidos por uma segunda abertura do app (pasta só do usuário)."""
    while True:
        time.sleep(0.8)
        try:
            for f in sorted(ENTRADA_DIR.glob("*.abrir")):
                try:
                    caminho = f.read_text(encoding="utf-8").strip()
                finally:
                    f.unlink(missing_ok=True)
                if caminho:
                    abrir_caminho(caminho)
        except OSError:
            pass


def vigia_ociosidade(srv, limite):
    while True:
        time.sleep(5)
        if time.monotonic() - ULTIMO_USO > limite:
            srv.shutdown()
            return


def main():
    global PORT
    janela = "--janela" in sys.argv
    preparar_pastas_basicas()
    trava = trava_instancia()
    if trava is None:
        print("BRAVO-PDF OCUPADO", flush=True)
        sys.exit(3)
    preparar_pastas()
    srv = Servidor(("127.0.0.1", int(os.environ.get("BRAVO_PORTA", "0"))), H)
    PORT = srv.server_address[1]
    print(f"BRAVO-PDF {PORT} {CHAVE_ENTRADA}", flush=True)
    if janela:
        threading.Thread(target=vigia_entrada, args=(srv,), daemon=True).start()
    else:
        threading.Thread(target=vigia_ociosidade, args=(srv, int(os.environ.get("BRAVO_OCIOSO", "180"))),
                         daemon=True).start()
    threading.Thread(target=vigia_caixa, daemon=True).start()
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            threading.Thread(target=abrir_caminho, args=(a,), daemon=True).start()
    try:
        srv.serve_forever()
    finally:
        srv.server_close()
        VISUAL.parar()
        TRABALHO.parar()
        shutil.rmtree(SESSAO_DIR, ignore_errors=True)  # documentos abertos não ficam no disco
        trava.close()


def preparar_pastas_basicas():
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DATA, 0o700)
    except OSError:
        pass


if __name__ == "__main__":
    main()
