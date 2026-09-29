# Step 5 Preview 工具调用 · 独立一键运行版

本包包含这一篇的完整文章、可编辑脚本、启动文件和环境准备程序，可以单独下载到任意可写目录使用。

## 双击开始

1. 解压整个文件夹。
2. macOS 双击 [启动.command](启动.command)；Windows x64 双击 [启动.bat](启动.bat)。首次会下载本篇专用 Python 3.12.14 并准备依赖，后续复用本包环境。
3. 直接选“最小示例”或“完整实验”，随后隐藏输入自己的 API Key。默认中国站，国际站用户先按 `R` 切换。

首次准备环境需要能访问 GitHub／Astral 与 PyPI 的网络，无需预装 Python 或 Jupyter。运行 Demo 时需要相应模型权限和账户额度。密钥只从隐藏输入或 `STEP_API_KEY` 环境变量读取，不保存到文件。

- **最小示例：** 1 个计算任务，最多 5 轮请求。
- **完整实验：** 3 个任务，每个最多 5 轮请求。

## 阅读、调参与复用

配套 Python 脚本与 Notebook 对应中文版。

- [完整中文 Cookbook](zh-CN/README.md)：模型介绍、完整代码、参数解释和迁移方法均在同一篇中。
- [English Cookbook](en/README.md)：介绍相同的模型能力和主要流程；示例输入、输出字段和校验细节可能不同，请以所读版本为准。
- [可编辑 Python 脚本](./tool_demo.py)：参数沿用文章分组，保存修改后再次双击运行。
- [可选 Notebook](./03_Step5_工具调用.ipynb)：按需要使用。

本篇无需额外素材包。 每次运行的 JSON／WAV 结果保存到本包的 `outputs/` 子目录。

也可以在本包目录的终端设置 `STEP_API_KEY` 后直接运行。将 `YOUR_STEP_API_KEY` 替换为自己的密钥，并在同一终端执行下方命令；未设置时仍会隐藏询问密钥。

```bash
# macOS：首次双击准备环境后
export STEP_API_KEY="YOUR_STEP_API_KEY"
.venv/bin/python tool_demo.py
.venv/bin/python tool_demo.py --full
```

```powershell
# Windows PowerShell
$env:STEP_API_KEY = "YOUR_STEP_API_KEY"
.\.venv\Scripts\python.exe tool_demo.py
.\.venv\Scripts\python.exe tool_demo.py --full
```

## 独立运行的范围

本包自行创建 `.runtime/`（解释器与缓存）、`.venv/`（环境）和 `outputs/`（结果），全部位于本包内部。你可以只保留这一份，将整个文件夹移动或发给别人使用；首次移动后启动器会自动恢复环境路径。分享时优先使用原始 ZIP。

本篇只使用 Python 标准库，无需安装语音设备或 WebSocket 依赖。

启动入口覆盖 macOS Apple Silicon／Intel 和 Windows x64。首次打开下载的脚本时，按操作系统提示允许打开可信文件。
