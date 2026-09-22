# Claude Key Setup

Configure Claude Code for StepFun while preserving your existing settings.
为 Claude Code 配置 StepFun，并保留已有的其他设置。

| Language / 语言 | Folder / 目录 | Documentation / 说明 |
| --- | --- | --- |
| 简体中文 | [`zh-CN/`](zh-CN/) | [中文版说明](zh-CN/README.md) |
| English | [`en/`](en/) | [English instructions](en/README.md) |

Each folder contains standalone Bash and PowerShell scripts, with prompts, errors, and documentation in the selected language.
每个目录都包含独立运行的 Bash、PowerShell 脚本，以及完整的对应语言提示和说明。

```text
zh-CN/
  configure_claude.sh
  configure_claude.ps1
  README.md
en/
  configure_claude.sh
  configure_claude.ps1
  README.md
tests/
  test_configure_claude.py
  test_configure_claude.ps1
```

Both versions replace only the top-level `env` object, preserve settings such as `hooks` and `theme`, and default to `step-5-preview`. They support the StepFun API and Step Plan.
两种语言版本都只替换顶层 `env`，保留 `hooks`、`theme` 等其他字段，默认模型为 `step-5-preview`，支持官方 API 与 Step Plan。

API key input is hidden. Credentials are kept out of Bash subprocess arguments, and new configuration, backup, and temporary files use restricted permissions. Windows runs without requiring administrator privileges.
API Key 输入隐藏；Bash 子进程参数中不包含 Key；新配置、备份和临时文件限制访问权限。Windows 无需管理员权限。

## Compatibility / 兼容入口

The root-level `configure_claude.sh` and `configure_claude.ps1` are exact copies of the Chinese version, retained so existing download links continue to work. For new downloads, use the selected language folder.
根目录的两个脚本是中文版的完整副本，用于保留旧下载链接。新用户请使用对应语言目录中的版本。

## Development and tests / 维护与测试

Run tests from the repository root. All fixtures use temporary files and fake keys.
在仓库根目录执行；测试只使用临时文件和假 Key。

```bash
python3 -B -m unittest discover -s tests -v
```

```powershell
# Windows PowerShell 5.1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_configure_claude.ps1 -Language zh-CN
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_configure_claude.ps1 -Language en
# PowerShell 7 on Windows
pwsh -NoProfile -File .\tests\test_configure_claude.ps1 -Language zh-CN
pwsh -NoProfile -File .\tests\test_configure_claude.ps1 -Language en
```

GitHub Actions runs both Bash variants on Linux and macOS, and both language variants on Windows PowerShell 5.1 and PowerShell 7. The suite also checks that legacy root scripts match `zh-CN/` and English files contain no untranslated Chinese text.
GitHub Actions 在 Linux、macOS 上验证两个 Bash 版本，并在 Windows PowerShell 5.1、PowerShell 7 上分别验证两种语言版本。测试也检查根目录兼容副本与 `zh-CN/` 一致，以及英文文件没有遗漏的中文内容。

When changing behavior, update both language folders and copy the Chinese scripts to the root compatibility paths before running the full suite.
修改行为时同步更新两种语言版本，再将中文版脚本复制到根目录兼容路径，最后运行完整测试。

## License

MIT License
