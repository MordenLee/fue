!macro customUnInstallSection
  # Optional checkbox shown on the uninstall components page.
  # Only when this section is selected will local app data be removed.
  Section /o "删除本地数据（聊天记录与知识库）" un.DeleteAppData
    SetShellVarContext current
    RMDir /r "$APPDATA\fue\backend-data"
    RMDir /r "$APPDATA\fue\logs"
    RMDir /r "$APPDATA\fue\pycache"
    RMDir "$APPDATA\fue"
  SectionEnd
!macroend
