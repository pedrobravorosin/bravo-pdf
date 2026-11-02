#!/bin/sh
# Remove o Bravo PDF instalado pelo instalar.sh. Suas preferências ficam guardadas,
# a não ser que você responda "s" no fim.
set -eu
D="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$D/bravo-pdf-app" "$D/applications/bravo-pdf.desktop" "$D/icons/hicolor/256x256/apps/bravo-pdf.png" \
  "$HOME/.local/bin/bravo-pdf"
echo "Bravo PDF removido."
if [ -d "$D/bravo-pdf" ]; then
  printf "Apagar também suas preferências e assinaturas guardadas (%s)? [s/N] " "$D/bravo-pdf"
  read -r r || r=n
  [ "$r" = "s" ] || [ "$r" = "S" ] && rm -rf "$D/bravo-pdf" && echo "Dados apagados." || echo "Dados mantidos."
fi
