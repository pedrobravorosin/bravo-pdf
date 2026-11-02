# Funções usadas pelos scripts construir-*.sh. Não rode direto.
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$RAIZ/ferramentas/versoes.sh"
DIST="$RAIZ/dist"
CACHE="${CACHE:-$RAIZ/.cache}"
mkdir -p "$DIST" "$CACHE"

sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

baixar() {  # url destino sha256
  if [ ! -f "$2" ]; then curl -fL --retry 3 -o "$2.parcial" "$1"; mv "$2.parcial" "$2"; fi
  if [ "$(sha "$2")" != "$3" ]; then echo "ERRO: hash não confere: $2" >&2; rm -f "$2"; exit 1; fi
}

# Python do computador que constrói: precisa ser 3.13 para pré-compilar os .pyc certos.
PY_HOST="${PY_HOST:-python3}"
"$PY_HOST" -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version' || {
  echo "ERRO: use Python 3.13 para construir (PY_HOST=...)" >&2; exit 1; }

instalar_libs() {  # pasta-site-packages plataforma...
  local destino="$1"; shift
  local plat=(); for p in "$@"; do plat+=(--platform "$p"); done
  "$PY_HOST" -m pip install -q --disable-pip-version-check --no-deps --no-compile --require-hashes \
    --only-binary=:all: --implementation cp --python-version 3.13 "${plat[@]}" \
    --target "$destino" -r "$RAIZ/app/requirements.txt"
  rm -rf "$destino"/bin  # scripts de linha de comando das bibliotecas: o app não usa
}

copiar_app() {  # destino
  mkdir -p "$1"
  (cd "$RAIZ/app" && tar cf - --exclude='__pycache__' --exclude='*.pyc' --exclude='requirements.txt' --exclude='tessdata' .) | (cd "$1" && tar xf -)
  # Modelos do OCR: sempre os do hash fixo (nunca o que estiver solto na pasta de desenvolvimento).
  mkdir -p "$1/tessdata"
  baixar "$TESS_POR_URL" "$CACHE/por.traineddata" "$TESS_POR_SHA256"
  baixar "$TESS_ENG_URL" "$CACHE/eng.traineddata" "$TESS_ENG_SHA256"
  baixar "$TESS_OSD_URL" "$CACHE/osd.traineddata" "$TESS_OSD_SHA256"
  cp "$CACHE/por.traineddata" "$CACHE/eng.traineddata" "$CACHE/osd.traineddata" "$1/tessdata/"
}

enxugar_python() {  # pasta-lib-do-python (onde fica os.py)
  local L="$1"
  rm -rf "$L"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3,pydoc_data} "$L"/turtle.py
  rm -rf "$L"/site-packages/pip "$L"/site-packages/pip-*
  find "$L" -name '_tkinter*' -delete
  find "$L" -type d -name '__pycache__' -prune -exec rm -rf {} +
}

pre_compilar() {  # pastas...
  "$PY_HOST" -m compileall -q -j0 --invalidation-mode unchecked-hash "$@" >/dev/null
}

# Trava de privacidade: nenhum documento, certificado ou preferência pessoal entra num pacote.
checar_privacidade() {
  if find "$1" \( -iname '*.pdf' -o -iname '*.pfx' -o -iname '*.p12' -o -name 'preferencias.json' \
       -o -path '*/sessao/*' -o -path '*/entrada/*' -o -iname '*.abrir' \) | grep -q .; then
    echo "ERRO: arquivo de dados pessoais dentro do pacote ($1)" >&2; exit 1
  fi
}
