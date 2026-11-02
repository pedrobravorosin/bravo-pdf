# Bravo PDF

Editor de PDF completo que funciona no seu computador: ver, anotar, preencher, assinar, organizar, tarjar, reconhecer texto, editar o texto original e comparar versões. Faz parte da Bravo Suite, ao lado do Bravo Finance.

**Fechado no seu computador.** Depois de instalado, o Bravo PDF não usa a internet para nada: não tem conta, nuvem, telemetria, anúncios nem atualização automática, e não pede permissão para acessar outras pastas ou aplicativos (iCloud, Google Drive, Documentos...). Seus documentos nunca saem da sua máquina.

## Recursos

**Ver e encontrar**
- Páginas com zoom (largura, página inteira, 50 a 400%), miniaturas, modo escuro e impressão.
- Busca no documento com todos os resultados destacados; "Marcar todas" ou "Tarjar todas" de uma vez.
- Painel de detalhes: páginas, tamanho, versão do PDF, formulário e assinaturas digitais (com verificação de integridade).

**Anotar e editar**
- Texto livre, marca-texto, sublinhado, tachado, notas, caneta, retângulo, elipse, linha, seta, carimbo, imagem e corretivo (branco por cima).
- **Editar o texto original** do PDF: clique num trecho e reescreva. Mantém posição, tamanho e cor; quando a fonte embutida não tem alguma letra nova, usa a fonte padrão mais parecida.
- Desfazer e refazer (Ctrl/Cmd+Z), mover, redimensionar e mudar cores de tudo.
- Ao salvar, as anotações podem ficar editáveis em outros programas ou ser incorporadas ao papel.

**Assinar**
- Assinatura desenhada, digitada (com fontes manuscritas) ou de uma foto (o fundo branco sai sozinho). Até 6 assinaturas guardadas, se você quiser.
- **Assinatura digital com certificado A1** (.pfx ou .p12, como e-CPF e e-CNPJ da ICP-Brasil), visível ou invisível, no padrão PAdES (ETSI.CAdES.detached). Abre como válida no Adobe Reader, no Poppler e em validadores PAdES. O arquivo do certificado e a senha ficam só na memória enquanto o app está aberto.

**Formulários**
- Preenche campos de texto, caixas de seleção, botões de opção e listas, direto na página.

**Páginas**
- Juntar vários PDFs e imagens, reordenar arrastando, girar, duplicar, apagar, inserir página em branco, extrair e dividir em vários arquivos.
- Marca d'água, numeração de páginas, cabeçalho e rodapé (com número, total, data e nome do arquivo).

**Proteger e entregar**
- **Tarja definitiva**: o que fica sob a tarja deixa de existir no arquivo (a página vira imagem e as informações ocultas são removidas), não é só um retângulo preto por cima.
- Senha para abrir (AES-256), remoção de metadados (autor, programa, datas) e compressão em três níveis.
- Imagens (JPG, PNG, TIFF, WebP...) viram PDF; páginas viram imagens; texto vira .txt.

**Reconhecer e comparar**
- **OCR sem internet** (Tesseract 5, português e inglês): PDF escaneado vira pesquisável e copiável, com a aparência intacta. Detecta e corrige páginas de lado ou de cabeça para baixo.
- **Comparar dois PDFs**: texto que entrou, saiu ou mudou, lado a lado, e diferenças visuais página a página.

**Abrir com dois cliques**: o instalador registra o Bravo PDF em "Abrir com" para arquivos .pdf, sem tomar o lugar do seu leitor padrão. Você escolhe se quer usá-lo como padrão.

Atalhos: V selecionar, H mão, E editar texto, T texto, M marca-texto, N nota, P caneta, R retângulo, L linha, A seta, S assinatura, Delete apaga, Ctrl/Cmd+F busca, Ctrl/Cmd+S salva, Ctrl/Cmd+P imprime.

## Instalar

| Seu computador | Arquivo | Como instalar |
|---|---|---|
| **Windows 10 ou 11** (64 bits) | `BravoPDF-Instalador-Windows.exe` | Dê dois cliques e siga o assistente. Não pede senha de administrador. |
| **Mac com chip Apple** (M1, M2, M3...) | `BravoPDF-macOS-AppleSilicon.dmg` | Abra o arquivo e arraste o Bravo PDF para Aplicativos. |
| **Mac com Intel** | `BravoPDF-macOS-Intel.dmg` | Abra o arquivo e arraste o Bravo PDF para Aplicativos. |
| **Ubuntu, Debian, Mint** (64 bits) | `BravoPDF-Linux-amd64.deb` | Dê dois cliques para abrir na central de programas, ou rode `sudo apt install ./BravoPDF-Linux-amd64.deb`. |
| **Outras distribuições Linux** (64 bits) | `BravoPDF-Linux-x86_64.tar.gz` | Extraia e rode `sh instalar.sh` na pasta. Instala só para o seu usuário, sem root. |

Cada instalador já traz tudo o que o app precisa, inclusive o Python e os modelos do OCR: a instalação também funciona sem internet. Abra o **Bravo PDF** pelo menu Iniciar ou pelo atalho na Área de Trabalho (Windows), pelo Launchpad (Mac) ou pelo menu de aplicativos (Linux). Ele não inicia sozinho com o computador.

Requisitos: Windows 10 ou 11 de 64 bits; macOS 11.3 ou mais novo (o OCR precisa do macOS 15 ou mais novo, porque a biblioteca do Tesseract só é publicada para ele; nos anteriores, o resto do app funciona normalmente); Linux x86_64 com glibc 2.28 ou mais novo (Ubuntu 20.04, Debian 10 ou posteriores).

**Avisos normais na primeira vez.** Os instaladores ainda não têm assinatura digital paga (Microsoft e Apple cobram por ela), então o sistema avisa:
- Windows: em "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**.
- Mac: ao abrir, o macOS diz que não pôde verificar o app. Vá em **Ajustes do Sistema > Privacidade e Segurança**, role até o aviso do Bravo PDF e clique em **Abrir Mesmo Assim**. É uma vez só.

### Desinstalar

- Windows: Configurações > Aplicativos > Bravo PDF > Desinstalar. Ele pergunta se você quer apagar também as preferências.
- Mac: arraste o app para o Lixo. As preferências ficam em `~/Library/Application Support/Bravo PDF`; apague a pasta se quiser.
- Linux: `sudo apt remove bravo-pdf` (pacote .deb) ou `sh ~/.local/share/bravo-pdf-app/desinstalar.sh` (versão portátil).

## Onde ficam os dados

| Sistema | Pasta |
|---|---|
| Windows | `%LOCALAPPDATA%\Bravo PDF` |
| macOS | `~/Library/Application Support/Bravo PDF` |
| Linux | `~/.local/share/bravo-pdf` |

O Bravo PDF **não guarda cópia dos seus documentos**. Dentro da pasta ficam só `preferencias.json` (tema, zoom e as assinaturas desenhadas que você escolheu guardar) e `sessao/`, com as cópias temporárias dos PDFs abertos, que é esvaziada ao fechar cada documento, ao fechar o app e ao abrir de novo. Senhas de PDF e certificados digitais nunca são gravados.

## Segurança

- **Sem internet.** Um bloqueio no próprio Python (`sys.addaudithook`, da biblioteca padrão) recusa qualquer conexão, resolução de nome ou pedido HTTP para fora do computador, no servidor e nos processos que leem os PDFs. A página tem Content-Security-Policy que só permite o próprio app. No Windows e no Linux, a janela abre com perfil próprio, sem extensões nem sincronização, e com todo endereço externo apontado para um proxy inexistente. No Mac, a janela recusa qualquer endereço que não seja o do app, e links dentro de PDFs não são seguidos.
- **Sem porta exposta.** O servidor escuta só em 127.0.0.1, numa porta livre escolhida a cada abertura, e desliga quando a janela fecha.
- **Chave por sessão.** Ao abrir, o app recebe do servidor uma chave de uso único (por um canal privado entre os dois processos) e troca por um cookie de sessão `HttpOnly` e `SameSite=Strict`. Sem ele, o servidor não entrega nada, nem para outros programas ou usuários do mesmo computador. Gravações também exigem a mesma origem e um cabeçalho próprio, e o cabeçalho `Host` é conferido.
- **PDF isolado.** Os PDFs são lidos e gerados em processos separados, com tempo e memória limitados: um arquivo malicioso ou quebrado não derruba o app. Formulários são desenhados sem executar JavaScript de PDF.
- **Senhas e certificados só na memória.** A senha do PDF e o certificado digital passam pelos cabeçalhos da página para o servidor local e pela entrada padrão do processo de trabalho, nunca pela linha de comando, e não são gravados.
- **Tarja de verdade.** A página tarjada é refeita como imagem e o conteúdo antigo, campos e informações ocultas são removidos do arquivo. Os testes conferem que o texto sob a tarja não aparece mais nos bytes do PDF.
- **Sem permissões extras.** O app não pede acesso a Documentos, Downloads, iCloud, Google Drive nem a outros apps. Você escolhe o arquivo e onde salvar nas janelas do próprio sistema.
- **Dependências fixas.** O Python embutido, cada biblioteca e os modelos do OCR têm versão fixa e hash SHA-256 conferido na construção (`ferramentas/versoes.sh` e `app/requirements.txt`). Uma trava impede que PDFs, certificados ou preferências entrem num instalador.

## Limites conhecidos

- Assinatura digital: só certificado A1 em arquivo (.pfx/.p12). Certificado A3 (token USB ou cartão) ainda não. A assinatura não inclui o atributo de política da ICP-Brasil nem consulta de revogação (que exigiria internet); validadores mostram a assinatura como íntegra e, para certificados ICP-Brasil, a cadeia é conferida pelo próprio validador.
- Editar texto original: funciona trecho a trecho. Se a fonte embutida no PDF não tiver alguma letra nova, o trecho passa para a fonte padrão mais parecida (Helvetica, Times ou Courier).
- OCR: português e inglês. Em Macs com macOS anterior ao 15, fica indisponível.

## Como funciona

```
app/
  server.py          servidor HTTP local (biblioteca padrão do Python)
  blindagem.py       bloqueio de rede
  motor.py           processo de trabalho isolado (ver, buscar, salvar, OCR, assinar...)
  pdf_montar.py      monta o PDF final: páginas, anotações, formulários, tarjas, senha, compressão
  pdf_anotacoes.py   anotações (aparência própria em PDF, editáveis ou incorporadas)
  pdf_formularios.py campos de formulário
  pdf_paginas.py     marca d'água, numeração, cabeçalho e rodapé
  pdf_texto.py       busca e edição do texto original (PDFium)
  pdf_ocr.py         OCR com Tesseract (camada de texto invisível)
  pdf_assinar.py     assinatura digital PAdES e conferência
  pdf_comparar.py    comparação de texto e visual
  pdf_desenho.py     geometria e desenho em PDF
  abrir.py           abre a janela no Windows e no Linux
  public/            a página (HTML, CSS e JS, sem bibliotecas de fora)
instaladores/
  windows/           instalador .exe (NSIS), com "Abrir com" para .pdf
  macos/             app nativo (Swift + WebKit) e textos do .dmg
  linux/             atalho, lançador e instalador da versão portátil
ferramentas/         construção dos instaladores, ícone e requirements com hashes
tests/               testes do motor e de segurança, com PDFs fictícios
```

### Desenvolvimento

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install --require-hashes --only-binary=:all: -r app/requirements.txt
pip install reportlab                     # só para gerar os PDFs de teste
bash ferramentas/baixar-tessdata.sh       # modelos do OCR (com hash conferido)
BRAVO_DADOS=/tmp/bravo-pdf-teste python app/abrir.py
python -m unittest discover tests
```

### Construir os instaladores

```bash
bash ferramentas/construir-windows.sh   # Linux ou Mac, precisa do NSIS (makensis)
bash ferramentas/construir-linux.sh     # Linux, precisa do dpkg-deb
bash ferramentas/construir-macos.sh     # Mac, precisa das Command Line Tools da Apple
```

Os arquivos saem em `dist/`.

## Licença

MIT. Veja [LICENSE](LICENSE).

Componentes incluídos nos instaladores, todos com licenças compatíveis com a MIT:

| Componente | Uso | Licença |
|---|---|---|
| Python 3.13 | linguagem | PSF |
| [pypdf](https://github.com/py-pdf/pypdf) | estrutura do PDF | BSD-3-Clause |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) / PDFium (Google) | ver, buscar e editar texto | Apache-2.0 / BSD-3-Clause |
| [Pillow](https://python-pillow.org) | imagens | MIT-CMU |
| [cryptography](https://cryptography.io) | certificado digital e AES-256 | Apache-2.0 / BSD |
| [asn1crypto](https://github.com/wbond/asn1crypto) | estrutura da assinatura (CMS) | MIT |
| [tesserocr](https://github.com/sirfz/tesserocr) | ligação com o Tesseract | MIT |
| [Tesseract 5](https://github.com/tesseract-ocr/tesseract) e modelos `tessdata` | OCR | Apache-2.0 |

O app não usa o MuPDF/PyMuPDF (AGPL).
