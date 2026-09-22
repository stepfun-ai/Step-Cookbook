# Claude Key Setup — 中文版

[English version](../en/README.md) · [返回仓库首页](../README.md)

快速配置 Claude Code 的 StepFun API Key 和端点设置。

## 特性

- ✅ 支持 2 种 StepFun 接入方式（官方 API、Step Plan）
- ✅ 自动检测 Claude Code 配置位置
- ✅ 自动创建基础配置文件（如果不存在）
- ✅ 前置条件检查（jq、bash/PowerShell、配置）
- ✅ 交互式菜单，简单易用
- ✅ 自动备份原配置
- ✅ 隐藏 API Key 输入，限制新配置、备份和临时文件的访问权限
- ✅ 仅替换 `env`，保留 `hooks`、`theme`、插件等其他配置
- ✅ 默认使用 `step-5-preview`，支持自定义模型名称
- ✅ 跨平台支持（macOS、Linux、Windows）

## 快速开始

### macOS / Linux（Bash）
```bash
curl -fsSL https://raw.githubusercontent.com/Zgh332358/claude-key-setup/main/zh-CN/configure_claude.sh -o configure_claude.sh
chmod +x configure_claude.sh
bash configure_claude.sh
```

### Windows（普通 PowerShell）

使用当前用户的普通 PowerShell 即可，无需管理员权限。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
irm https://raw.githubusercontent.com/Zgh332358/claude-key-setup/main/zh-CN/configure_claude.ps1 -OutFile configure_claude.ps1
.\configure_claude.ps1
```

### 指定配置文件路径
```bash
# macOS/Linux
bash configure_claude.sh -c /path/to/settings.json

# Windows PowerShell
.\configure_claude.ps1 -c C:\path\to\settings.json
```

显式指定的路径会始终被使用；文件或父目录不存在时自动创建，不会回退到另一份默认配置。也支持 `-c settings.json` 这样的相对路径。路径不可用或不可写时会报错退出。

## 支持模式

| 选项 | 模式 | Base URL | 说明 | API Key 获取 |
|------|------|----------|------|-------------|
| 1 | StepFun 官方 API | `https://api.stepfun.com` | 按量计费 | https://platform.stepfun.com/interface-key |
| 2 | StepFun Step Plan | `https://api.stepfun.com/step_plan` | 订阅制 | https://platform.stepfun.com/interface-key |

## 前置条件

### 必需
- **bash** (macOS/Linux) 或 **Windows PowerShell 5.1 / PowerShell 7** (Windows)
- **jq**（仅 Bash 版本需要，用于安全更新 JSON；PowerShell 使用内置 JSON 支持）

- **Claude Code** - 已安装 CLI 工具

### 可选
- **配置文件** - 如果不存在，脚本会自动创建

## 配置文件位置

| 系统 | 配置文件路径 |
|------|-------------|
| macOS/Linux | `~/.claude/settings.json` |
| Windows | `%USERPROFILE%\.claude\settings.json` |

如果配置文件不存在，脚本会自动创建。

## 配置流程

1. ✅ 检查前置条件（bash/PowerShell、环境）
2. ✅ 查找/创建配置文件
3. ✅ 显示菜单（StepFun 两个选项）
4. ✅ 输入 API Key（隐藏输入内容）
5. ✅ 输入模型名称（默认 `step-5-preview`，可回车跳过；也可输入 `step-3.5-flash` 等其他模型名称）
6. ✅ 备份原配置
7. ✅ 仅替换配置中的 `env`，保留其他字段
8. ✅ 提示重启 Claude Code

## 使用示例

```bash
# macOS/Linux
bash configure_claude.sh

# 选择 1 (StepFun 官方 API)
# 输入 API Key: sk-xxx
# 模型名称: step-5-preview (或回车使用默认)
```

```powershell
# Windows PowerShell
.\configure_claude.ps1

# 选择 1 (StepFun 官方 API)
# 输入 API Key: sk-xxx
# 模型名称: step-5-preview (或回车使用默认)
```

## 脚本说明

仓库包含两个脚本：
- `configure_claude.sh` - Bash 版本（macOS、Linux、WSL）
- `configure_claude.ps1` - PowerShell 版本（Windows）

两个脚本功能完全相同，只是针对不同平台做了适配。

## 配置结构

脚本会读取原有 `settings.json`，仅替换整个 `env` 对象，写入以下字段：
- `env.ANTHROPIC_AUTH_TOKEN` - API Key
- `env.ANTHROPIC_BASE_URL` - API 端点
- `env.ANTHROPIC_MODEL` - 默认模型
- `env.ANTHROPIC_SMALL_FAST_MODEL` - 快速模型
- `env.ANTHROPIC_DEFAULT_SONNET_MODEL` - Sonnet 模型
- `env.ANTHROPIC_DEFAULT_OPUS_MODEL` - Opus 模型
- `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` - Haiku 模型

`env` 之外的所有字段（例如 `hooks`、`theme`、`model`、`statusLine`、`permissions` 和插件配置）都会保留。旧 `env` 内的其他环境变量会被移除；JSON 的缩进格式可能调整。

脚本会在替换已有配置前备份原文件，并先生成完整的新 JSON。如果配置不是有效的 JSON 对象或生成失败，会报错退出并保留原文件。新建配置只包含 `env`，不会额外设置顶层 `model`。

Bash 版本会保留配置文件的软链接并更新其目标。PowerShell 版本遇到符号链接或其他重解析点配置时会停止更新，请使用 `-ConfigPath` 指定实际目标文件。

## 凭据保护

- API Key 输入不回显，完成提示只显示“已配置”。Bash 通过标准输入向 jq 传递 Key，不将 Key 放入进程命令行参数，并取消 `API_KEY` 的导出以防新密钥被子进程继承。
- Bash 新建的配置、备份和临时文件权限为 `0600`，新建目录权限为 `0700`；已有父目录权限保持原样。
- Windows 使用受限 ACL 创建凭据文件，只允许当前用户和 SYSTEM 访问；无法安全设置文件权限时停止写入。
- 备份使用随机后缀，避免重复运行覆盖同名备份；历史备份不会自动删除或更改权限。
- `settings.json` 及备份仍包含可用的 API Key，请勿将它们提交到仓库或公开分享。

## 回归测试

以下测试命令需在仓库根目录执行。在 macOS/Linux 上使用 Python 3 和 jq 运行，覆盖中英文两个版本：

```bash
python3 -B -m unittest discover -s tests -v
```

测试使用临时配置文件和测试 API Key，验证字段保留、模型选择、备份、JSON 转义、无效配置保护、软链接更新，以及隐藏输入、进程参数、文件权限、相对路径和失败清理，不会修改当前用户的 Claude 配置。

Windows 上可分别在普通 Windows PowerShell 5.1 和 PowerShell 7 中运行原生测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_configure_claude.ps1 -Language zh-CN
pwsh -NoProfile -File .\tests\test_configure_claude.ps1 -Language zh-CN
```

Windows 测试需要支持 ACL 的文件系统，仅使用临时目录和假 Key，检查 JSON 更新、备份内容、私有 ACL、文件名冲突和失败时的数据保护。

## License

MIT License
