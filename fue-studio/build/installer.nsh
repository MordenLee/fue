!macro customUnInstall
  # Updates and silent uninstalls must not opt into removing shared components.
  ${IfNot} ${isUpdated}
  ${AndIfNot} ${Silent}
    SetShellVarContext current
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "是否同时卸载 FUE Core 及其 Python 运行环境？$\r$\n$\r$\n选择“是”：删除由 FUE 安装器管理的共享 Core；已安装的 Agent Skill 将无法使用，直到重新安装 Core。$\r$\n选择“否”：保留 Core，Agent Skill 可以继续使用。$\r$\n$\r$\n两种选择都会保留聊天记录、知识库及宿主中的 Skill 文件。" IDNO fue_keep_core
    nsExec::ExecToStack '"$INSTDIR\resources\python\python.exe" "$INSTDIR\resources\core\fue.py" installation remove-core --confirm'
    Pop $R0
    Pop $R1
    ${If} $R0 != 0
      MessageBox MB_OK|MB_ICONEXCLAMATION "Core 未能完全卸载。请先关闭使用 FUE 的宿主，等待 Core 空闲退出后重试；也可选择保留 Core 后继续卸载 Studio。$\r$\n资料库仍然保留。"
      Abort
    ${EndIf}
    fue_keep_core:
  ${EndIf}
!macroend

!macro customUnInstallSection
  # Core and workspace data can still be used by installed Agent skills.
  # Workspace deletion is separate from the Core removal choice above.
  Section /o "清理桌面日志与缓存（保留共享资料库）" un.DeleteAppData
    SetShellVarContext current
    RMDir /r "$APPDATA\fue\logs"
    RMDir /r "$APPDATA\fue\pycache"
    RMDir "$APPDATA\fue"
  SectionEnd
!macroend
