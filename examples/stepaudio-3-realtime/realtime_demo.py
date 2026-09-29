"""StepAudio 3 Realtime 实时语音：最小对话与 VAD 调参
默认运行最小示例；--full 执行正文全部实验。参数按原文章分组，可直接修改。"""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def main(full=False):
    # 2.5 配置连接和音频设备
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
    REGION = os.environ.get("STEPFUN_REGION", "cn")
    ENDPOINTS = {"cn": "wss://api.stepfun.com/v1/realtime",
                 "global": "wss://api.stepfun.ai/v1/realtime"}
    AUDIO_CONFIG = {"input_rate": 24000, "output_rate": 24000,
                    "input_device": None, "output_device": None, "block_ms": 20}

    # 2.6 识别设备并检查格式
    import sounddevice as sd
    print(sd.query_devices())
    sd.check_input_settings(device=AUDIO_CONFIG["input_device"], channels=1,
                            dtype="int16", samplerate=AUDIO_CONFIG["input_rate"])
    sd.check_output_settings(device=AUDIO_CONFIG["output_device"], channels=1,
                             dtype="int16", samplerate=AUDIO_CONFIG["output_rate"])
    print("设备接受当前音频格式。")

    # 3.1 参数组：助手要求与 VAD
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

    # 3.2 客户端配置：音频缓冲与分块
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

    # 3.2 客户端配置：音频缓冲与分块
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

    # 3.3 将收音队列连接到 WebSocket
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

    # 3.4 话轮事件：VAD 与本地打断
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

    # 3.5 响应事件：字幕、音频与响应标识
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

    # 3.6 会话初始化与事件分发
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

    # 3.7 用连接对象组合这些组件
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

    # 3.8 在终端启动一轮对话
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

    # 3.8 在终端启动一轮对话
    api_key = os.environ.get("STEP_API_KEY", "").strip() or getpass.getpass("StepFun API Key（隐藏输入）：").strip()
    if not api_key:
        raise ValueError("需要 API Key 才能启动会话")

    # 3.8 在终端启动一轮对话
    RUN_RESULTS.append(run_session(SETTINGS, "A-baseline", api_key))
    print(json.dumps(RUN_RESULTS[-1], ensure_ascii=False, indent=2))

    if not full:
        Path("baseline.json").write_text(
            json.dumps(RUN_RESULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    # 4.1 `silence_duration_ms`：等待用户说完
    B_SETTINGS = {**SETTINGS, "silence_duration_ms": 300}
    RUN_RESULTS.append(run_session(B_SETTINGS, "B-silence-300", api_key))
    print(json.dumps(RUN_RESULTS[-1], ensure_ascii=False, indent=2))

    # 5. 读取事件记录与实际听感
    if RUN_RESULTS:
        result_dir = Path("realtime_results")
        result_dir.mkdir(exist_ok=True)
        result_file = result_dir / ("sessions_" + uuid.uuid4().hex[:8] + ".json")
        result_file.write_text(json.dumps(RUN_RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
        print("结果文件：", result_file)

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
