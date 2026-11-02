#!/bin/bash
# Gera dist/BravoPDF-Instalador-Windows.exe.
# Roda em Linux ou macOS com: bash, curl, unzip, Python 3.13 com pip, makensis (NSIS 3).
. "$(dirname "$0")/comum.sh"
command -v makensis >/dev/null || { echo "ERRO: instale o NSIS (makensis)" >&2; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
O="$T/origem"; mkdir -p "$O"

echo "== Python $PY_VERSAO oficial para Windows"
NUPKG="$CACHE/python.$PY_VERSAO.nupkg"
baixar "$PY_WIN_URL" "$NUPKG" "$PY_WIN_SHA256"
unzip -q "$NUPKG" 'tools/*' -d "$T/nupkg"
mv "$T/nupkg/tools" "$O/python"
enxugar_python "$O/python/Lib"
rm -rf "$O/python/include" "$O/python/libs" "$O/python/Scripts" "$O/python/vcruntime140_1.dll.bak" 2>/dev/null || true

echo "== Bibliotecas (win_amd64, com hash conferido)"
instalar_libs "$O/python/Lib/site-packages" win_amd64

echo "== App"
copiar_app "$O/app"
rm -f "$O/app/icone/bravo-pdf.icns" "$O/app/icone/bravo-pdf.png"
sed 's/$/\r/' "$RAIZ/LICENSE" > "$O/LICENCA.txt"
pre_compilar "$O/app" "$O/python/Lib"
checar_privacidade "$O"

echo "== Instalador"
TAM=$(du -sk "$O" | cut -f1)
SAIDA="$DIST/BravoPDF-Instalador-Windows.exe"
makensis -V2 -INPUTCHARSET UTF8 -DVERSAO="$VERSAO_APP" -DORIGEM="$O" -DSAIDA="$SAIDA" -DTAMANHO_KB="$TAM" \
  "$RAIZ/instaladores/windows/bravo-pdf.nsi"
ls -la "$SAIDA"
