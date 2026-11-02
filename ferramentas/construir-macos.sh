#!/bin/bash
# Gera os instaladores do Mac (imagem .dmg com o app pronto, arrastar para Aplicativos):
#   dist/BravoPDF-macOS-AppleSilicon.dmg   (Macs com chip M1, M2, M3...)
#   dist/BravoPDF-macOS-Intel.dmg          (Macs com processador Intel)
# Roda num Mac com: Xcode Command Line Tools (swiftc, codesign, hdiutil), curl e Python 3.13 com pip.
# Quem instala o app não precisa de nada disso: o Python vai dentro do app.
# Observação: o tesserocr (OCR) só tem pacotes para macOS 15 ou mais novo. Em Macs mais
# antigos o app abre normalmente e só o OCR aparece como indisponível.
. "$(dirname "$0")/comum.sh"
[ "$(uname)" = Darwin ] || { echo "ERRO: rode num Mac" >&2; exit 1; }
M="$RAIZ/instaladores/macos"

construir() {  # arquitetura-swift tripla-pbs hash nome-do-dmg plataformas-pip...
  local ARCH="$1" TRIPLA="$2" HASH="$3" NOME_DMG="$4"; shift 4
  local T; T="$(mktemp -d)"
  local APP="$T/dmg/Bravo PDF.app"
  local C="$APP/Contents" R="$APP/Contents/Resources"
  echo "== $NOME_DMG ($ARCH)"
  mkdir -p "$C/MacOS" "$R"

  local TGZ="$CACHE/$(pbs_arquivo "$TRIPLA")"
  baixar "$PBS_BASE/$(pbs_arquivo "$TRIPLA")" "$TGZ" "$HASH"
  tar -xzf "$TGZ" -C "$R"
  local LIB="$R/python/lib/python3.13"
  enxugar_python "$LIB"
  rm -rf "$R/python/include" "$R/python/share" "$R/python/lib/pkgconfig" "$R/python/lib"/{libtcl,libtk,tcl,tk,itcl,thread}* \
    "$R/python/bin"/{pip*,idle*,pydoc*,2to3*,python3*-config}
  instalar_libs "$LIB/site-packages" "$@"

  copiar_app "$R/app"
  rm -f "$R/app/icone/bravo-pdf.ico" "$R/app/icone/bravo-pdf.png"
  cp "$RAIZ/app/icone/bravo-pdf.icns" "$R/bravo-pdf.icns"
  pre_compilar "$R/app" "$LIB"
  checar_privacidade "$APP"

  swiftc -O -target "$ARCH-apple-macos11.3" -o "$C/MacOS/BravoPDF" "$M/main.swift"
  sed "s/VERSAO/$VERSAO_APP/g" "$M/Info.plist" > "$C/Info.plist"
  printf 'APPL????' > "$C/PkgInfo"

  # Assinatura local (ad-hoc): cada binário e depois o app inteiro.
  find "$R/python" -type f \( -perm -u+x -o -name '*.so' -o -name '*.dylib' \) -print0 |
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q Mach-O; then codesign --force --sign - --timestamp=none "$f"; fi
    done
  codesign --force --sign - --timestamp=none --options runtime "$APP"
  codesign --verify --deep --strict "$APP"
  "$R/python/bin/python3" -I -c 'import ssl, ctypes, sqlite3' 2>/dev/null || [ "$ARCH" != "$(uname -m)" ] || {
    echo "ERRO: Python do app não abre" >&2; exit 1; }

  cp "$M/LEIA-ME.txt" "$T/dmg/LEIA-ME.txt"
  ln -s /Applications "$T/dmg/Aplicativos"
  rm -f "$DIST/$NOME_DMG"
  hdiutil create -quiet -volname "Bravo PDF" -srcfolder "$T/dmg" -fs HFS+ -format UDZO -imagekey zlib-level=9 \
    -ov "$DIST/$NOME_DMG"
  rm -rf "$T"
  ls -la "$DIST/$NOME_DMG"
}

construir arm64 aarch64-apple-darwin "$PY_MAC_ARM64_SHA256" BravoPDF-macOS-AppleSilicon.dmg \
  macosx_15_0_arm64 macosx_14_0_arm64 macosx_13_0_arm64 macosx_12_0_arm64 macosx_11_0_arm64 macosx_11_0_universal2 macosx_10_13_universal2 macosx_10_9_universal2
construir x86_64 x86_64-apple-darwin "$PY_MAC_X86_64_SHA256" BravoPDF-macOS-Intel.dmg \
  macosx_15_0_x86_64 macosx_14_0_x86_64 macosx_13_0_x86_64 macosx_12_0_x86_64 macosx_11_0_x86_64 macosx_10_13_x86_64 macosx_10_12_x86_64 macosx_10_9_x86_64 macosx_10_13_universal2 macosx_10_9_universal2
