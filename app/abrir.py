"""Abre o Bravo PDF numa janela própria (Windows e Linux).

- Liga o servidor local (só 127.0.0.1, porta livre escolhida na hora) e recebe
  dele uma chave de uso único para entrar.
- Abre a interface numa janela de aplicativo do Edge, Chrome, Chromium ou Brave,
  com perfil separado e sem acesso à internet: todo endereço que não seja o do
  próprio computador vai para um proxy inexistente e falha.
- Arquivos passados na linha de comando (abrir com dois cliques) são entregues
  ao servidor pelo canal privado entre os dois processos. Se o Bravo PDF já
  estiver aberto, o pedido vai para a pasta de dados do usuário e a janela
  aberta mostra o arquivo.
- Quando a janela fecha, o servidor desliga e apaga os documentos temporários.

No macOS o app nativo (instaladores/macos) faz esse papel.
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
import blindagem  # noqa: E402

blindagem.ativar()
from server import DATA, ENTRADA_DIR, NOME  # noqa: E402  (só constantes; não liga nada)

WINDOWS = os.name == "nt"

FLAGS_JANELA = [
    "--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
    "--disable-background-networking", "--disable-component-update", "--disable-default-apps",
    "--disable-domain-reliability", "--disable-breakpad", "--disable-client-side-phishing-detection",
    "--metrics-recording-only", "--no-pings", "--disable-features=Translate,OptimizationHints,MediaRouter,"
    "AutofillServerCommunication,SpareRendererForSitePerProcess,msEdgeShopping,msEdgeCollections",
    "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=<-loopback>;127.0.0.1;localhost",
    "--window-size=1360,900",
]


def aviso(texto):
    if WINDOWS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, texto, NOME, 0x40)
    elif shutil.which("zenity"):
        subprocess.run(["zenity", "--info", f"--title={NOME}", f"--text={texto}"], check=False)
    elif shutil.which("kdialog"):
        subprocess.run(["kdialog", "--title", NOME, "--msgbox", texto], check=False)
    else:
        print(texto, file=sys.stderr)


def acha_navegador_app():
    if WINDOWS:
        bases = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        rel = [("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe"),
               ("BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
        for r in rel:
            for b in bases:
                if b and Path(b, *r).exists():
                    return str(Path(b, *r))
        return None
    for nome in ("microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable",
                 "chromium", "chromium-browser", "brave-browser", "brave"):
        p = shutil.which(nome)
        if p:
            return p
    return None


def python_do_servidor():
    exe = Path(sys.executable)
    if WINDOWS and exe.name.lower() == "pythonw.exe":
        exe = exe.with_name("python.exe")
    return str(exe)


def arquivos_pedidos():
    return [str(Path(a).resolve()) for a in sys.argv[1:] if not a.startswith("-") and Path(a).is_file()]


def entregar_a_janela_aberta(arquivos):
    """O Bravo PDF já está aberto: deixa o pedido na pasta privada que ele vigia."""
    ENTRADA_DIR.mkdir(parents=True, exist_ok=True)
    for a in arquivos:
        destino = ENTRADA_DIR / f"{secrets.token_hex(8)}.abrir"
        fd = os.open(destino.with_suffix(".tmp"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(a)
        destino.with_suffix(".tmp").replace(destino)


def ligar_servidor(janela):
    DATA.mkdir(parents=True, exist_ok=True)
    log = os.fdopen(os.open(DATA / "servidor.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w")
    extra = {"creationflags": 0x08000000} if WINDOWS else {"start_new_session": True}
    args = [python_do_servidor(), "-I", "-s", str(APP / "server.py")] + (["--janela"] if janela else arquivos_pedidos())
    srv = subprocess.Popen(args, cwd=str(APP), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, **extra)
    linha = srv.stdout.readline().decode("ascii", "ignore").split()
    if linha[:2] == ["BRAVO-PDF", "OCUPADO"]:
        pedidos = arquivos_pedidos()
        if pedidos:
            entregar_a_janela_aberta(pedidos)
        else:
            aviso(f"O {NOME} já está aberto.")
        sys.exit(0)
    if len(linha) != 3 or linha[0] != "BRAVO-PDF":
        aviso(f"O {NOME} não conseguiu ligar. Veja o arquivo servidor.log em:\n{DATA}")
        sys.exit(1)
    if janela:
        for a in arquivos_pedidos():
            srv.stdin.write(f"ABRIR {a}\n".encode("utf-8"))
        srv.stdin.flush()
    return srv, f"http://127.0.0.1:{int(linha[1])}/entrar?t={linha[2]}"


def preparar_perfil():
    """Perfil novo a cada abertura: pergunta onde salvar cada arquivo e não guarda nada."""
    perfil = tempfile.mkdtemp(prefix="bravo-pdf-janela-")
    padrao = Path(perfil, "Default")
    padrao.mkdir()
    prefs = {"download": {"prompt_for_download": True, "directory_upgrade": True},
             "savefile": {"default_directory": str(Path.home() / "Documents")},
             "credentials_enable_service": False, "profile": {"password_manager_enabled": False},
             "translate": {"enabled": False}, "spellcheck": {"dictionaries": []}}
    Path(padrao, "Preferences").write_text(json.dumps(prefs), encoding="utf-8")
    return perfil


def main():
    nav = acha_navegador_app()
    srv, url = ligar_servidor(janela=bool(nav))
    if not nav:
        srv.stdin.close()
        webbrowser.open(url)
        return
    perfil = preparar_perfil()
    try:
        subprocess.run([nav, f"--app={url}", f"--user-data-dir={perfil}", *FLAGS_JANELA], check=False)
    finally:
        try:
            srv.stdin.close()
            srv.wait(timeout=15)
        except Exception:  # noqa: BLE001
            srv.kill()
        shutil.rmtree(perfil, ignore_errors=True)


if __name__ == "__main__":
    main()
