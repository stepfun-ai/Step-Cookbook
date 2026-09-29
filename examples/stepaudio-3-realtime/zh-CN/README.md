# StepAudio 3 Realtime 实时语音：最小对话与 VAD 调参

**简体中文** | [English](../en/README.md)

> 中英文版本介绍相同的模型能力和主要流程；示例输入、提示词、输出字段和校验细节可能不同，请以所读版本的代码为准。配套 Python 脚本与 Notebook 对应中文版。

## 1. 认识实时语音模型与话轮

StepAudio 3 Realtime 面向双向实时语音交互，通过持续的 WebSocket 连接接收音频，并返回文字与语音事件。模型服务在同一会话中处理语音理解、话轮管理和回复，支持用户在助手说话时重新开口。[模型概览](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-realtime)

理解两个概念就能开始调参：**VAD（语音活动检测）**判断何时开始说话、何时结束；**话轮**表示一段用户输入及其对应回复。前者影响停顿如何被切分，后者要求客户端正确归属字幕和音频。自然打断还需要本地播放器及时丢弃旧回复的缓冲。

本篇使用 `stepaudio-3-realtime-preview`，在普通 Python 项目中做一个最小语音对话。主要调整 VAD 参数与助手要求，并把收音、响应处理和连接生命周期按职责拆开，便于接入自己的界面。

**本文路线：** 准备设备 → 配置音频与 VAD → 收发会话事件 → 启动一次对话 → 比较参数 → 集成播放器。

## 2. 前置条件与环境准备

### 2.1 前置条件

**需要掌握：** Python 函数、字典与 JSON；了解一次请求如何返回结果。语音部分会用到回调和队列，正文会解释它们在收音与播放中的作用。

**需要准备：**

- Python 3.10 或以上版本、一个终端和任意代码编辑器。
- [StepFun 开放平台](https://platform.stepfun.com/)账号，已创建 API Key，并确认可以调用 `stepaudio-3-realtime-preview`。
- 可以访问所用区域 API 的网络环境。真实调用会使用账户额度。
- 音频设备：麦克风与耳机；系统已允许终端或 IDE 使用麦克风。

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

实时连接使用 `websocket-client`，音频设备使用 `sounddevice`。在已激活的终端安装：

```bash
python -m pip install websocket-client==1.8.0 sounddevice==0.5.2
```

若系统缺少 PortAudio，按 [sounddevice 安装说明](https://python-sounddevice.readthedocs.io/en/0.5.2/installation.html)安装对应组件。

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

在项目中新建 `realtime_demo.py`，将本文的 **Python 代码块按顺序放进这个文件**；`bash` 和 `powershell` 代码块只在终端执行。完成定义与调用后运行：

```bash
python realtime_demo.py
```

代码按“连接配置、能力参数、调用、结果处理”分组。接入已有项目时，按这些分组复用函数，并在业务入口调用。配套 `.ipynb` 是相同代码的可选交互形式；普通 Python 文件包含本篇完整运行路径。

### 2.5 配置连接和音频设备

`MODEL` 与 `REGION` 选择服务；`input_device`、`output_device` 选择本机设备。`None` 表示系统默认设备，稍后可以从设备列表选择编号。`block_ms` 是本地音频回调的分块时长，起点为 20 毫秒。

输入与输出均使用单声道 16 位 PCM。PCM 无文件头，`input_rate` 和 `output_rate` 必须与服务端要求、设备设置一致；改变本地值不会让服务端自动重采样。本例保留 24000 Hz 起点，接入前按当前会话格式核对。

```python
import base64
import getpass
import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path

MODEL = "stepaudio-3-realtime-preview"
REGION = "cn"
ENDPOINTS = {"cn": "wss://api.stepfun.com/v1/realtime",
             "global": "wss://api.stepfun.ai/v1/realtime"}
AUDIO_CONFIG = {"input_rate": 24000, "output_rate": 24000,
                "input_device": None, "output_device": None, "block_ms": 20}
```

### 2.6 识别设备并检查格式

`sounddevice` 访问的是 Python 进程所在机器的设备。以下检查在本机终端执行，成功后再建立模型连接。需要改设备时，只调整 `AUDIO_CONFIG` 的设备编号。

```python
import sounddevice as sd
print(sd.query_devices())
sd.check_input_settings(device=AUDIO_CONFIG["input_device"], channels=1,
                        dtype="int16", samplerate=AUDIO_CONFIG["input_rate"])
sd.check_output_settings(device=AUDIO_CONFIG["output_device"], channels=1,
                         dtype="int16", samplerate=AUDIO_CONFIG["output_rate"])
print("设备接受当前音频格式。")
```

## 3. 配置会话并完成一次对话

### 3.1 参数组：助手要求与 VAD

`instructions` 控制回复语言与表达方式，`voice` 控制返回音色。VAD 单独放在 `VAD_CONFIG`：

| 参数 | 本例起点 | 改动时关注什么 |
| --- | --- | --- |
| `prefix_padding_ms` | 500 毫秒 | 语音起点之前保留的音频；观察开头音节是否完整 |
| `silence_duration_ms` | 100 毫秒 | 等待静音多久再结束话轮；观察句中停顿是否被提前截断 |
| `energy_awakeness_threshold` | 2500 | 语音活动的能量门槛；结合麦克风增益和背景声音调整 |

先只改变一个 VAD 参数，同时固定设备和说法。字段依据见[会话接口](https://platform.stepfun.com/docs/zh/api-reference/realtime/chat)。

```python
ASSISTANT_CONFIG = {
    "instructions": "你是实时语音助手。请用用户的语言简短回答；不确定时明确说明。",
    "voice": "jingdiannvsheng",
}
VAD_CONFIG = {"prefix_padding_ms": 500, "silence_duration_ms": 100,
              "energy_awakeness_threshold": 2500}
SETTINGS = {**AUDIO_CONFIG, **ASSISTANT_CONFIG, **VAD_CONFIG}
RUN_RESULTS = []


def make_event(kind, **fields):
    return {"event_id": "client_" + uuid.uuid4().hex, "type": kind, **fields}


def session_update(settings):
    return make_event("session.update", session={
        "modalities": ["text", "audio"],
        "instructions": settings["instructions"], "voice": settings["voice"],
        "input_audio_format": "pcm16", "output_audio_format": "pcm16",
        "turn_detection": {"type": "server_vad",
            **{key: settings[key] for key in VAD_CONFIG}},
    })
```

### 3.2 客户端配置：音频缓冲与分块

收音回调把 PCM 放入发送队列，播放回调从缓冲取出 PCM。队列容量限制内存占用；`block_ms` 决定每次交给设备的分块大小。这些是客户端音频配置，与服务端 VAD 的停顿时长分开调整。

```python
class AudioBuffers:
    def __init__(self, ready, stopping):
        self.ready, self.stopping = ready, stopping
        self.queue = queue.Queue(maxsize=100)
        self.playback = bytearray()
        self.lock = threading.Lock()
        self.device_lock = threading.RLock()
        self.input_stream = self.output_stream = None

    def capture(self, indata, frames, time_info, status):
        if not self.ready.is_set() or self.stopping.is_set():
            return
        try:
            self.queue.put_nowait(bytes(indata))
        except queue.Full:
            self.stopping.set()
            print("发送队列已满，本次会话停止。")

    def render(self, outdata, frames, time_info, status):
        size = frames * 2  # 单声道 PCM16，每帧两个字节。
        with self.lock:
            available = min(size, len(self.playback))
            chunk = bytes(self.playback[:available])
            del self.playback[:available]
        outdata[:available] = chunk
        outdata[available:size] = b"\x00" * (size - available)

    def clear(self):
        with self.lock:
            self.playback.clear()
```

设备只在服务端确认会话配置后打开。下面两个函数集中处理设备格式与释放；接入其他播放器时，可以替换这一层，保留上面的会话参数。

```python
def open_audio(session):
    import sounddevice as sd
    audio, settings = session.audio, session.settings
    with audio.device_lock:
        if session.stopping.is_set():
            return
        common = {"channels": 1, "dtype": "int16"}
        for direction, callback in [("output", audio.render), ("input", audio.capture)]:
            rate = settings[direction + "_rate"]
            stream_type = sd.RawOutputStream if direction == "output" else sd.RawInputStream
            stream = stream_type(samplerate=rate,
                blocksize=max(1, rate * settings["block_ms"] // 1000),
                device=settings[direction + "_device"], callback=callback, **common)
            setattr(audio, direction + "_stream", stream)
            stream.start()
        session.ready.set()


def close_audio(session):
    with session.audio.device_lock:
        session.ready.clear()
        for name in ["input_stream", "output_stream"]:
            stream = getattr(session.audio, name)
            if stream is not None:
                for operation in [stream.stop, stream.close]:
                    try:
                        operation()
                    except Exception:
                        pass
                setattr(session.audio, name, None)
```

### 3.3 将收音队列连接到 WebSocket

发送线程持续读取 PCM 并封装为 `input_audio_buffer.append`。它不决定用户是否说完；话轮判断交给前面配置的服务端 VAD。停止标记同时控制发送线程与设备。

```python
def send_microphone(session):
    try:
        while not session.stopping.is_set():
            try:
                chunk = session.audio.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            session.ws.send(json.dumps(make_event("input_audio_buffer.append",
                audio=base64.b64encode(chunk).decode("ascii"))))
    except Exception as exc:
        session.errors.append(str(exc).replace(session.key, "[已隐藏]"))
        session.stopping.set()
    finally:
        if session.stopping.is_set():
            session.ws.close()
```

### 3.4 话轮事件：VAD 与本地打断

收到 `speech_started` 时清空旧播放缓冲，并将仍在生成的响应标为丢弃；这样上一轮迟到的音频不会混入新话轮。收到 `speech_stopped` 时记录时间，供后面观察首个音频分块的到达间隔。

```python
def handle_turn(session, event):
    kind = event["type"]
    if kind == "input_audio_buffer.speech_started":
        session.speech_starts += 1
        session.stopped_at = None
        session.audio.clear()
        session.discarded.update(session.active)
        print("用户开始说话")
    elif kind == "input_audio_buffer.speech_stopped":
        session.speech_stops += 1
        session.stopped_at = time.monotonic()
        print("用户说话结束，等待回复")
    elif kind == "conversation.item.input_audio_transcription.completed":
        transcript = event.get("transcript", "")
        session.transcripts.append(transcript)
        print("用户：", transcript)
    else:
        return False
    return True
```

### 3.5 响应事件：字幕、音频与响应标识

`response_id` 把每个音频分块归到具体回复。客户端只播放仍有效的响应。完成事件到来后释放这轮状态，同时保存结束状态与分块数。集成字幕区时，可以将这里的文字输出替换为界面更新。

```python
def handle_response(session, event):
    kind = event["type"]
    if kind == "response.created":
        rid = event["response"]["id"]
        session.active.add(rid)
        session.chunks[rid] = 0
        return
    if kind == "response.done":
        response = event["response"]
        rid = response["id"]
        session.responses.append({"status": response.get("status"),
                                  "audio_chunks": session.chunks.pop(rid, 0)})
        session.active.discard(rid)
        session.discarded.discard(rid)
        session.caption_started.discard(rid)
        print("本轮结束：", response.get("status"))
        return
    if kind not in {"response.audio.delta", "response.audio_transcript.delta",
                    "response.audio_transcript.done"}:
        return
    rid = event.get("response_id")
    if not rid:
        raise ValueError("响应缺少 response_id")
    if rid not in session.active or rid in session.discarded:
        return
    if kind == "response.audio_transcript.delta":
        session.caption_started.add(rid)
        print(event.get("delta", ""), end="", flush=True)
    elif kind == "response.audio_transcript.done":
        print("" if rid in session.caption_started else event.get("transcript", ""))
    else:
        raw = base64.b64decode(event["delta"], validate=True)
        if not raw:
            return
        if len(raw) % 2:
            raise ValueError("PCM16 分块必须包含完整采样帧")
        with session.audio.lock:
            session.audio.playback.extend(raw)
        session.chunks[rid] += 1
        if session.chunks[rid] == 1 and session.stopped_at is not None:
            session.first_audio_ms.append(round((time.monotonic() - session.stopped_at) * 1000))
            session.stopped_at = None
```

### 3.6 会话初始化与事件分发

服务端先发送 `session.created`，客户端再发送配置；只有 `session.updated` 到达后才打开麦克风。这个顺序保证音色与 VAD 参数已经生效。以下入口将会话事件交给对应处理函数。

```python
def on_event(session, ws, message):
    if session.stopping.is_set():
        return
    try:
        event = json.loads(message)
        kind = event["type"]
        if kind == "session.created":
            ws.send(json.dumps(session_update(session.settings), ensure_ascii=False))
        elif kind == "session.updated" and not session.ready.is_set():
            open_audio(session)
            session.sender = threading.Thread(target=send_microphone, args=(session,), daemon=True)
            session.sender.start()
        elif kind == "error":
            detail = event.get("error", {})
            raise RuntimeError(str(detail.get("message", "会话接口返回错误")))
        elif not handle_turn(session, event):
            handle_response(session, event)
    except Exception as exc:
        session.errors.append(str(exc).replace(session.key, "[已隐藏]"))
        session.stopping.set()
        ws.close()


def run_socket(session):
    try:
        session.ws.run_forever(ping_interval=20, ping_timeout=10)
    except Exception as exc:
        session.errors.append(str(exc).replace(session.key, "[已隐藏]"))
    finally:
        session.stopping.set()
        close_audio(session)
        session.ws.close()
```

### 3.7 用连接对象组合这些组件

`RealtimeSession` 保存一轮连接的状态，提供 `start()`、`stop()` 和 `summary()`。它可以用于终端程序、Web 后端或桌面应用；启动和停止方式由调用它的项目决定。

```python
class RealtimeSession:
    def __init__(self, settings, key):
        self.settings, self.key = settings.copy(), key
        self.ready, self.stopping = threading.Event(), threading.Event()
        self.audio = AudioBuffers(self.ready, self.stopping)
        self.active, self.discarded, self.caption_started = set(), set(), set()
        self.chunks, self.responses, self.transcripts = {}, [], []
        self.first_audio_ms, self.errors = [], []
        self.speech_starts = self.speech_stops = 0
        self.stopped_at = self.ws = self.thread = self.sender = None

    def start(self):
        import websocket
        if self.thread is not None:
            raise RuntimeError("每轮对话请新建连接对象")
        self.ws = websocket.WebSocketApp(
            f"{ENDPOINTS[REGION]}?model={MODEL}",
            header=["Authorization: Bearer " + self.key],
            on_message=lambda ws, msg: on_event(self, ws, msg),
            on_error=lambda ws, exc: self.errors.append(str(exc).replace(self.key, "[已隐藏]")),
        )
        self.thread = threading.Thread(target=run_socket, args=(self,), daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.ws is not None:
            self.ws.close()
        for worker in [self.thread, self.sender]:
            if worker is not None and worker is not threading.current_thread():
                worker.join(timeout=5)
        close_audio(self)

    def summary(self):
        return {"speech_starts": self.speech_starts, "speech_stops": self.speech_stops,
                "user_transcripts": self.transcripts, "responses": self.responses,
                "first_audio_after_speech_stopped_ms": self.first_audio_ms,
                "errors": self.errors}
```

### 3.8 在终端启动一轮对话

最后定义普通 Python 调用入口。启动后等待配置确认，然后在终端保持程序运行；说几句话并听回复，按 Enter 停止。`finally` 会释放连接和设备，同一个过程也可以在 IDE 终端执行。

```python
def run_session(settings, label, key):
    session = RealtimeSession(settings, key)
    try:
        session.start()
        deadline = time.monotonic() + 15
        while not session.ready.is_set() and not session.stopping.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("等待会话配置确认超时")
            time.sleep(0.05)
        if not session.ready.is_set():
            raise RuntimeError("会话未就绪：" + "; ".join(session.errors))
        input("已就绪。请戴耳机对话；结束本组时按 Enter：")
    finally:
        session.stop()
    return {"label": label, "settings": {"model": MODEL, **settings}, **session.summary()}
```

```python
api_key = os.environ.get("STEP_API_KEY", "").strip() or getpass.getpass("StepFun API Key（隐藏输入）：").strip()
if not api_key:
    raise ValueError("需要 API Key 才能启动会话")
```

```python
RUN_RESULTS.append(run_session(SETTINGS, "A-baseline", api_key))
print(json.dumps(RUN_RESULTS[-1], ensure_ascii=False, indent=2))
```

## 4. 按 VAD 参数分别调整

### 4.1 `silence_duration_ms`：等待用户说完

第一组结束后，把 `silence_duration_ms` 改成 300，其他条件保持不变。接下来仍通过同一个入口启动第二组，说与 A 组相同的话，按 Enter 结束。较长的静音等待会给句中停顿留出更多时间，也会影响开始回复的时机。

```python
B_SETTINGS = {**SETTINGS, "silence_duration_ms": 300}
RUN_RESULTS.append(run_session(B_SETTINGS, "B-silence-300", api_key))
print(json.dumps(RUN_RESULTS[-1], ensure_ascii=False, indent=2))
```

两组都可以依次使用完整短句、句中停顿、助手回复时重新开口这三种说法。关注开头是否完整、句子是否提前结束、重新开口后旧回复是否及时停止。

### 4.2 `prefix_padding_ms`：保留说话起点

这个参数决定在检测到语音起点后，向前保留多少音频。开头音节与转写首词是主要观察对象；它不会设置句尾要等多久。保持已经选定的静音时长，单独修改 `VAD_CONFIG` 中这一项，再用同样的开头短句运行一组。

### 4.3 `energy_awakeness_threshold`：匹配收音环境

能量门槛影响哪些声音更容易被识别为语音活动。调节时固定设备距离、麦克风增益和背景声音，观察安静时是否仍触发话轮，以及正常说话是否有完整转写。不要同时改变音频设备和门槛，否则难以判断变化来自哪里。

### 4.4 `instructions`：调整回复方式

VAD 负责输入话轮，`instructions` 负责助手如何表达。需要比较回复长短时，单独修改 `ASSISTANT_CONFIG` 的要求，使用相同问题和 VAD 设置对照。每次修改配置字典后，重新构造 `SETTINGS` 并新建会话，已有连接不会自动采用本地新值。

## 5. 读取事件记录与实际听感

`first_audio_after_speech_stopped_ms` 从客户端收到话轮结束事件计时，到首个有效音频分块到达结束，包含网络影响。它与用户停止发声到设备实际出声的端到端时间不同；设备缓冲和 VAD 等待需要另行测量。

下面保存两组配置、转写、响应状态和事件间隔。记录不包含 API Key 或原始麦克风音频。

```python
if RUN_RESULTS:
    result_dir = Path("realtime_results")
    result_dir.mkdir(exist_ok=True)
    result_file = result_dir / ("sessions_" + uuid.uuid4().hex[:8] + ".json")
    result_file.write_text(json.dumps(RUN_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    print("结果文件：", result_file)
```

比较时结合转写完整性、话轮事件、响应状态和实际听感。事件计数帮助解释发生了什么，播放与自然打断体验需要在目标设备上实际对话。

## 6. 接到自己的项目

可按以下边界复用代码：

- **设置层：** 将 `ASSISTANT_CONFIG` 与 `VAD_CONFIG` 接到项目配置项；音频格式与设备放在 `AUDIO_CONFIG`。
- **会话层：** 使用 `RealtimeSession.start()` 建立连接，项目的退出或断开逻辑调用 `stop()`。终端演示的 `input()` 只负责等待用户结束，服务中可替换为按钮或连接生命周期。
- **输出层：** 将 `handle_response()` 中的文字输出接到字幕区，把有效 PCM 交给现有播放器，保留响应归属与旧缓冲清理。

先沿用本文参数完成一个短会话，再针对自己的停顿习惯和设备做单变量调整。模型可用名称与会话格式以[官方模型文档](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-realtime)和账户配置为准。

更新日期：2026-09-29。正文代码面向普通 Python 项目；配套 Notebook 为同内容的可选形式。模型标识与接口字段保留英文。
