# Claude Key Setup

Configure Claude Code to use a StepFun API key and endpoint.

This folder contains the standalone English scripts. The [Chinese version](../zh-CN/README.md) provides the same functionality.

## Features

- Two StepFun connection options: the Official API and Step Plan
- Automatic detection of Claude Code configuration files
- Creation of a configuration file when none exists
- Prerequisite checks for Bash / PowerShell, jq, and configuration files
- Interactive setup with a hidden API key prompt
- Automatic backups of existing configuration files
- Restricted access to new configuration files, backups, and temporary files
- Replacement of only `env`, preserving `hooks`, `theme`, plugin settings, and other fields
- `step-5-preview` as the default model, with support for custom model names
- Support for macOS, Linux, WSL, and Windows

## Quick start

### macOS / Linux / WSL (Bash)

```bash
curl -fsSL https://raw.githubusercontent.com/Zgh332358/claude-key-setup/main/en/configure_claude.sh -o configure_claude.sh
chmod +x configure_claude.sh
bash configure_claude.sh
```

### Windows (PowerShell)

Run the script in a regular PowerShell session as your current user. Administrator privileges are not required.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
irm https://raw.githubusercontent.com/Zgh332358/claude-key-setup/main/en/configure_claude.ps1 -OutFile configure_claude.ps1
.\configure_claude.ps1
```

### Use a custom configuration path

```bash
# macOS / Linux / WSL
bash configure_claude.sh -c /path/to/settings.json
```

```powershell
# Windows PowerShell
.\configure_claude.ps1 -c C:\path\to\settings.json
```

An explicitly supplied path is always used. The script creates the file and its parent directories if needed; it does not fall back to another default configuration. Relative paths such as `-c settings.json` are also supported. The script exits with an error if the path is invalid or cannot be written.

## Connection options

| Option | Connection | Base URL | Billing | API keys |
| --- | --- | --- | --- | --- |
| 1 | StepFun Official API | `https://api.stepfun.ai/` | Pay as you go | [StepFun console](https://platform.stepfun.ai/interface-key) |
| 2 | StepFun Step Plan | `https://api.stepfun.ai/step_plan` | Subscription | [StepFun console](https://platform.stepfun.ai/interface-key) |

## Prerequisites

- **Bash** on macOS / Linux / WSL, or **Windows PowerShell 5.1 / PowerShell 7** on Windows
- **jq** for the Bash script, used to update JSON safely; PowerShell uses its built-in JSON support
- **Claude Code** installed

An existing configuration file is optional. The script creates one when needed.

## Default configuration locations

| System | Configuration file |
| --- | --- |
| macOS / Linux / WSL | `~/.claude/settings.json` |
| Windows | `%USERPROFILE%\.claude\settings.json` |

The script also checks for `settings.local.json` if it does not find `settings.json`. Use `-c` to select a specific file.

## Setup workflow

1. Check prerequisites.
2. Locate the configuration file, or prepare to create one.
3. Choose the StepFun Official API or Step Plan.
4. Enter your API key; the input is hidden.
5. Enter a model name, or press Enter to use `step-5-preview`. Other names, such as `step-3.5-flash`, can also be entered.
6. Back up the existing configuration.
7. Replace the entire `env` object while preserving other fields.
8. Restart Claude Code to apply the changes.

## Examples

```bash
# macOS / Linux / WSL
bash configure_claude.sh

# Select 1 for the StepFun Official API.
# Enter your API key when prompted; it will not be displayed.
# Enter step-5-preview, or press Enter to accept the default.
```

```powershell
# Windows PowerShell
.\configure_claude.ps1

# Select 1 for the StepFun Official API.
# Enter your API key when prompted; it will not be displayed.
# Enter step-5-preview, or press Enter to accept the default.
```

## Included scripts

- `configure_claude.sh`: Bash version for macOS, Linux, and WSL
- `configure_claude.ps1`: PowerShell version for Windows

Both scripts perform the same configuration task, with file handling adapted to each platform.

## Configuration changes

The scripts read the existing `settings.json` and replace its entire `env` object with these fields:

| Field | Value |
| --- | --- |
| `env.ANTHROPIC_AUTH_TOKEN` | Your API key |
| `env.ANTHROPIC_BASE_URL` | The selected API endpoint |
| `env.ANTHROPIC_MODEL` | The selected model |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | The selected model |
| `env.ANTHROPIC_DEFAULT_SONNET_MODEL` | The selected model |
| `env.ANTHROPIC_DEFAULT_OPUS_MODEL` | The selected model |
| `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` | The selected model |

All fields outside `env` are preserved, including `hooks`, `theme`, `model`, `statusLine`, `permissions`, and plugin settings. Any additional variables previously stored inside `env` are removed. JSON indentation may change.

Before replacing an existing file, the scripts create a backup and generate the complete updated JSON. If the original file is not a valid JSON object or generation fails, the scripts stop and preserve the original file. A newly created configuration contains only `env`; the scripts do not add a top-level `model` field.

The Bash script preserves configuration symlinks and updates their targets. The PowerShell script rejects symbolic links and other reparse points; use `-ConfigPath` to specify the actual target file.

PowerShell rejects configurations that cannot be safely serialized, including nesting beyond its supported depth of 100 and date values automatically converted by older PowerShell versions. An error leaves the original configuration in place.

## Credential protection

- API key input is hidden, and the completion message displays only `Configured`. Bash passes the key to jq through standard input, keeping it out of process command-line arguments and the inherited `API_KEY` environment of child processes.
- Bash creates configuration files, backups, and temporary files with `0600` permissions, and new directories with `0700` permissions. Existing parent directory permissions are unchanged.
- Windows creates credential files with a private ACL granting access only to the current user and SYSTEM. If these permissions cannot be applied and verified, writing stops.
- Backup filenames include random suffixes to avoid overwriting previous backups. Historical backups are not automatically deleted or assigned new permissions.
- Configuration files and backups contain usable API keys. Do not commit them to a repository or share them publicly.

## Regression tests

Run the Bash regression suite from the repository root on macOS / Linux with Python 3 and jq:

```bash
python3 -B -m unittest discover -s tests -v
```

To run only the English Bash tests:

```bash
python3 -B -m unittest discover -s tests -p test_configure_claude.py -k EnglishConfigureClaudeTests -v
```

The suite uses temporary configuration files and fake API keys. It checks preservation of existing fields, model selection, backups, JSON escaping, invalid-input protection, symlink handling, hidden key input, process arguments, file permissions, relative paths, and cleanup after failures. It does not modify your Claude configuration.

Run the native Windows tests from the repository root in a regular Windows PowerShell 5.1 or PowerShell 7 session:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_configure_claude.ps1 -Language en
pwsh -NoProfile -File .\tests\test_configure_claude.ps1 -Language en
```

Windows tests require a file system that supports ACLs. They use temporary directories and fake keys to check JSON updates, backup contents, private ACLs, filename conflicts, and data protection when operations fail.

## License

MIT License
