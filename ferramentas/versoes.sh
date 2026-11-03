# Versões fixas e hashes conferidos de tudo que entra nos instaladores.
# Mude aqui para atualizar; os scripts de construção conferem cada hash.
VERSAO_APP=0.0.0

PY_VERSAO=3.13.17
# Windows: Python oficial da Python Software Foundation (pacote NuGet "python", x64).
# SHA512 do catálogo NuGet: DmZ5KLtPGVc8bNiPZRM7LgeyQ6XHFvM1tWqma7nsb4IyglbSLDop4joCdqxcam14YhH+q1JIkK0eVmKRlsaynA==
PY_WIN_URL="https://api.nuget.org/v3-flatcontainer/python/$PY_VERSAO/python.$PY_VERSAO.nupkg"
PY_WIN_SHA256=dce409744b088f94c6e37ba41f8100c384c27e029e843237364c602d30d475e5

# macOS e Linux: Python independente (python-build-standalone, o mesmo usado pelo uv),
# relocável e sem dependências do sistema.
PBS_DATA=20261021
PBS_BASE="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_DATA"
PY_MAC_ARM64_SHA256=9c985cbf327425873469896ce748c7134b6deca8edb81e93c589ad2fc5aff445
PY_MAC_X86_64_SHA256=b7d7c2dd63545cabe996191b6f20f0b652c7de123d9ca451dda7e5f1ebbcbbbc
PY_LINUX_X86_64_SHA256=cbda6f7767884fc456860b11fd184391a9320cae00a86c0f49a1c7ac6e236f7a
pbs_arquivo() { echo "cpython-$PY_VERSAO+$PBS_DATA-$1-install_only.tar.gz"; }

# OCR: modelos de idioma do Tesseract 4.1.0 (Apache-2.0), baixados na construção e
# conferidos pelo hash. Vão dentro do app: o OCR nunca usa a internet.
TESSDATA_BASE="https://raw.githubusercontent.com/tesseract-ocr"
TESS_POR_URL="$TESSDATA_BASE/tessdata_best/4.1.0/por.traineddata"
TESS_POR_SHA256=711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04
TESS_ENG_URL="$TESSDATA_BASE/tessdata_best/4.1.0/eng.traineddata"
TESS_ENG_SHA256=8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba
TESS_OSD_URL="$TESSDATA_BASE/tessdata/4.1.0/osd.traineddata"
TESS_OSD_SHA256=e19f2ae860792fdf372cf48d8ce70ae5da3c4052962fe22e9de1f680c374bb0e
