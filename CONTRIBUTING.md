# 贡献指南

感谢你愿意改进 TrayPocket。这个项目优先保持简单、可读、容易自行构建。

## 本地开发

1. 克隆仓库。
2. 修改 `src/TrayPocket.cs` 或文档文件。
3. 在项目目录运行：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\build.ps1
```

4. 手动运行 `TrayPocket.exe`，确认托盘菜单、隐藏窗口、恢复窗口和退出行为正常。

## 提交建议

- 不要提交 `TrayPocket.exe`、压缩包、日志、缓存、`.env` 或任何私人配置文件。
- 如果修改了用户可见行为，请同步更新 `README.md` 或 `CHANGELOG.md`。
- 如果参考了第三方项目或代码，请在 `THIRD_PARTY_NOTICES.md` 里说明来源和许可证。

## 代码风格

- 当前代码使用单文件 C# WinForms 实现，优先保持直接清晰。
- 注释用于解释 Windows API、托盘行为、线程切换等不够直观的地方。
- 新增功能要尽量避免引入重型依赖。
