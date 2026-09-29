"""StepAudio 3 TTS：语速、发音控制与个性化音色复刻
默认运行最小示例；--full 执行正文全部实验。参数按原文章分组，可直接修改。"""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def main(full=False):
    # 2.5 初始化连接与凭证
    import getpass
    import json
    import os
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    BASE_URLS = {"cn": "https://api.stepfun.com/v1", "global": "https://api.stepfun.ai/v1"}
    REGION = os.environ.get("STEPFUN_REGION", "cn")

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

    # 2.6 设置 HTTP 超时与响应读取
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

    # 2.6 设置 HTTP 超时与响应读取
    api_key = get_key()

    # 3.1 准备文本与请求
    MODEL = "stepaudio-3-tts"
    VOICE = "zixinnansheng"
    TEXT = "重庆的银行今天营业。请保持自然的语速。"
    OUTPUT_DIR = Path("tts_results")
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 3.1 准备文本与请求
    VARIANTS = {"baseline": {}, "slow": {"speed": 0.8}, "fast": {"speed": 1.2},
                "pronunciation": {"pronunciation_map": {"tone": ["重/chong2", "行/hang2"]}}}

    def request_for(text, voice, variant, model="stepaudio-3-tts"):
        if not 1 <= len(text) <= 1000:
            raise ValueError("本篇每次合成 1–1000 个字符。")
        if not voice.strip():
            raise ValueError("请指定当前账号可用的音色 ID。")
        return {"model": model, "input": text, "voice": voice, "language": "zh",
                "response_format": "wav", "speed": 1.0, **VARIANTS[variant]}

    # 3.1 准备文本与请求
    def inspect_wav(raw):
        if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            raise ValueError("返回内容不是可识别的 WAV；未保存成音频。")
        with wave.open(io.BytesIO(raw), "rb") as wav:
            if wav.getnframes() <= 0:
                raise ValueError("返回音频没有采样帧。")
            return {"duration_seconds": wav.getnframes()/wav.getframerate(),
                    "sample_rate": wav.getframerate(), "channels": wav.getnchannels(), "sample_width": wav.getsampwidth()}

    # 3.1 准备文本与请求
    def synthesize(text, voice, variant, label):
        payload = request_for(text, voice, variant, MODEL)
        raw, elapsed, content_type = post(payload, api_key, REGION, "/audio/speech")
        meta = inspect_wav(raw)
        target = OUTPUT_DIR / (label + ".wav")
        target.write_bytes(raw)
        return {"file": str(target), "request": payload, "elapsed_seconds": elapsed,
                "content_type": content_type, **meta,
                "generation_to_audio_duration": elapsed / meta["duration_seconds"]}

    # 3.1 准备文本与请求
    baseline = synthesize(TEXT, VOICE, "baseline", "baseline")
    print(json.dumps(baseline, ensure_ascii=False, indent=2))

    if not full:
        Path("baseline.json").write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    # 4.1 比较语速与发音控制
    variants = [synthesize(TEXT, VOICE, name, name) for name in ["slow", "fast"]]
    for row in variants:
        print(row["file"], round(row["duration_seconds"], 2), "秒")

    # 4.1 比较语速与发音控制
    pronunciation = synthesize(TEXT, VOICE, "pronunciation", "pronunciation")
    variants.append(pronunciation)
    print(pronunciation["file"])

    # 4.2 准备个性化复刻的原录音
    REFERENCE = PACKAGE_DIR / "assets/voice_reference/LJ025-0076.wav"
    REFERENCE_TEXT = "Many animals of even complex structure which live parasitically within others are wholly devoid of an alimentary cavity."
    NEW_TEXT = "This is a synthetic voice demonstration. The reference recording defines the voice, while this sentence provides new content."
    LANGUAGE = "en"

    # 4.2 准备个性化复刻的原录音
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

    # 4.2 准备个性化复刻的原录音
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

    # 4.2 准备个性化复刻的原录音
    reference_meta = inspect_reference(REFERENCE)
    reference_audio = REFERENCE.read_bytes()
    print(json.dumps(reference_meta, ensure_ascii=False, indent=2))

    # 4.3 保存本次参考输入，便于复用音色
    STATE_DIR = OUTPUT_DIR / "personal_voice"
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE = STATE_DIR / "state.json"
    fingerprint = {"audio_sha256": hashlib.sha256(reference_audio).hexdigest(),
                   "model": MODEL, "region": REGION, "reference_transcript": REFERENCE_TEXT}
    state = (json.loads(STATE_FILE.read_text(encoding="utf-8"))
             if STATE_FILE.exists() else {"input": fingerprint})
    if state.get("input") != fingerprint:
        raise ValueError("参考输入已改变，请为新录音设置另一个 STATE_DIR。")

    # 4.4 上传原录音
    if not state.get("file_id"):
        body, content_type = upload_body(reference_audio)
        raw, upload_seconds = send("/files", body, content_type)
        state["file_id"] = json.loads(raw)["id"]
        save_json(STATE_FILE, state)
    print("参考文件已准备。")

    # 4.5 用原录音和逐字稿创建音色
    if not state.get("voice_id"):
        payload = {"model": MODEL, "file_id": state["file_id"], "text": REFERENCE_TEXT}
        raw, clone_seconds = send("/audio/voices", json.dumps(payload).encode("utf-8"), "application/json")
        state["voice_id"] = json.loads(raw)["id"]
        save_json(STATE_FILE, state)
    print("个性化音色已准备。")

    # 4.6 用个性化音色合成新文本
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

    # 5. 对照原声，读懂音频与耗时
    all_records = [baseline, *variants]
    save_json(OUTPUT_DIR / "records.json", all_records)
    for row in all_records:
        print({"文件": row["file"], "完整请求耗时_秒": round(row["elapsed_seconds"], 2),
               "音频时长_秒": round(row["duration_seconds"], 2),
               "生成耗时与音频时长之比": round(row["generation_to_audio_duration"], 2),
               "采样率": row["sample_rate"]})

def cli():
    import argparse
    import datetime
    import os
    import uuid
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='运行正文全部实验；默认仅最小示例')
    parser.add_argument('--output-dir', type=Path, help='指定本次结果目录')
    args = parser.parse_args()
    run_name = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = (args.output_dir or PACKAGE_DIR / 'outputs' / (Path(__file__).stem + '-' + run_name)).resolve()
    output.mkdir(parents=True, exist_ok=True)
    print('本次结果目录：' + str(output), flush=True)
    os.chdir(output)
    try:
        main(full=args.full)
    except KeyboardInterrupt:
        print('已中止。')
        raise SystemExit(130)
    except Exception as exc:
        # 请求函数已把鉴权与网络错误转成不含请求头的提示。
        if isinstance(exc, (ValueError, RuntimeError)):
            print('本次未完成：' + str(exc))
        else:
            print('本次未完成：' + type(exc).__name__ + '；请检查网络、素材或音频设备。')
        raise SystemExit(1)


if __name__ == '__main__':
    cli()
