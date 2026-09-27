# StepAudio 3 TTS: Control speaking rate, pronunciation, and personalized voices

[简体中文](../zh-CN/README.md) | **English**

> Both language versions use the same sample inputs, parameters, and checking rules. Chinese prompts, string literals, and output fields in the code are preserved so that runs remain comparable.

## 1. Understand text-to-speech and personalized voices

StepAudio 3 TTS converts text into speech: your application supplies the text and voice configuration, and the API returns synthesized audio. It supports both standard and streaming synthesis. This guide uses standard HTTP synthesis to save complete WAV files that are easy to integrate, play, and compare. [Model overview](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-tts)

The parameters have distinct roles: `voice` selects the voice identity, `speed` controls speaking rate, and `pronunciation_map` specifies how target words are pronounced. To use a personalized voice, first create it from a reference recording and its transcript, then pass it as `voice` in a synthesis request. [Speech synthesis API](https://platform.stepfun.ai/docs/en/api-reference/audio/create-audio)

This guide is for Python developers who need to generate speech in an application. You will synthesize one sentence, adjust rate and pronunciation separately, and then complete the full workflow: upload a reference recording → create a voice → synthesize new text.

**Workflow:** Configure the client → Synthesize and save a WAV file → Compare parameters → Create a personalized voice → Integrate it into your project.

## 2. Prerequisites and setup

### 2.1 Prerequisites

**Required knowledge:** Python functions, dictionaries, and JSON, plus a basic understanding of the request–response flow. No specific application framework is required.

**You will need:**

- Python 3.10 or later, a terminal, and a code editor of your choice.
- A [StepFun Platform](https://platform.stepfun.com/) account with an API key and access to `stepaudio-3-tts`.
- Network access to the API for your selected region. Live requests consume your account quota.
- Reference audio: save the supplied WAV and transcript under `assets/voice_reference/` in your project for the personalized voice section.

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

The request and file-handling code uses the Python standard library, so no third-party SDK is required. If your project already uses another HTTP client, you can keep it and use the request bodies shown here.

### 2.4 Configure credentials and run the example

The code reads the `STEPFUN_API_KEY` environment variable. Set it in your IDE's run configuration or your service's deployment environment. If it is not set locally, the code prompts for the key in the terminal with input hidden. You do not need to store the key in source code.

Set `REGION = "cn"` for the China region, which uses `.com` endpoints, or `"global"` for the international region, which uses `.ai` endpoints. Use a key issued for the selected region.

Create `tts_demo.py` in your project and **copy this guide's Python code blocks into that file in order**. Run the `bash` and `powershell` blocks only in a terminal. After adding the definitions and calls, run:

```bash
python tts_demo.py
```

The code is organized into connection configuration, capability parameters, calls, and result handling. To integrate it into an existing project, reuse the functions in these groups and call them from your application entry point. The companion `.ipynb` provides an optional interactive format for the same code; the Python file contains the complete execution path for this guide.

### 2.5 Initialize the connection and credentials

`BASE_URLS` stores the regional endpoints, and `REGION` selects the endpoint for this run. `get_key()` prompts only when the environment variable is missing, which suits terminal use. A service can read the key directly from its deployment environment.

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
    key = os.environ.get("STEPFUN_API_KEY", "").strip()
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

### 2.6 Set the HTTP timeout and read responses

The following `post()` function is the shared request helper for this guide. `HTTP_TIMEOUT_SECONDS` is a client setting that limits the wait for a network operation; configure it separately from reasoning effort or output length. The function returns the response bytes, the elapsed time through the end of the response read, and the content type.

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
        # Do not write request headers or raw server errors to result files.
        raise RuntimeError(f"HTTP {exc.code}：核对区域、权限、额度及请求字段；本例不自动重试。") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError(f"网络连接失败或超过 {HTTP_TIMEOUT_SECONDS} 秒；本次停止。") from None
    elapsed = time.perf_counter() - start
    return body, elapsed, content_type

def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
```

`post()` returns audio bytes, and `save_json()` saves configuration and result records. Audio parsing and file saving are implemented in the synthesis step.

```python
api_key = get_key()
```

The synthesis model is `stepaudio-3-tts`, and the initial preset voice is `zixinnansheng`. The personalized voice section uploads the supplied recording, creates a voice in your account, and synthesizes new text. Each stage uses quota according to the platform's rules. For model and billing details, see [StepAudio 3 TTS](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-tts).

## 3. Generate an audio clip

### 3.1 Prepare the text and request

The sample sentence contains “重庆” (Chongqing) and “银行” (bank), allowing you to observe both speaking rate and context-dependent character pronunciation. Start at the default rate, then change one parameter at a time.

```python
MODEL = "stepaudio-3-tts"
VOICE = "zixinnansheng"
TEXT = "重庆的银行今天营业。请保持自然的语速。"
OUTPUT_DIR = Path("tts_results")
OUTPUT_DIR.mkdir(exist_ok=True)
```

**Parameter group: voice, speaking rate, and pronunciation overrides.** Set `voice` to a preset or personalized voice ID available to your account. `speed` ranges from 0.5 to 2.0, with a starting value of 1.0. This example fixes `language="zh"` and `response_format="wav"` so language and file format remain consistent across comparisons.

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

When changing `speed`, keep the text and `voice` fixed. When changing `voice`, keep the rate fixed. Numbers in `pronunciation_map.tone` indicate tones; the target pronunciations are sent with the request. The following function reads WAV metadata to confirm the returned format and duration.

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

`request_for()` sets the model, text, voice, language, and WAV output. `inspect_wav()` reads the actual sample rate, channel count, and duration from the returned file header. The next function combines synthesis, file saving, and result recording.

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

Open `tts_results/baseline.wav` in your system's audio player to hear the synthesized speech. You can also pass the returned file path to your application's existing player.

## 4. Adjust the output and create a personalized voice

### 4.1 Compare speaking rate and pronunciation controls

The following two blocks focus on `speed` and `pronunciation_map`, changing one setting at a time. `slow` sets the rate to 0.8, and `fast` sets it to 1.2. `pronunciation` keeps the default rate and uses `pronunciation_map` to specify the readings of “重” and “行”.

**First compare `speed`.** Synthesize the same sentence at 0.8 and 1.2, then compare file duration and the rhythm you hear.

```python
variants = [synthesize(TEXT, VOICE, name, name) for name in ["slow", "fast"]]
for row in variants:
    print(row["file"], round(row["duration_seconds"], 2), "秒")
```

**Then compare `pronunciation_map`.** Use the default rate and override only the pronunciations of “重” and “行”. Compare the generated file with `baseline.wav` to hear whether the target words use the specified readings.

```python
pronunciation = synthesize(TEXT, VOICE, "pronunciation", "pronunciation")
variants.append(pronunciation)
print(pronunciation["file"])
```

`speed` controls the generated speaking rate. Audio duration helps with the comparison, but listen to the sentences, pauses, and pronunciation as well. This guide limits each synthesis request to 1–1000 characters. For field usage, see the [speech synthesis API](https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio).

### 4.2 Prepare a reference recording for voice cloning

Personalized voice cloning uses characteristics from a reference recording to synthesize different text. This example uses a human narration from the public LJ Speech dataset, recorded by Linda Johnson and curated by Keith Ito. The publisher identifies the text, recordings, and annotations as public domain in the [dataset description](https://keithito.com/LJ-Speech-Dataset/). When using your own material, use your own voice or a voice you have permission to use.

- [Original reference recording: LJ025-0076.wav](../assets/voice_reference/LJ025-0076.wav) · [Publisher's original WAV download](https://keithito.com/LJ-Speech-Dataset/LJ025-0076.wav)
- [New-text synthesis sample using the reference voice (AI-generated)](../assets/voice_reference/personalized_example.wav)
- [Source and file information](../assets/voice_reference/SOURCE.md)

The original recording is approximately 8.397 seconds long, at 22050 Hz, mono, 16-bit PCM WAV. The downloaded file is preserved without cropping or resampling. The supplied synthesis sample contains new text and must not be presented as an actual statement by the original speaker.

After downloading the complete package, run the code from the example's root directory, which contains `assets/voice_reference/`. If you use this article on its own, save the original WAV at the location declared below. No additional Python files are required.

```python
REFERENCE = Path("assets/voice_reference/LJ025-0076.wav")
REFERENCE_TEXT = "Many animals of even complex structure which live parasitically within others are wholly devoid of an alimentary cavity."
NEW_TEXT = "This is a synthetic voice demonstration. The reference recording defines the voice, while this sentence provides new content."
LANGUAGE = "en"
```

**Parameter group: reference recording and transcript.** `REFERENCE` selects the voice source, and `REFERENCE_TEXT` must match the recording word for word. First check the WAV format and duration, then construct the upload request body.

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

Voice creation and synthesis share the following sending function. It uses the account and region configured earlier; only the path and request body change. The client controls the timeout, and the recording's audio is not written to ordinary JSON records.

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

This example requires a 5–10-second, mono, 16-bit PCM reference WAV. Upload it with `purpose="storage"`. The `text` field used for voice creation is the original recording's transcript; the synthesis `input` field is the new text. The next sections implement those three stages.

### 4.3 Save the reference input to reuse the voice

File IDs and voice IDs belong to the calling account. A state file allows subsequent use with the same account, recording, and model without repeated uploads or voice creation. It does not store the API key. Use a new state directory when switching accounts.

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

### 4.4 Upload the original recording

The multipart request contains two parts: `purpose` and the audio file. Save the returned file ID in the state so it can be reused next time.

```python
if not state.get("file_id"):
    body, content_type = upload_body(reference_audio)
    raw, upload_seconds = send("/files", body, content_type)
    state["file_id"] = json.loads(raw)["id"]
    save_json(STATE_FILE, state)
print("参考文件已准备。")
```

### 4.5 Create a voice from the recording and transcript

The `id` in the creation response becomes the `voice` value for subsequent synthesis. Save the API's returned value directly. When switching accounts, create the voice again under that account.

```python
if not state.get("voice_id"):
    payload = {"model": MODEL, "file_id": state["file_id"], "text": REFERENCE_TEXT}
    raw, clone_seconds = send("/audio/voices", json.dumps(payload).encode("utf-8"), "application/json")
    state["voice_id"] = json.loads(raw)["id"]
    save_json(STATE_FILE, state)
print("个性化音色已准备。")
```

### 4.6 Synthesize new text with the personalized voice

After cloning, use the same speech synthesis endpoint and set `voice` to the newly created voice ID. Both the reference recording and the new text are in English here, so `language` is `en`.

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

The complete API sequence is [upload a file](https://platform.stepfun.com/docs/zh/api-reference/files/create) → [create a voice](https://platform.stepfun.com/docs/zh/api-reference/audio/create-voice) → [synthesize speech](https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio). To synthesize different text later, reuse `state["voice_id"]` and run only the synthesis stage.

## 5. Compare the voices and interpret audio timing

Play the reference recording, then the newly synthesized speech. Assess voice identity, delivery, clarity, and completeness separately. Because the new text differs from the original, you can listen for whether voice characteristics carry over. Voice similarity requires listening; a valid file format only confirms that the audio can be read.

The following code saves the preset-voice comparison records. `generation_to_audio_duration` divides the full generation-request time by the generated audio duration to show the relationship between generation time and content length. This guide receives complete WAV files and does not measure streaming time to first chunk.

```python
all_records = [baseline, *variants]
save_json(OUTPUT_DIR / "records.json", all_records)
for row in all_records:
    print({"文件": row["file"], "完整请求耗时_秒": round(row["elapsed_seconds"], 2),
           "音频时长_秒": round(row["duration_seconds"], 2),
           "生成耗时与音频时长之比": round(row["generation_to_audio_duration"], 2),
           "采样率": row["sample_rate"]})
```

For each clip, listen for omissions, repetition, truncation, and the expected pronunciation of target words. Keep text and voice fixed when comparing rates. Keep text, rate, and pronunciation settings fixed when comparing voices. Each record retains its request parameters so you can synthesize the clip again.

## 6. Use your own text and voice

For a preset voice, replace `TEXT` and `VOICE` and reuse `synthesize()`. For a personal recording, replace `REFERENCE` and its verbatim transcript in `REFERENCE_TEXT`, choose a new `STATE_DIR`, and run the steps in order starting with reference-file checks. After changing `NEW_TEXT`, run only the new-text synthesis stage.

If the reference voice and target text are Chinese, set the corresponding language to `zh` and supply a Chinese transcript that matches the recording word for word. In your application, play the result at the actual sample rate stored in the WAV file. Retain the new voice ID and input version so you can regenerate audio under the same account.

Last updated: 2026-09-27. The code runs in a standard Python project; the companion Notebook is an optional format with the same content. Model identifiers and API field names remain in English.
