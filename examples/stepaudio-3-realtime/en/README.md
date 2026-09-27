# StepAudio 3 Realtime: Build a minimal voice conversation and tune VAD

[简体中文](../zh-CN/README.md) | **English**

> Both language versions use the same sample inputs, parameters, and checking rules. Chinese prompts, string literals, and output fields in the code are preserved so that runs remain comparable.

## 1. Understand realtime voice models and conversation turns

StepAudio 3 Realtime supports two-way realtime voice interaction. It receives audio over a persistent WebSocket connection and returns text and audio events. The service handles speech understanding, turn management, and responses within one session, and allows the user to start speaking again while the assistant is talking. [Model overview](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-realtime)

Two concepts are central to tuning. **Voice activity detection (VAD)** determines when speech starts and ends. A **turn** consists of a user input and its corresponding response. VAD affects how pauses divide speech, while turn handling requires the client to associate transcripts and audio with the correct response. Natural interruption also requires the local player to discard buffered audio from the previous response promptly.

This guide uses `stepaudio-3-realtime-preview` to implement a minimal voice conversation in a standard Python project. You will tune VAD parameters and assistant instructions, with recording, response handling, and connection lifecycle code separated by responsibility so you can integrate them into your own interface.

**Workflow:** Prepare devices → Configure audio and VAD → Exchange session events → Start a conversation → Compare parameters → Integrate a player.

## 2. Prerequisites and setup

### 2.1 Prerequisites

**Required knowledge:** Python functions, dictionaries, and JSON, plus a basic understanding of the request–response flow. The audio implementation also uses callbacks and queues; this guide explains their roles in recording and playback.

**You will need:**

- Python 3.10 or later, a terminal, and a code editor of your choice.
- A [StepFun Platform](https://platform.stepfun.com/) account with an API key and access to `stepaudio-3-realtime-preview`.
- Network access to the API for your selected region. Live requests consume your account quota.
- Audio devices: a microphone and headphones, with microphone access granted to your terminal or IDE.

### 2.2 Create a Python environment

For an existing project, you can use its current virtual environment. For a new project, create an environment in any working directory. Run the following in a macOS or Linux terminal:

```bash
mkdir stepfun-demo
cd stepfun-demo
python3 -m venv .venv
source .venv/bin/activate
```

In Windows PowerShell, run:

```powershell
mkdir stepfun-demo
cd stepfun-demo
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

After activation, confirm the Python version with the following command. All subsequent `python` commands refer to this environment’s interpreter.

```bash
python --version
```

### 2.3 Install dependencies

Use `websocket-client` for the realtime connection and `sounddevice` for audio devices. Install them in the activated environment:

```bash
python -m pip install websocket-client==1.8.0 sounddevice==0.5.2
```

If PortAudio is missing, install the required system component according to the [sounddevice installation guide](https://python-sounddevice.readthedocs.io/en/0.5.2/installation.html).

### 2.4 Configure credentials and run the example

The code reads the `STEPFUN_API_KEY` environment variable. Set it in your IDE's run configuration or your service's deployment environment. If it is not set locally, the code prompts for the key in the terminal with input hidden. You do not need to store the key in source code.

Set `REGION = "cn"` for the China region, which uses `.com` endpoints, or `"global"` for the international region, which uses `.ai` endpoints. Use a key issued for the selected region.

Create `realtime_demo.py` in your project and **copy this guide's Python code blocks into that file in order**. Run the `bash` and `powershell` blocks only in a terminal. After adding the definitions and calls, run:

```bash
python realtime_demo.py
```

The code is organized into connection configuration, capability parameters, calls, and result handling. To integrate it into an existing project, reuse the functions in these groups and call them from your application entry point. The companion `.ipynb` provides an optional interactive format for the same code; the Python file contains the complete execution path for this guide.

### 2.5 Configure the connection and audio devices

`MODEL` and `REGION` select the service. `input_device` and `output_device` select devices on the local machine; `None` uses the system default. You can select device IDs from the list shown later. `block_ms` sets the duration of each local audio callback block, starting at 20 milliseconds.

Both input and output use mono 16-bit PCM. PCM has no file header, so `input_rate` and `output_rate` must match the server requirements and device settings. Changing a local value does not make the server resample audio automatically. This example retains 24000 Hz as its starting point; verify it against the current session format before integration.

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

### 2.6 Identify devices and check the format

`sounddevice` accesses devices on the machine running the Python process. Run the following checks in a local terminal before connecting to the model. To change devices, update only the device IDs in `AUDIO_CONFIG`.

```python
import sounddevice as sd
print(sd.query_devices())
sd.check_input_settings(device=AUDIO_CONFIG["input_device"], channels=1,
                        dtype="int16", samplerate=AUDIO_CONFIG["input_rate"])
sd.check_output_settings(device=AUDIO_CONFIG["output_device"], channels=1,
                         dtype="int16", samplerate=AUDIO_CONFIG["output_rate"])
print("设备接受当前音频格式。")
```

## 3. Configure a session and complete a conversation

### 3.1 Parameter group: assistant instructions and VAD

`instructions` controls the response language and style, while `voice` selects the output voice. VAD settings are grouped in `VAD_CONFIG`:

| Parameter | Starting value | What to observe when changing it |
| --- | --- | --- |
| `prefix_padding_ms` | 500 ms | Audio retained before the detected speech start; check whether initial syllables are complete |
| `silence_duration_ms` | 100 ms | How long to wait in silence before ending a turn; check whether pauses within a sentence end the turn too early |
| `energy_awakeness_threshold` | 2500 | Energy threshold for speech activity; tune it alongside microphone gain and background sound |

Change one VAD parameter at a time while keeping the device and spoken input fixed. For field definitions, see the [session API](https://platform.stepfun.com/docs/zh/api-reference/realtime/chat).

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

### 3.2 Client configuration: audio buffers and chunks

The recording callback places PCM in a send queue, and the playback callback consumes PCM from a buffer. Queue capacity limits memory use; `block_ms` controls the chunk size passed to the device. These are client audio settings and should be tuned separately from the server VAD silence interval.

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
        size = frames * 2  # Mono PCM16: two bytes per frame.
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

Devices open only after the server confirms the session configuration. The following functions handle device formats and resource cleanup. To integrate another player, replace this layer while keeping the session parameters above.

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

### 3.3 Connect the recording queue to the WebSocket

The sending thread continuously reads PCM and wraps it in `input_audio_buffer.append` events. It does not decide when the user has finished speaking; the server VAD configured above makes that decision. A stop flag controls both the sending thread and the devices.

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

### 3.4 Turn events: VAD and local interruption handling

On `speech_started`, clear the previous playback buffer and mark any response still being generated for discard. This prevents late audio from the previous response from entering the new turn. On `speech_stopped`, record a timestamp to measure the interval until the first audio chunk arrives.

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

### 3.5 Response events: transcripts, audio, and response IDs

`response_id` associates each audio chunk with a specific response. The client plays only responses that remain valid. When a completion event arrives, release that response's state and save its completion status and chunk count. To integrate a transcript panel, replace the text output here with UI updates.

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

### 3.6 Initialize the session and dispatch events

The server first sends `session.created`, then the client sends its configuration. The microphone opens only after `session.updated` arrives. This sequence ensures that the voice and VAD settings are active. The following entry point dispatches session events to the corresponding handlers.

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

### 3.7 Combine the components in a connection object

`RealtimeSession` holds the state for one connection and exposes `start()`, `stop()`, and `summary()`. You can use it in a terminal program, web backend, or desktop application. The calling project determines when to start and stop the connection.

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

### 3.8 Start a conversation in the terminal

Finally, define the entry point for a standard Python script. It waits for configuration confirmation, then keeps the program running in the terminal. Say a few sentences and listen to the replies, then press Enter to stop. The `finally` block releases the connection and devices. You can use the same flow in an IDE terminal.

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
api_key = os.environ.get("STEPFUN_API_KEY", "").strip() or getpass.getpass("StepFun API Key（隐藏输入）：").strip()
if not api_key:
    raise ValueError("需要 API Key 才能启动会话")
```



```python
RUN_RESULTS.append(run_session(SETTINGS, "A-baseline", api_key))
print(json.dumps(RUN_RESULTS[-1], ensure_ascii=False, indent=2))
```

## 4. Tune VAD parameters individually

### 4.1 `silence_duration_ms`: wait for the user to finish

After the first session ends, change `silence_duration_ms` to 300 and hold all other conditions constant. Start the second session through the same entry point, say the same phrases as in session A, and press Enter to stop. A longer silence interval allows more time for pauses within a sentence and also affects when the assistant starts replying.

```python
B_SETTINGS = {**SETTINGS, "silence_duration_ms": 300}
RUN_RESULTS.append(run_session(B_SETTINGS, "B-silence-300", api_key))
print(json.dumps(RUN_RESULTS[-1], ensure_ascii=False, indent=2))
```

In both sessions, try a complete short sentence, a sentence with a pause, and speaking again while the assistant is replying. Check whether the beginning is captured fully, whether sentences end prematurely, and whether the previous response stops promptly when you resume speaking.

### 4.2 `prefix_padding_ms`: preserve the start of speech

This parameter determines how much preceding audio to retain after speech onset is detected. Focus on initial syllables and the first transcribed word. It does not set the wait at the end of a sentence. Keep the chosen silence interval fixed, change only this value in `VAD_CONFIG`, and run another session using the same short opening phrase.

### 4.3 `energy_awakeness_threshold`: match the recording environment

The energy threshold affects which sounds are more likely to count as speech activity. Keep microphone distance, gain, and background sound fixed while tuning it. Observe whether quiet periods trigger turns and whether normal speech is transcribed completely. Changing the audio device and threshold together makes it difficult to attribute the effect.

### 4.4 `instructions`: change the response style

VAD controls input turns, while `instructions` controls how the assistant responds. To compare response lengths, change only the requirements in `ASSISTANT_CONFIG` and use the same question and VAD settings. After changing a configuration dictionary, rebuild `SETTINGS` and create a new session. Existing connections do not automatically adopt changes to local values.

## 5. Interpret event records and listening results

`first_audio_after_speech_stopped_ms` measures the interval from the client's receipt of the turn-end event to the arrival of the first valid audio chunk, including network effects. It differs from the end-to-end time between the user stopping speech and sound actually coming from the device. Device buffering and VAD waiting time require separate measurements.

The following code saves both sessions' configurations, transcripts, response statuses, and event intervals. It does not save the API key or raw microphone audio.

```python
if RUN_RESULTS:
    result_dir = Path("realtime_results")
    result_dir.mkdir(exist_ok=True)
    result_file = result_dir / ("sessions_" + uuid.uuid4().hex[:8] + ".json")
    result_file.write_text(json.dumps(RUN_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    print("结果文件：", result_file)
```

Compare transcript completeness, turn events, response statuses, and what you hear. Event counts help explain what happened; playback and natural interruption behavior require an actual conversation on the target device.

## 6. Integrate the example into your project

Reuse the code along these boundaries:

- **Configuration:** Map `ASSISTANT_CONFIG` and `VAD_CONFIG` to your application's settings. Keep audio format and device settings in `AUDIO_CONFIG`.
- **Session lifecycle:** Call `RealtimeSession.start()` to connect and `stop()` from your application's exit or disconnect logic. The terminal example uses `input()` only to wait for the user to finish. A service can replace it with a button action or connection lifecycle event.
- **Output:** Route text from `handle_response()` to a transcript panel and pass valid PCM to your existing player. Retain response association and cleanup of old playback buffers.

First complete a short session with this guide's settings, then change one variable at a time for your pause patterns and devices. Available model names and session formats are governed by the [official model documentation](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-realtime) and your account configuration.

Last updated: 2026-09-27. The code runs in a standard Python project; the companion Notebook is an optional format with the same content. Model identifiers and API field names remain in English.
