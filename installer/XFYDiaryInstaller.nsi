Unicode true
!include "MUI2.nsh"

Name "XFY Diary"
OutFile "..\release\XFYDiary-Setup-v1.0.0.exe"
InstallDir "$LOCALAPPDATA\Programs\XFY Diary"
InstallDirRegKey HKCU "Software\XFYDiary" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_ICON "..\logo_done.ico"
!define MUI_UNICON "..\logo_done.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

LangString SecMainName ${LANG_SIMPCHINESE} "程序文件（必选）"
LangString SecDesktopName ${LANG_SIMPCHINESE} "创建桌面快捷方式"
LangString SecMainDesc ${LANG_SIMPCHINESE} "安装 XFY 日记程序文件。"
LangString SecDesktopDesc ${LANG_SIMPCHINESE} "在桌面创建快捷方式图标。"
LangString ShortcutUninstall ${LANG_SIMPCHINESE} "卸载 XFY Diary"

Section "-MainFiles" SecMain
  SetOutPath "$INSTDIR"
  File /r /x "diary.db" "..\dist\XFYDiary\*"

  CreateDirectory "$SMPROGRAMS\XFY Diary"
  CreateShortcut "$SMPROGRAMS\XFY Diary\XFY Diary.lnk" "$INSTDIR\XFYDiary.exe" "" "$INSTDIR\XFYDiary.exe" 0
  CreateShortcut "$SMPROGRAMS\XFY Diary\$(ShortcutUninstall).lnk" "$INSTDIR\Uninstall.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\XFYDiary" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary" "DisplayName" "XFY Diary"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary" "DisplayIcon" "$INSTDIR\XFYDiary.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary" "NoRepair" 1
SectionEnd

Section /o "$(SecDesktopName)" SecDesktop
  CreateShortcut "$DESKTOP\XFY Diary.lnk" "$INSTDIR\XFYDiary.exe" "" "$INSTDIR\XFYDiary.exe" 0
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\XFY Diary.lnk"
  Delete "$SMPROGRAMS\XFY Diary\XFY Diary.lnk"
  Delete "$SMPROGRAMS\XFY Diary\$(ShortcutUninstall).lnk"
  RMDir "$SMPROGRAMS\XFY Diary"

  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\XFYDiary"
  DeleteRegKey HKCU "Software\XFYDiary"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(SecDesktopDesc)
!insertmacro MUI_FUNCTION_DESCRIPTION_END
