#!/bin/bash
# Gera, para Linux 64 bits (x86_64):
#   dist/BravoPDF-Linux-amd64.deb         (Ubuntu, Debian, Mint, Pop!_OS...)
#   dist/BravoPDF-Linux-x86_64.tar.gz    (qualquer distribuição, instala sem root)
# Roda em Linux com: bash, curl, tar, dpkg-deb, Python 3.13 com pip.
. "$(dirname "$0")/comum.sh"
command -v dpkg-deb >/dev/null || { echo "ERRO: precisa do dpkg-deb" >&2; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
L="$RAIZ/instaladores/linux"

echo "== Python $PY_VERSAO (python-build-standalone, x86_64)"
TGZ="$CACHE/$(pbs_arquivo x86_64-unknown-linux-gnu)"
baixar "$PBS_BASE/$(pbs_arquivo x86_64-unknown-linux-gnu)" "$TGZ" "$PY_LINUX_X86_64_SHA256"
O="$T/origem"; mkdir -p "$O"
tar -xzf "$TGZ" -C "$O"
LIB="$O/python/lib/python3.13"
enxugar_python "$LIB"
rm -rf "$O/python/include" "$O/python/share" "$O/python/lib/pkgconfig" "$O/python/lib"/{libtcl,libtk,tcl,tk,itcl,thread}* \
  "$O/python/bin"/{pip*,idle*,pydoc*,2to3*,python3*-config}

# Tira símbolos de depuração das bibliotecas (~110 MB a menos). O executável fica como está:
# o strip quebra o binário do python-build-standalone.
strip --strip-debug "$O/python/lib/libpython3.13.so.1.0"
find "$LIB/lib-dynload" -name '*.so' -exec strip --strip-debug {} +
"$O/python/bin/python3" -c 'import ssl, ctypes, sqlite3, _decimal' || { echo "ERRO: Python quebrado" >&2; exit 1; }

echo "== Bibliotecas (manylinux x86_64, com hash conferido)"
instalar_libs "$LIB/site-packages" manylinux_2_28_x86_64 manylinux_2_17_x86_64 manylinux2014_x86_64

echo "== App"
copiar_app "$O/app"
rm -f "$O/app/icone/bravo-pdf.icns" "$O/app/icone/bravo-pdf.ico"
cp "$RAIZ/LICENSE" "$O/LICENCA.txt"
pre_compilar "$O/app" "$LIB"
"$O/python/bin/python3" -I -c "import tesserocr, pypdfium2, pypdf, PIL, cryptography" || { echo "ERRO: bibliotecas não abrem" >&2; exit 1; }
checar_privacidade "$O"

echo "== Pacote .deb"
P="$T/deb"
mkdir -p "$P/DEBIAN" "$P/opt/bravo-pdf" "$P/usr/bin" "$P/usr/share/applications" \
  "$P/usr/share/icons/hicolor/256x256/apps" "$P/usr/share/icons/hicolor/512x512/apps" "$P/usr/share/doc/bravo-pdf"
cp -R "$O/python" "$O/app" "$P/opt/bravo-pdf/"
install -m 755 "$L/bravo-pdf" "$P/usr/bin/bravo-pdf"
install -m 644 "$L/bravo-pdf.desktop" "$P/usr/share/applications/"
install -m 644 "$O/app/icone/bravo-pdf-256.png" "$P/usr/share/icons/hicolor/256x256/apps/bravo-pdf.png"
"$PY_HOST" -c "from PIL import Image; Image.open('$O/app/icone/bravo-pdf.png').resize((512,512), Image.LANCZOS).save('$P/usr/share/icons/hicolor/512x512/apps/bravo-pdf.png')" 2>/dev/null \
  || rmdir "$P/usr/share/icons/hicolor/512x512/apps"
install -m 644 "$RAIZ/LICENSE" "$P/usr/share/doc/bravo-pdf/copyright"
chmod -R u=rwX,go=rX "$P/opt" "$P/usr"
cat > "$P/DEBIAN/control" <<FIM
Package: bravo-pdf
Version: $VERSAO_APP
Architecture: amd64
Maintainer: Bravo PDF <noreply@users.noreply.github.com>
Installed-Size: $(du -sk "$P/opt" "$P/usr" | awk '{s+=$1} END {print s}')
Section: misc
Priority: optional
Homepage: https://github.com/pedrobravorosin/bravo-pdf
Description: Editor de PDF completo que funciona sem internet
 Anota, preenche formulários, assina (desenho ou certificado digital A1),
 organiza páginas, tarja dados de verdade, reconhece texto (OCR), edita
 o texto original e compara versões. Nenhum arquivo sai do computador.
FIM
DEB="$DIST/BravoPDF-Linux-amd64.deb"
dpkg-deb --root-owner-group -Zxz --build "$P" "$DEB" >/dev/null

echo "== Pacote portátil .tar.gz"
Q="$T/tar/bravo-pdf"; mkdir -p "$Q"
cp -R "$O/python" "$O/app" "$O/LICENCA.txt" "$Q/"
install -m 755 "$L/instalar.sh" "$L/desinstalar.sh" "$Q/"
install -m 644 "$L/bravo-pdf.desktop" "$Q/"
printf 'Bravo PDF %s para Linux 64 bits\n\nPara instalar (sem root e sem internet), abra um terminal nesta pasta e rode:\n\n  sh instalar.sh\n\nDepois abra o Bravo PDF pelo menu de aplicativos.\n' "$VERSAO_APP" > "$Q/LEIA-ME.txt"
tar -C "$T/tar" -czf "$DIST/BravoPDF-Linux-x86_64.tar.gz" bravo-pdf
ls -la "$DEB" "$DIST/BravoPDF-Linux-x86_64.tar.gz"
