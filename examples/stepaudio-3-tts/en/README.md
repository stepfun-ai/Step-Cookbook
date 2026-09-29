# StepAudio 3 TTS: Control speaking rate, pronunciation, and personalized voices

[简体中文](../zh-CN/README.md) | **English**

> The Chinese and English guides cover the same model capabilities and main workflows. Sample inputs, prompts, output fields, and validation details may differ; follow the code in the guide you are reading. The companion Python scripts and Notebooks follow the Chinese guide.

## 1. Understand text-to-speech and personalized voices

StepAudio 3 TTS converts text into speech: your application supplies the text and voice configuration, and the API returns synthesized audio. It supports both non-streaming and streaming synthesis. This guide uses non-streaming synthesis to save complete WAV files for playback and comparison. [Model overview](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-tts)

The parameters have distinct roles: `voice` selects the voice identity, `speed` controls speaking rate, and `pronunciation_map` specifies how target words are pronounced. To use a personalized voice, first create it from a reference recording and its transcript, then pass it as `voice` in a synthesis request. [Speech synthesis API](https://platform.stepfun.ai/docs/en/api-reference/audio/create-audio)

This guide is for Python developers who need to generate speech in an application. You will synthesize one sentence, adjust rate and pronunciation separately, and then complete the full workflow: upload a reference recording → create a voice → synthesize new text.

**Workflow:** Configure the client → Synthesize and save a WAV file → Compare parameters → Create a personalized voice → Integrate it into your project.

## 2. Prerequisites and setup

### 2.1 Prerequisites

**Required knowledge:** Familiarity with Python functions, dictionaries, and JSON.

- Python 3.10 or later.
- A StepFun API key with access to `stepaudio-3-tts`.
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

### 2.3 Dependencies

This example uses only the Python standard library.

### 2.4 Configure credentials and run the example

Set `STEP_API_KEY` in the terminal that will run the example. Replace `YOUR_STEP_API_KEY` with your API key.

macOS / Linux:

```bash
export STEP_API_KEY="YOUR_STEP_API_KEY"
```

Windows PowerShell:

```powershell
$env:STEP_API_KEY = "YOUR_STEP_API_KEY"
```

Run the Python commands below in the same terminal. For a Notebook, start Jupyter from that terminal so its kernel inherits the variable. If the variable is unset, the code prompts for the key with input hidden.

Set `REGION = "cn"` for the China region, which uses `.com` endpoints, or `"global"` for the international region, which uses `.ai` endpoints. Use a key issued for the selected region.

Create `tts_demo.py` in your project and **copy this guide's Python code blocks into that file in order**. Run the `bash` and `powershell` blocks only in a terminal. After adding the definitions and calls, run:

```bash
python tts_demo.py
```

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
    key = os.environ.get("STEP_API_KEY", "").strip()
    if not key:
        key = getpass.getpass("Enter your StepFun API key (input hidden): ").strip()
    if not key:
        raise ValueError("No API key provided.")
    return key

import io
import wave
import hashlib
import uuid
```

### 2.6 Set the HTTP timeout and read responses

The `post()` helper sends an HTTP request and returns the response bytes, full-response time, and content type. `HTTP_TIMEOUT_SECONDS` sets the timeout for blocking network operations.

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
        raise RuntimeError(f"HTTP {exc.code}: Check the region, permissions, quota, and request fields. This example does not retry automatically.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError(f"Connection failed or a network operation exceeded the {HTTP_TIMEOUT_SECONDS}-second timeout.") from None
    elapsed = time.perf_counter() - start
    return body, elapsed, content_type

def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
```

`post()` returns audio bytes, and `save_json()` saves configuration and result records. Audio parsing and file saving are implemented in the synthesis step.

```python
api_key = get_key()
```

The synthesis model is `stepaudio-3-tts`, and the initial preset voice is `zixinnansheng`. The personalized voice section uploads the supplied recording, creates a voice in your account, and synthesizes new text. For model details, see [StepAudio 3 TTS](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-tts).

## 3. Generate an audio clip

### 3.1 Prepare the text and request

The sample sentence contains the abbreviation "LOL". Compare speaking rates, then use a pronunciation override to replace the abbreviation with a spoken phrase. Change one parameter at a time.

```python
MODEL = "stepaudio-3-tts"
VOICE = "zixinnansheng"
TEXT = "The message says LOL, and everyone smiles."
OUTPUT_DIR = Path("tts_results")
OUTPUT_DIR.mkdir(exist_ok=True)
```

**Parameter group: voice, speaking rate, and pronunciation overrides.** Set `voice` to a preset or personalized voice ID available to your account. `speed` ranges from 0.5 to 2.0, with a starting value of 1.0. This example fixes `language="en"` and `response_format="wav"` so language and file format remain consistent across comparisons.

```python
VARIANTS = {"baseline": {}, "slow": {"speed": 0.8}, "fast": {"speed": 1.2},
            "pronunciation": {"pronunciation_map": {"tone": ["LOL/laugh out loudly"]}}}

def request_for(text, voice, variant, model="stepaudio-3-tts"):
    if not 1 <= len(text) <= 1000:
        raise ValueError("Each request in this example must contain 1-1000 characters.")
    if not voice.strip():
        raise ValueError("Specify a voice ID available to your account.")
    return {"model": model, "input": text, "voice": voice, "language": "en",
            "response_format": "wav", "speed": 1.0, **VARIANTS[variant]}
```

When changing `speed`, keep the text and `voice` fixed. When changing `voice`, keep the rate fixed. Each entry in `pronunciation_map.tone` uses `source/replacement` syntax; `LOL/laugh out loudly` specifies the spoken replacement for "LOL". The following function reads WAV metadata to confirm the returned format and duration.

```python
def inspect_wav(raw):
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("The response is not a recognized WAV file; no audio file was saved.")
    with wave.open(io.BytesIO(raw), "rb") as wav:
        if wav.getnframes() <= 0:
            raise ValueError("The returned audio contains no sample frames.")
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

The following two blocks focus on `speed` and `pronunciation_map`, changing one setting at a time. `slow` sets the rate to 0.8, and `fast` sets it to 1.2. `pronunciation` keeps the default rate and uses `pronunciation_map` to specify a spoken replacement for "LOL".

**First compare `speed`.** Synthesize the same sentence at 0.8 and 1.2, then compare file duration and the rhythm you hear.

```python
variants = [synthesize(TEXT, VOICE, name, name) for name in ["slow", "fast"]]
for row in variants:
    print(row["file"], round(row["duration_seconds"], 2), "seconds")
```

**Then compare `pronunciation_map`.** Use the default rate and override only "LOL". Compare the generated file with `baseline.wav` and check whether the abbreviation is spoken as "laugh out loudly".

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
        raise ValueError("The reference WAV must be 5-10 seconds long.")
    if meta["channels"] != 1 or meta["sample_width"] != 2:
        raise ValueError("This example requires a mono, 16-bit PCM WAV file.")
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
        raise RuntimeError(f"HTTP {exc.code}: Check the region, permissions, and request fields.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Connection failed or a network operation timed out.") from None
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
    raise ValueError("The reference input has changed. Use a different STATE_DIR for the new input.")
```

### 4.4 Upload the original recording

The multipart request contains two parts: `purpose` and the audio file. Save the returned file ID in the state so it can be reused next time.

```python
if not state.get("file_id"):
    body, content_type = upload_body(reference_audio)
    raw, upload_seconds = send("/files", body, content_type)
    state["file_id"] = json.loads(raw)["id"]
    save_json(STATE_FILE, state)
print("The reference file is ready.")
```

### 4.5 Create a voice from the recording and transcript

The `id` in the creation response becomes the `voice` value for subsequent synthesis. Save the API's returned value directly. When switching accounts, create the voice again under that account.

```python
if not state.get("voice_id"):
    payload = {"model": MODEL, "file_id": state["file_id"], "text": REFERENCE_TEXT}
    raw, clone_seconds = send("/audio/voices", json.dumps(payload).encode("utf-8"), "application/json")
    state["voice_id"] = json.loads(raw)["id"]
    save_json(STATE_FILE, state)
print("The personalized voice is ready.")
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
    print({"file": row["file"], "full_request_seconds": round(row["elapsed_seconds"], 2),
           "audio_duration_seconds": round(row["duration_seconds"], 2),
           "generation_to_audio_duration": round(row["generation_to_audio_duration"], 2),
           "sample_rate": row["sample_rate"]})
```

For each clip, listen for omissions, repetition, truncation, and the expected pronunciation of target words. Keep text and voice fixed when comparing rates. Keep text, rate, and pronunciation settings fixed when comparing voices. Each record retains its request parameters so you can synthesize the clip again.

## 6. Use your own text and voice

For a preset voice, replace `TEXT` and `VOICE` and reuse `synthesize()`. For a personal recording, replace `REFERENCE` and its verbatim transcript in `REFERENCE_TEXT`, choose a new `STATE_DIR`, and run the steps in order starting with reference-file checks. After changing `NEW_TEXT`, run only the new-text synthesis stage.

If the reference voice and target text are Chinese, set the corresponding language to `zh` and supply a Chinese transcript that matches the recording word for word. In your application, play the result at the actual sample rate stored in the WAV file. Retain the new voice ID and input version so you can regenerate audio under the same account.

## 7. Companion code and starter project

This example includes a Jupyter Notebook, an editable Python script, and a starter project for running and adapting the code. Browse the [example directory](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts) for all files, or see the [setup and launch guide](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/README.md) for instructions.

| Resource | How to use it |
| --- | --- |
| [Jupyter Notebook](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/05_StepAudio3_TTS.ipynb) | Work through the example cell by cell and inspect the inputs and results at each step. |
| [Python example script](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/tts_demo.py) | Run the minimal example or full experiment from a terminal, or adapt the code for your application. |
| [macOS launcher](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/%E5%90%AF%E5%8A%A8.command) · [Windows launcher](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/%E5%90%AF%E5%8A%A8.bat) · [launcher menu](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/launcher.py) | Prepare the runtime, then choose the minimal example or full experiment and the API region. |
| [Environment configuration](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts/setup) · [locked dependencies](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/setup/requirements.lock) | Inspect the setup scripts, dependency versions, and environment checks. |
| [Reference audio and text](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts/assets/voice_reference) · [source information](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/assets/voice_reference/SOURCE.md) | Find the reference recording, transcript, new synthesis text, synthesized example, and provenance details. |

To use the launchers, obtain the complete example directory from the current repository and keep its relative paths intact. Initial setup requires an internet connection. The supplied Notebook, Python script, launch menu, and setup guide currently follow the Chinese version. To reproduce this guide's English prompts, sample inputs, and result fields, use the Python code blocks in this guide.

Last updated: 2026-09-29.
