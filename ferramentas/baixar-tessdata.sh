#!/bin/bash
# Baixa os modelos do OCR (hash conferido) para app/tessdata, para rodar o app em desenvolvimento.
# Os instaladores fazem isso sozinhos (copiar_app em comum.sh).
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$RAIZ/ferramentas/versoes.sh"
D="$RAIZ/app/tessdata"; mkdir -p "$D"
sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
for par in "por:$TESS_POR_URL:$TESS_POR_SHA256" "eng:$TESS_ENG_URL:$TESS_ENG_SHA256" "osd:$TESS_OSD_URL:$TESS_OSD_SHA256"; do
  nome="${par%%:*}"; resto="${par#*:}"; hash="${resto##*:}"; url="${resto%:*}"
  f="$D/$nome.traineddata"
  [ -f "$f" ] && [ "$(sha "$f")" = "$hash" ] && continue
  curl -fL --retry 3 -o "$f.parcial" "$url"
  [ "$(sha "$f.parcial")" = "$hash" ] || { rm -f "$f.parcial"; echo "ERRO: hash não confere: $nome" >&2; exit 1; }
  mv "$f.parcial" "$f"
done
echo "Modelos do OCR prontos em $D"
