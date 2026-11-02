"""Testes de segurança do servidor e do bloqueio de rede. Rode: python -m unittest discover tests"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import quote

AQUI = Path(__file__).resolve().parent
APP = AQUI.parent / "app"
EX = AQUI / "exemplos"


def ligar(dados, *extra):
    env = dict(os.environ, BRAVO_DADOS=str(dados))
    p = subprocess.Popen([sys.executable, "-I", "-s", str(APP / "server.py"), "--janela", *extra], cwd=str(APP), env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p, p.stdout.readline().decode().split()


class TestServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.proc, linha = ligar(cls.tmp.name)
        assert linha[0] == "BRAVO-PDF", linha
        cls.porta, cls.chave = int(linha[1]), linha[2]
        cls.host = f"127.0.0.1:{cls.porta}"
        st, h, _ = cls.req("GET", f"/entrar?t={cls.chave}")
        assert st == 303, st
        cls.cookie = h["set-cookie"].split(";")[0]
        assert "HttpOnly" in h["set-cookie"] and "SameSite=Strict" in h["set-cookie"]

    @classmethod
    def tearDownClass(cls):
        cls.proc.stdin.close()
        cls.proc.wait(timeout=15)
        cls.tmp.cleanup()

    @classmethod
    def req(cls, metodo, caminho, corpo=None, cab=None):
        c = http.client.HTTPConnection("127.0.0.1", cls.porta, timeout=120)
        h = {"Host": cls.host, **(cab or {})}
        c.request(metodo, caminho, body=corpo, headers=h)
        r = c.getresponse()
        dados = r.read()
        c.close()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, dados

    def com_sessao(self, metodo, caminho, corpo=None, cab=None):
        return self.req(metodo, caminho, corpo, {"Cookie": self.cookie, **(cab or {})})

    def gravar(self, metodo, caminho, corpo=None, cab=None):
        return self.com_sessao(metodo, caminho, corpo, {"X-Bravo": "1", **(cab or {})})

    def abrir(self, caminho, senha=None):
        cab = {"X-Nome": quote(Path(caminho).name)}
        if senha is not None:
            cab["X-Senha"] = quote(senha)
        return self.gravar("POST", "/api/abrir", Path(caminho).read_bytes(), cab)

    def test_sem_sessao_nada_e_entregue(self):
        for caminho in ("/", "/api/estado", "/app.js", "/api/pendentes"):
            self.assertEqual(self.req("GET", caminho)[0], 403, caminho)
        self.assertEqual(self.req("GET", "/api/estado", cab={"Cookie": "bp=errado"})[0], 403)

    def test_chave_vale_uma_vez(self):
        self.assertEqual(self.req("GET", f"/entrar?t={self.chave}")[0], 403)
        self.assertEqual(self.req("GET", "/entrar?t=chute")[0], 403)

    def test_cabecalhos_de_protecao(self):
        st, h, _ = self.com_sessao("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("default-src 'none'", h["content-security-policy"])
        self.assertNotIn("http:", h["content-security-policy"].replace("http://127.0.0.1", ""))
        self.assertEqual(h["x-frame-options"], "DENY")

    def test_host_estranho_recusado(self):
        st, _, _ = self.req("GET", "/api/estado", cab={"Cookie": self.cookie, "Host": "evil.example:80"})
        self.assertEqual(st, 403)

    def test_gravacao_exige_mesma_origem(self):
        corpo = json.dumps({"tema": "escuro"})
        self.assertEqual(self.com_sessao("PUT", "/api/preferencias", corpo)[0], 403)
        self.assertEqual(self.gravar("PUT", "/api/preferencias", corpo, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.gravar("PUT", "/api/preferencias", corpo, {"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.gravar("PUT", "/api/preferencias", corpo, {"Origin": f"http://{self.host}"})[0], 200)
        self.assertEqual(self.com_sessao("POST", "/api/abrir", b"%PDF-1.4")[0], 403)

    def test_sem_travessia_de_pasta(self):
        for caminho in ("/../server.py", "/%2e%2e/server.py", "/icone/../../server.py", "/../preferencias.json"):
            self.assertEqual(self.com_sessao("GET", caminho)[0], 404, caminho)
        self.assertEqual(self.gravar("DELETE", "/api/doc/../../x")[0], 404)

    def test_abrir_ver_e_fechar(self):
        st, _, d = self.abrir(EX / "texto-3-paginas.pdf")
        self.assertEqual(st, 200, d)
        info = json.loads(d)
        self.assertEqual(len(info["paginas"]), 3)
        st, h, png = self.com_sessao("GET", f"/api/pagina?doc={info['id']}&p=0&escala=1")
        self.assertEqual(st, 200)
        self.assertTrue(png.startswith(b"\x89PNG"))
        sessao = Path(self.tmp.name) / "sessao"
        self.assertEqual(len(list(sessao.iterdir())), 1)
        self.assertEqual(self.gravar("DELETE", f"/api/doc/{info['id']}")[0], 200)
        self.assertEqual(list(sessao.iterdir()), [])  # o arquivo temporário some ao fechar
        self.assertEqual(self.com_sessao("GET", f"/api/pagina?doc={info['id']}&p=0")[0], 404)

    def test_pdf_com_senha_e_lixo(self):
        from pypdf import PdfWriter
        w = PdfWriter(clone_from=str(EX / "texto-3-paginas.pdf"))
        w.encrypt("12345", algorithm="AES-256")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.pdf"
            with open(p, "wb") as f:
                w.write(f)
            st, _, corpo = self.abrir(p)
            self.assertEqual(st, 401)
            self.assertTrue(json.loads(corpo)["senha"])
            self.assertEqual(self.abrir(p, "errada")[0], 401)
            self.assertEqual(self.abrir(p, "12345")[0], 200)
        self.assertEqual(self.gravar("POST", "/api/abrir", b"nao e pdf")[0], 400)
        # PDF quebrado não derruba o servidor
        st, _, _ = self.gravar("POST", "/api/abrir", b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n%%EOF")
        self.assertIn(st, (400, 422))
        self.assertEqual(self.com_sessao("GET", "/api/estado")[0], 200)

    def test_senha_nunca_vai_para_o_disco(self):
        prefs = Path(self.tmp.name) / "preferencias.json"
        conteudo = prefs.read_text("utf-8") if prefs.exists() else ""
        self.assertNotIn("12345", conteudo)
        for p in Path(self.tmp.name).rglob("*"):
            if p.is_file() and p.suffix != ".pdf":
                try:
                    dados = p.read_bytes()
                except PermissionError:  # Windows: arquivo da trava de instância, aberto pelo servidor
                    continue
                self.assertNotIn(b"12345", dados, p)

    def test_certificado_invalido(self):
        st, _, _ = self.gravar("POST", "/api/certificado", json.dumps({"pfx": "bm9wZQ==", "senha": "x"}))
        self.assertIn(st, (400, 422))

    def test_uma_instancia_por_usuario(self):
        p, linha = ligar(self.tmp.name)
        p.wait(timeout=10)
        self.assertEqual(linha, ["BRAVO-PDF", "OCUPADO"])


class TestBlindagem(unittest.TestCase):
    def test_internet_bloqueada(self):
        codigo = (
            "import sys, socket, urllib.request; sys.path.insert(0, sys.argv[1]); import blindagem; blindagem.ativar()\n"
            "falhas = 0\n"
            "for f in (lambda: socket.create_connection(('1.1.1.1', 443), 2), lambda: socket.getaddrinfo('example.com', 443),\n"
            "          lambda: urllib.request.urlopen('https://example.com', timeout=2),\n"
            "          lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('8.8.8.8', 53))):\n"
            "    try: f()\n"
            "    except PermissionError: falhas += 1\n"
            "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.close()\n"
            "print(falhas)\n")
        r = subprocess.run([sys.executable, "-I", "-c", codigo, str(APP)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), "4", r.stderr)

    def test_motor_tambem_sem_internet(self):
        codigo = ("import sys; sys.path.insert(0, sys.argv[1]); sys.argv = ['motor.py']\n"
                  "import runpy, socket\n"
                  "import blindagem; blindagem.ativar()\n"
                  "try: socket.create_connection(('1.1.1.1', 443), 2); print('ABERTO')\n"
                  "except PermissionError: print('BLOQUEADO')\n")
        r = subprocess.run([sys.executable, "-I", "-c", codigo, str(APP)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), "BLOQUEADO", r.stderr)
        self.assertIn("blindagem.ativar()", (APP / "motor.py").read_text("utf-8"))

    def test_servidor_desliga_e_apaga_a_sessao_quando_a_janela_fecha(self):
        with tempfile.TemporaryDirectory() as d:
            p, linha = ligar(d)
            self.assertEqual(linha[0], "BRAVO-PDF")
            (Path(d) / "sessao" / "sobra.tmp").write_bytes(b"x")
            p.stdin.close()
            inicio = time.monotonic()
            p.wait(timeout=15)
            self.assertLess(time.monotonic() - inicio, 15)
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", int(linha[1])), 1)
            self.assertFalse(any((Path(d) / "sessao").glob("*")))


if __name__ == "__main__":
    unittest.main()
