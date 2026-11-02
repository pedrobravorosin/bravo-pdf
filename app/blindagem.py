"""Bloqueio de rede do Bravo PDF.

Instala um "audit hook" do Python (sys.addaudithook, biblioteca padrão) que
recusa qualquer conexão, resolução de nome ou pedido HTTP para fora do próprio
computador. Só o endereço de loopback (127.0.0.1 / ::1) é permitido, que é por
onde a janela do app conversa com o servidor local. Depois de instalado, o
bloqueio não pode ser desligado pelo resto do processo.
"""
import ipaddress
import sys
from urllib.parse import urlsplit

_ATIVO = False


def _local(host):
    if host is None:
        return True
    if isinstance(host, (bytes, bytearray)):
        host = host.decode("ascii", "ignore")
    h = str(host).strip("[]").split("%")[0].lower()
    if h in ("", "localhost"):
        return h == "localhost"
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _recusa(onde):
    raise PermissionError(f"Bravo PDF: acesso à internet bloqueado ({onde})")


def _gancho(evento, args):
    if evento in ("socket.connect", "socket.sendto", "socket.bind"):
        endereco = args[1] if len(args) > 1 else None
        if not (isinstance(endereco, tuple) and _local(endereco[0])):
            _recusa(evento)
    elif evento in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex",
                    "socket.gethostbyaddr", "socket.getnameinfo"):
        alvo = args[0] if args else None
        if evento == "socket.getnameinfo" and isinstance(alvo, tuple):
            alvo = alvo[0]
        if not _local(alvo):
            _recusa(evento)
    elif evento in ("urllib.Request", "webbrowser.open"):
        if not _local(urlsplit(str(args[0])).hostname):
            _recusa(evento)
    elif evento in ("ftplib.connect", "smtplib.connect", "poplib.connect", "imaplib.open", "telnetlib.Telnet.open",
                    "http.client.connect"):
        host = args[1] if len(args) > 1 else None
        if not _local(host):
            _recusa(evento)


def ativar():
    global _ATIVO
    if not _ATIVO:
        sys.addaudithook(_gancho)
        _ATIVO = True
