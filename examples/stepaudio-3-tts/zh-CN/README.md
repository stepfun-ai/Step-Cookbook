# StepAudio 3 TTS：语速、发音控制与个性化音色复刻

**简体中文** | [English](../en/README.md)

> 中英文版本介绍相同的模型能力和主要流程；示例输入、提示词、输出字段和校验细节可能不同，请以所读版本的代码为准。配套 Python 脚本与 Notebook 对应中文版。

## 1. 认识文本转语音与个性化音色

StepAudio 3 TTS 是文本转语音模型：应用提供要朗读的文字与声音配置，接口返回合成音频。它支持普通合成和流式合成；本篇使用普通 HTTP 合成保存完整 WAV，便于复制到项目、播放和比较。[模型概览](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-tts)

几个参数分别承担不同职责：`voice` 决定声音身份，`speed` 控制语速，`pronunciation_map` 指定目标词的读法。个性化音色先由参考录音和逐字稿创建，随后在合成请求中作为 `voice` 使用。[语音合成接口](https://platform.stepfun.ai/docs/en/api-reference/audio/create-audio)

本篇面向需要在应用中生成语音的 Python 开发者。先合成一句话，再分别调整语速与读音，最后完成“上传自己的参考录音 → 创建音色 → 合成新文本”的全过程。

**本文路线：** 配置客户端 → 合成并保存 WAV → 按参数对照 → 创建个性化音色 → 接入项目。

## 2. 前置条件与环境准备

### 2.1 前置条件

**需要掌握：** Python 函数、字典与 JSON；了解一次请求如何返回结果。不要求预先接入特定开发框架。

**需要准备：**

- Python 3.10 或以上版本、一个终端和任意代码编辑器。
- [StepFun 开放平台](https://platform.stepfun.com/)账号，已创建 API Key，并确认可以调用 `stepaudio-3-tts`。
- 可以访问所用区域 API 的网络环境。真实调用会使用账户额度。
- 参考音频：个性化复刻部分使用随文 WAV 与逐字稿，保存到项目的 `assets/voice_reference/`。

### 2.2 创建 Python 环境

已有项目可以使用现有虚拟环境。新项目可在任意工作目录创建环境。macOS／Linux 终端执行：

```bash
mkdir stepfun-demo
cd stepfun-demo
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell 执行：

```powershell
mkdir stepfun-demo
cd stepfun-demo
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

激活后，用以下命令确认正在使用的 Python 版本。后文的 `python` 都指这个环境中的解释器。

```bash
python --version
```

### 2.3 安装本篇依赖

本篇请求和文件处理使用 Python 标准库，无需安装第三方 SDK。已经使用其他 HTTP 客户端的项目也可保留现有客户端，按正文提供的请求体接入。

### 2.4 配置密钥与运行方式

在运行示例的终端中设置 `STEP_API_KEY`，将 `YOUR_STEP_API_KEY` 替换为自己的 API 密钥。

macOS / Linux：

```bash
export STEP_API_KEY="YOUR_STEP_API_KEY"
```

Windows PowerShell：

```powershell
$env:STEP_API_KEY = "YOUR_STEP_API_KEY"
```

设置后，在同一终端运行后面的 Python 命令；使用 Notebook 时，请从该终端启动 Jupyter，让内核继承环境变量。也可以在 IDE 的运行配置或服务部署环境中设置 `STEP_API_KEY`。未设置时，代码会隐藏询问密钥，密钥无需写进源码。

中国站设置 `REGION = "cn"`，使用 `.com` 地址；国际站设置为 `"global"`，使用 `.ai` 地址。密钥应与对应站点一致。

在项目中新建 `tts_demo.py`，将本文的 **Python 代码块按顺序放进这个文件**；`bash` 和 `powershell` 代码块只在终端执行。完成定义与调用后运行：

```bash
python tts_demo.py
```

代码按“连接配置、能力参数、调用、结果处理”分组。接入已有项目时，按这些分组复用函数，并在业务入口调用。配套 `.ipynb` 是相同代码的可选交互形式；普通 Python 文件包含本篇完整运行路径。

### 2.5 初始化连接与凭证

`BASE_URLS` 保存站点地址，`REGION` 选择本次连接。`get_key()` 只在环境变量缺失时询问密钥，适用于终端运行；服务中可直接从部署环境读取。

```python
import getpass
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URLS = {"cn": "https://api.stepfun.com/v1", "global": "https://api.stepfun.ai/v1"}
REGION = "cn"

def get_key() -> str:
    key = os.environ.get("STEP_API_KEY", "").strip()
    if not key:
        key = getpass.getpass("输入 StepFun API 密钥（隐藏输入，不保存到文件）：").strip()
    if not key:
        raise ValueError("未提供密钥，已停止。")
    return key

import io
import wave
import hashlib
import uuid
```

### 2.6 设置 HTTP 超时与响应读取

下面的 `post()` 是本篇公共请求函数。`HTTP_TIMEOUT_SECONDS` 控制一次网络操作的等待上限，是客户端配置；它与模型的推理强度或输出长度分开设置。函数返回响应字节、完整读取耗时和内容类型。

```python
HTTP_TIMEOUT_SECONDS = 90

def post(payload: dict, key: str, region: str = "cn", path: str = "/chat/completions"):
    request = urllib.request.Request(
        BASE_URLS[region] + path,
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        # 不把请求头或服务端原始错误写进结果文件。
        raise RuntimeError(f"HTTP {exc.code}：核对区域、权限、额度及请求字段；本例不自动重试。") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError(f"网络连接失败或超过 {HTTP_TIMEOUT_SECONDS} 秒；本次停止。") from None
    elapsed = time.perf_counter() - start
    return body, elapsed, content_type

def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
```

`post()` 返回音频字节，`save_json()` 保存配置与结果记录。音频文件的解析和保存将在合成步骤中实现。

```python
api_key = get_key()
```

语音合成使用 `stepaudio-3-tts`，起始预置音色为 `zixinnansheng`。个性化复刻部分会上传随文参考录音、创建账户音色，再合成新文本；各阶段按平台规则使用额度。模型与计费说明见 [StepAudio 3 TTS](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-tts)。

## 3. 先生成一段语音

### 3.1 准备文本与请求

同一句文本包含“重庆”和“银行”，可以同时观察语速与多音字读法。先按默认速度合成，再分别改一个参数。

```python
MODEL = "stepaudio-3-tts"
VOICE = "zixinnansheng"
TEXT = "重庆的银行今天营业。请保持自然的语速。"
OUTPUT_DIR = Path("tts_results")
OUTPUT_DIR.mkdir(exist_ok=True)
```

**参数组：音色、语速与指定发音。** `voice` 使用当前账户可用的预置或个性化音色 ID；`speed` 范围为 0.5–2.0，起点为 1.0。本例固定 `language="zh"` 与 `response_format="wav"`，保证对照时语言和文件格式一致。

```python
VARIANTS = {"baseline": {}, "slow": {"speed": 0.8}, "fast": {"speed": 1.2},
            "pronunciation": {"pronunciation_map": {"tone": ["重/chong2", "行/hang2"]}}}

def request_for(text, voice, variant, model="stepaudio-3-tts"):
    if not 1 <= len(text) <= 1000:
        raise ValueError("本篇每次合成 1–1000 个字符。")
    if not voice.strip():
        raise ValueError("请指定当前账号可用的音色 ID。")
    return {"model": model, "input": text, "voice": voice, "language": "zh",
            "response_format": "wav", "speed": 1.0, **VARIANTS[variant]}
```

改变 `speed` 时保持文本和 `voice` 一致；改变 `voice` 时保持语速一致。`pronunciation_map.tone` 中的数字表示声调，目标读音会随请求一起发送。下面的函数读取 WAV 文件信息，用于确认得到的文件格式和时长。

```python
def inspect_wav(raw):
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("返回内容不是可识别的 WAV；未保存成音频。")
    with wave.open(io.BytesIO(raw), "rb") as wav:
        if wav.getnframes() <= 0:
            raise ValueError("返回音频没有采样帧。")
        return {"duration_seconds": wav.getnframes()/wav.getframerate(),
                "sample_rate": wav.getframerate(), "channels": wav.getnchannels(), "sample_width": wav.getsampwidth()}
```

`request_for()` 设置模型、文本、音色、语言和 WAV 输出。`inspect_wav()` 从返回文件头读取真实采样率、声道和时长。下面将合成、文件保存和记录组合为一个函数。

```python
def synthesize(text, voice, variant, label):
    payload = request_for(text, voice, variant, MODEL)
    raw, elapsed, content_type = post(payload, api_key, REGION, "/audio/speech")
    meta = inspect_wav(raw)
    target = OUTPUT_DIR / (label + ".wav")
    target.write_bytes(raw)
    return {"file": str(target), "request": payload, "elapsed_seconds": elapsed,
            "content_type": content_type, **meta,
            "generation_to_audio_duration": elapsed / meta["duration_seconds"]}
```

```python
baseline = synthesize(TEXT, VOICE, "baseline", "baseline")
print(json.dumps(baseline, ensure_ascii=False, indent=2))
```

用系统播放器打开 `tts_results/baseline.wav` 即可听到合成内容。代码返回的文件路径也可以交给项目现有的播放器。

## 4. 调整输出，并创建个性化音色

### 4.1 比较语速与发音控制

下面两段分别关注 `speed` 和 `pronunciation_map`，每次只改一项。`slow` 把速度改为 0.8；`fast` 改为 1.2；`pronunciation` 保持默认语速，用 `pronunciation_map` 指定“重”和“行”的读音。

**先比较 `speed`。** 本轮分别用 0.8 和 1.2 合成同一段话，观察时长和实际听到的节奏。

```python
variants = [synthesize(TEXT, VOICE, name, name) for name in ["slow", "fast"]]
for row in variants:
    print(row["file"], round(row["duration_seconds"], 2), "秒")
```

**再比较 `pronunciation_map`。** 使用默认语速，仅覆盖“重”和“行”的读音。将生成文件与 `baseline.wav` 对照，听目标词是否按指定读法生成。

```python
pronunciation = synthesize(TEXT, VOICE, "pronunciation", "pronunciation")
variants.append(pronunciation)
print(pronunciation["file"])
```

`speed` 调整生成语速；音频时长可辅助比较，最终仍需听清句子、停顿与读音。本篇每次合成限制为 1–1000 字符。字段用法见[语音合成接口](https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio)。

### 4.2 准备个性化复刻的原录音

个性化复刻使用参考录音中的声音特征，再合成不同文本。本例选择公开 LJ Speech 数据集的真人朗读：Linda Johnson 录音，Keith Ito 整理。发布者在[数据集说明](https://keithito.com/LJ-Speech-Dataset/)中将文本、录音与标注列为 public domain。换成自己的素材时，使用本人或已获授权的声音。

- [原始参考录音 LJ025-0076.wav](../assets/voice_reference/LJ025-0076.wav) · [发布者的原始下载地址](https://keithito.com/LJ-Speech-Dataset/LJ025-0076.wav)
- [同一参考音色合成的新文本示例（AI 生成）](../assets/voice_reference/personalized_example.wav)
- [来源与文件信息](../assets/voice_reference/SOURCE.md)

原录音约 8.397 秒，22050 Hz、单声道、16 位 PCM WAV，保留下载原文件，没有裁剪或重采样。随文提供的合成示例读的是新内容，不能当作原说话人的真实发言。

下载完整包后，从案例根目录运行代码，该目录中包含 `assets/voice_reference/`；单独使用本文时，将原 WAV 保存到下面声明的位置。代码不需要额外的 Python 文件。

```python
REFERENCE = Path("assets/voice_reference/LJ025-0076.wav")
REFERENCE_TEXT = "Many animals of even complex structure which live parasitically within others are wholly devoid of an alimentary cavity."
NEW_TEXT = "This is a synthetic voice demonstration. The reference recording defines the voice, while this sentence provides new content."
LANGUAGE = "en"
```

**参数组：参考录音与逐字稿。** `REFERENCE` 决定声音来源，`REFERENCE_TEXT` 应与原音逐字对应。这里先检查 WAV 格式和时长，再按文件上传接口组装请求体。

```python
def inspect_reference(path):
    with wave.open(str(path), "rb") as wav:
        meta = {"seconds": wav.getnframes()/wav.getframerate(), "sample_rate": wav.getframerate(),
                "channels": wav.getnchannels(), "sample_width": wav.getsampwidth()}
    if not 5 <= meta["seconds"] <= 10:
        raise ValueError("参考 WAV 需要 5–10 秒。")
    if meta["channels"] != 1 or meta["sample_width"] != 2:
        raise ValueError("本例采用单声道 16 位 PCM WAV。")
    return meta

def upload_body(audio):
    boundary = "cookbook_" + uuid.uuid4().hex
    data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nstorage\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"reference.wav\"\r\n"
            "Content-Type: audio/wav\r\n\r\n").encode() + audio
    data += f"\r\n--{boundary}--\r\n".encode()
    return data, "multipart/form-data; boundary=" + boundary
```

音色创建与合成共享下列发送函数。它使用前面配置的账户与区域；只更换路径和请求体。超时由客户端控制，录音内容不会写入普通 JSON 记录。

```python
def send(path, data, content_type):
    request = urllib.request.Request(
        BASE_URLS[REGION] + path, data=data,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": content_type},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}：请核对区域、权限和请求字段。") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("网络连接失败或超时，本次停止。") from None
    return raw, time.perf_counter() - start
```

```python
reference_meta = inspect_reference(REFERENCE)
reference_audio = REFERENCE.read_bytes()
print(json.dumps(reference_meta, ensure_ascii=False, indent=2))
```

本例要求参考 WAV 为 5–10 秒、单声道、16 位 PCM。上传使用 `purpose="storage"`；创建音色时的 `text` 是原录音逐字稿，合成时的 `input` 才是新文本。下面按这三个阶段执行。

### 4.3 保存本次参考输入，便于复用音色

文件 ID 与音色 ID 属于调用账户。状态文件用于同一账户、同一录音、同一模型的后续使用，避免反复上传和创建；它不保存 API Key。换账户时使用新的状态目录。

```python
STATE_DIR = OUTPUT_DIR / "personal_voice"
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / "state.json"
fingerprint = {"audio_sha256": hashlib.sha256(reference_audio).hexdigest(),
               "model": MODEL, "region": REGION, "reference_transcript": REFERENCE_TEXT}
state = (json.loads(STATE_FILE.read_text(encoding="utf-8"))
         if STATE_FILE.exists() else {"input": fingerprint})
if state.get("input") != fingerprint:
    raise ValueError("参考输入已改变，请为新录音设置另一个 STATE_DIR。")
```

### 4.4 上传原录音

multipart 请求包含 `purpose` 与音频文件两个部分。将接口返回的文件 ID 写入状态，下一次可以复用。

```python
if not state.get("file_id"):
    body, content_type = upload_body(reference_audio)
    raw, upload_seconds = send("/files", body, content_type)
    state["file_id"] = json.loads(raw)["id"]
    save_json(STATE_FILE, state)
print("参考文件已准备。")
```

### 4.5 用原录音和逐字稿创建音色

创建结果里的 `id` 就是后续合成使用的 `voice` 值。这里直接保存接口返回值，换到其他账户时需要在自己的账户下重新创建。

```python
if not state.get("voice_id"):
    payload = {"model": MODEL, "file_id": state["file_id"], "text": REFERENCE_TEXT}
    raw, clone_seconds = send("/audio/voices", json.dumps(payload).encode("utf-8"), "application/json")
    state["voice_id"] = json.loads(raw)["id"]
    save_json(STATE_FILE, state)
print("个性化音色已准备。")
```

### 4.6 用个性化音色合成新文本

复刻后仍使用语音合成接口，只需把 `voice` 改为刚创建的音色 ID。此处参考录音与新文本均为英文，因此 `language` 为 `en`。

```python
payload = {"model": MODEL, "voice": state["voice_id"], "input": NEW_TEXT,
           "language": LANGUAGE, "response_format": "wav", "speed": 1.0}
raw, elapsed = send("/audio/speech", json.dumps(payload).encode("utf-8"), "application/json")
personal_meta = inspect_wav(raw)
personal_file = STATE_DIR / ("personal_" + uuid.uuid4().hex[:8] + ".wav")
personal_file.write_bytes(raw)
personal_record = {"file": str(personal_file), "input": NEW_TEXT, "language": LANGUAGE,
                   "elapsed_seconds": elapsed, **personal_meta}
save_json(personal_file.with_suffix(".json"), personal_record)
print(json.dumps(personal_record, ensure_ascii=False, indent=2))
```

完整接口顺序为[上传文件](https://platform.stepfun.com/docs/zh/api-reference/files/create) → [创建音色](https://platform.stepfun.com/docs/zh/api-reference/audio/create-voice) → [语音合成](https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio)。后续更换新文本时，复用 `state["voice_id"]`，只需再执行合成阶段。

## 5. 对照原声，读懂音频与耗时

先播放参考录音，再播放新合成内容，分别观察音色、语气、清晰度和完整性。新文本与原文不同，可以观察声音特征是否延续。音色相似度需要实际听辨；文件格式正确只表示得到了可读取音频。

以下保存预置音色的对照记录。`generation_to_audio_duration` 是完整生成请求耗时除以生成音频时长，用于观察生成与内容长度的关系。本篇使用整段 WAV 返回，未测量流式首包延迟。

```python
all_records = [baseline, *variants]
save_json(OUTPUT_DIR / "records.json", all_records)
for row in all_records:
    print({"文件": row["file"], "完整请求耗时_秒": round(row["elapsed_seconds"], 2),
           "音频时长_秒": round(row["duration_seconds"], 2),
           "生成耗时与音频时长之比": round(row["generation_to_audio_duration"], 2),
           "采样率": row["sample_rate"]})
```

听每段时，核对有没有漏读、重复或截断，目标词读音是否符合预期。比较语速时保持文本与音色一致；比较音色时保持文本、语速和发音配置一致。每组记录保留请求参数，方便再次合成。

## 6. 换成自己的文本与声音

使用预置音色时，直接替换 `TEXT` 和 `VOICE`，沿用 `synthesize()`。使用个人录音时，替换 `REFERENCE` 与逐字稿 `REFERENCE_TEXT`，换一个 `STATE_DIR`，从参考文件检查开始顺序执行。修改 `NEW_TEXT` 后，只运行合成新文本阶段即可。

如果参考声音和目标文本为中文，将相应语言设置为 `zh`，使用与你的录音逐字对应的中文文本。把合成结果接到应用时，按 WAV 中的真实采样率播放；保留新音色 ID 和输入版本，就能在同一账户下重复生成。

## 7. 配套代码与运行脚手架

本案例提供 Notebook、可编辑 Python 脚本及运行脚手架，便于逐步学习、运行示例和接入自己的项目。完整文件见[案例目录](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts)，环境准备和启动步骤见[运行指南](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/README.md)。

| 配套资源 | 用途 |
| --- | --- |
| [Jupyter Notebook](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/05_StepAudio3_TTS.ipynb) | 按单元格阅读和执行案例，观察每一步的输入与结果。 |
| [Python 示例脚本](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/tts_demo.py) | 在终端运行最小示例或完整实验，也可修改后复用到自己的项目。 |
| [macOS 启动入口](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/%E5%90%AF%E5%8A%A8.command) · [Windows 启动入口](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/%E5%90%AF%E5%8A%A8.bat) · [启动菜单](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/launcher.py) | 准备案例运行环境，并选择最小示例、完整实验及 API 区域。 |
| [环境配置目录](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts/setup) · [锁定依赖](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/setup/requirements.lock) | 包含环境准备脚本、依赖版本和环境检查程序。 |
| [参考音频与文本](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts/assets/voice_reference) · [素材来源](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/assets/voice_reference/SOURCE.md) | 包含参考录音、逐字稿、新合成文本、合成示例及来源说明。 |

使用启动脚手架时，请从当前仓库获取完整案例目录，并保留启动文件、`setup/` 和素材之间的相对路径；首次准备环境需要联网。配套 Notebook、Python 脚本和启动菜单对应中文版，英文版的提示词、示例输入和部分结果字段可能不同。

更新日期：2026-09-29。正文代码面向普通 Python 项目；配套 Notebook 为同内容的可选形式。模型标识与接口字段保留英文。
