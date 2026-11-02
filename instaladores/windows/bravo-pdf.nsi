; Instalador do Bravo PDF para Windows 10 e 11 (64 bits).
; Gerado por ferramentas/construir-windows.sh com o NSIS (makensis).
; - Instala só para o usuário atual, sem pedir administrador.
; - Traz o Python oficial e as bibliotecas: não usa a internet.
; - Não configura nada para iniciar com o Windows.
; - Registra o Bravo PDF como opção de "Abrir com" para PDFs (sem tomar o lugar
;   do leitor padrão: quem escolhe é a pessoa, em Configurações > Aplicativos padrão).
Unicode true
ManifestDPIAware true
RequestExecutionLevel user
SetCompressor /SOLID lzma

!ifndef VERSAO
  !error "Defina VERSAO"
!endif
!ifndef ORIGEM
  !error "Defina ORIGEM (pasta com python\ e app\)"
!endif
!ifndef SAIDA
  !error "Defina SAIDA"
!endif

!define NOME "Bravo PDF"
!define PROGID "BravoPDF.Documento"
!define CLASSES "Software\Classes"
!define CHAVE_DESINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\BravoPDF"

Name "${NOME}"
OutFile "${SAIDA}"
InstallDir "$LOCALAPPDATA\Programs\${NOME}"
BrandingText "${NOME} ${VERSAO}"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${VERSAO}.0"
VIAddVersionKey "ProductName" "${NOME}"
VIAddVersionKey "FileDescription" "Instalador do ${NOME}"
VIAddVersionKey "FileVersion" "${VERSAO}"
VIAddVersionKey "ProductVersion" "${VERSAO}"
VIAddVersionKey "LegalCopyright" "Licença MIT"

!include "MUI2.nsh"
!include "x64.nsh"
!define MUI_ICON "${ORIGEM}\app\icone\bravo-pdf.ico"
!define MUI_UNICON "${ORIGEM}\app\icone\bravo-pdf.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Este assistente vai instalar o ${NOME} ${VERSAO}.$\r$\n$\r$\nO ${NOME} funciona inteiramente no seu computador, sem internet e sem conta. Seus documentos nunca saem daqui.$\r$\n$\r$\nClique em Avançar para continuar."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o ${NOME} agora"
!define MUI_FINISHPAGE_RUN_FUNCTION AbrirAgora

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${ORIGEM}\LICENCA.txt"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "O ${NOME} precisa do Windows 10 ou 11 de 64 bits."
    Abort
  ${EndIf}
FunctionEnd

Function AbrirAgora
  ExecShell "" "$SMPROGRAMS\${NOME}.lnk"
FunctionEnd

Section "Instalar"
  SetShellVarContext current
  ; Versão anterior: troca os arquivos do programa (os dados ficam em outra pasta e são mantidos).
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  SetOutPath "$INSTDIR"
  File /r "${ORIGEM}\python"
  File /r "${ORIGEM}\app"
  File "${ORIGEM}\LICENCA.txt"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"

  CreateShortCut "$SMPROGRAMS\${NOME}.lnk" "$INSTDIR\python\pythonw.exe" '-I -s "$INSTDIR\app\abrir.py"' \
    "$INSTDIR\app\icone\bravo-pdf.ico" 0 SW_SHOWNORMAL "" "${NOME}"
  CreateShortCut "$DESKTOP\${NOME}.lnk" "$INSTDIR\python\pythonw.exe" '-I -s "$INSTDIR\app\abrir.py"' \
    "$INSTDIR\app\icone\bravo-pdf.ico" 0 SW_SHOWNORMAL "" "${NOME}"

  ; "Abrir com" para .pdf (só no usuário atual; nada de administrador).
  WriteRegStr HKCU "${CLASSES}\${PROGID}" "" "Documento PDF"
  WriteRegStr HKCU "${CLASSES}\${PROGID}\DefaultIcon" "" "$INSTDIR\app\icone\bravo-pdf.ico"
  WriteRegStr HKCU "${CLASSES}\${PROGID}\shell\open\command" "" '"$INSTDIR\python\pythonw.exe" -I -s "$INSTDIR\app\abrir.py" "%1"'
  WriteRegStr HKCU "${CLASSES}\.pdf\OpenWithProgids" "${PROGID}" ""
  WriteRegStr HKCU "Software\BravoPDF\Capabilities" "ApplicationName" "${NOME}"
  WriteRegStr HKCU "Software\BravoPDF\Capabilities" "ApplicationDescription" "Editor de PDF que funciona sem internet"
  WriteRegStr HKCU "Software\BravoPDF\Capabilities\FileAssociations" ".pdf" "${PROGID}"
  WriteRegStr HKCU "Software\RegisteredApplications" "${NOME}" "Software\BravoPDF\Capabilities"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'

  WriteRegStr HKCU "${CHAVE_DESINST}" "DisplayName" "${NOME}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "Publisher" "${NOME}"
  WriteRegStr HKCU "${CHAVE_DESINST}" "DisplayIcon" "$INSTDIR\app\icone\bravo-pdf.ico"
  WriteRegStr HKCU "${CHAVE_DESINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_DESINST}" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegStr HKCU "${CHAVE_DESINST}" "QuietUninstallString" '"$INSTDIR\Desinstalar.exe" /S'
  WriteRegDWORD HKCU "${CHAVE_DESINST}" "NoModify" 1
  WriteRegDWORD HKCU "${CHAVE_DESINST}" "NoRepair" 1
  WriteRegDWORD HKCU "${CHAVE_DESINST}" "EstimatedSize" ${TAMANHO_KB}
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\${NOME}.lnk"
  Delete "$DESKTOP\${NOME}.lnk"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\LICENCA.txt"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${CHAVE_DESINST}"
  DeleteRegKey HKCU "${CLASSES}\${PROGID}"
  DeleteRegValue HKCU "${CLASSES}\.pdf\OpenWithProgids" "${PROGID}"
  DeleteRegKey HKCU "Software\BravoPDF"
  DeleteRegValue HKCU "Software\RegisteredApplications" "${NOME}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
  ; Os dados só são apagados se a pessoa pedir (no modo silencioso, ficam guardados).
  IfFileExists "$LOCALAPPDATA\${NOME}\*.*" 0 fim
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
      "Apagar também suas preferências e assinaturas guardadas do ${NOME}?$\r$\n$\r$\nEscolha Não para guardá-las caso instale de novo." \
      /SD IDNO IDNO fim
    RMDir /r "$LOCALAPPDATA\${NOME}"
  fim:
SectionEnd
