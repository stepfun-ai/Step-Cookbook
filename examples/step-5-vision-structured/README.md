# Step 5 Preview 图像理解与结构化输出 · 独立一键运行版

本包包含这一篇的完整文章、可编辑脚本、启动文件和环境准备程序，可以单独下载到任意可写目录使用。

## 双击开始

1. 解压整个文件夹。
2. macOS 双击 [启动.command](启动.command)；Windows x64 双击 [启动.bat](启动.bat)。首次会下载本篇专用 Python 3.12.14 并准备依赖，后续复用本包环境。
3. 直接选“最小示例”或“完整实验”，随后隐藏输入自己的 API Key。默认中国站，国际站用户先按 `R` 切换。

首次准备环境需要能访问 GitHub／Astral 与 PyPI 的网络，无需预装 Python 或 Jupyter。运行 Demo 时需要相应模型权限和账户额度。密钥只从隐藏输入或 `STEPFUN_API_KEY` 环境变量读取，不保存到文件。

- **最小示例：** 1 次图像请求。
- **完整实验：** 3 次图像请求，包含缺失字段和替换输入。

## 阅读、调参与复用

- [完整中文 Cookbook](zh-CN/README.md)：模型介绍、完整代码、参数解释和迁移方法均在同一篇中。
- [English Cookbook](en/README.md)：与中文正文对应的英文技术文档；示例输入与参数保持一致。
- [可编辑 Python 脚本](./vision_demo.py)：参数沿用文章分组，保存修改后再次双击运行。
- [可选 Notebook](./02_Step5_图像理解与结构化输出.ipynb)：按需要使用。

样例素材保存在本包 `assets/` 中。 每次运行的 JSON／WAV 结果保存到本包的 `outputs/` 子目录。

也可以在本包目录的终端直接运行：

```bash
# macOS：首次双击准备环境后
.venv/bin/python vision_demo.py
.venv/bin/python vision_demo.py --full
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe vision_demo.py
.\.venv\Scripts\python.exe vision_demo.py --full
```

## 独立运行的范围

本包自行创建 `.runtime/`（解释器与缓存）、`.venv/`（环境）和 `outputs/`（结果），全部位于本包内部。你可以只保留这一份，将整个文件夹移动或发给别人使用；首次移动后启动器会自动恢复环境路径。分享时优先使用原始 ZIP。

本篇只使用 Python 标准库，无需安装语音设备或 WebSocket 依赖。

启动入口覆盖 macOS Apple Silicon／Intel 和 Windows x64。首次打开下载的脚本时，按操作系统提示允许打开可信文件。
