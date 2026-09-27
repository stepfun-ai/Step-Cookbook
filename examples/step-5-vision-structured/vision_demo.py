"""Step 5 Preview 图像理解与结构化输出：从图片到可用 JSON
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
        key = os.environ.get("STEPFUN_API_KEY", "").strip()
        if not key:
            key = getpass.getpass("输入 StepFun API 密钥（隐藏输入，不保存到文件）：").strip()
        if not key:
            raise ValueError("未提供密钥，已停止。")
        return key

    import base64

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

    # 2.6 设置 HTTP 超时与响应读取
    def chat(payload: dict, key: str, region: str = "cn") -> tuple[dict, float]:
        body, elapsed, _ = post(payload, key, region)
        data = json.loads(body)
        if not isinstance(data, dict) or not data.get("choices"):
            raise ValueError("响应没有 choices，不能作为一次成功生成。")
        return data, elapsed

    def response_record(data: dict) -> dict:
        choice = data["choices"][0]
        message = choice.get("message", {})
        return {"response_id": data.get("id"), "returned_model": data.get("model"),
                "finish_reason": choice.get("finish_reason"), "content": message.get("content"),
                "refusal": message.get("refusal"), "usage": data.get("usage")}

    def save_json(path: Path, value) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    # 2.6 设置 HTTP 超时与响应读取
    api_key = get_key()

    # 3.1 定义字段和输出约束
    MODEL = "step-5-preview"
    ASSET_DIR = PACKAGE_DIR / "assets/vision"
    IMAGES = [
        {"file": "clear.png", "expected": {"A": 12, "B": 7, "C": 5}},
        {"file": "missing.png", "expected": {"A": 12, "B": 7, "C": None}},
        {"file": "adapted.png", "expected": {"A": 12, "B": 9, "C": 5}},
    ]
    for item in IMAGES:
        if not (ASSET_DIR / item["file"]).is_file():
            raise FileNotFoundError(f"请把随文图片放到 {ASSET_DIR}：{item['file']}")

    # 3.1 定义字段和输出约束
    SCHEMA = {"type": "object", "properties": {k: {"type": ["integer", "null"]} for k in ["A", "B", "C"]},
              "required": ["A", "B", "C"], "additionalProperties": False}

    # 3.1 定义字段和输出约束
    IMAGE_DETAIL = "high"
    STRICT_SCHEMA = True

    def request_for(image_path, model):
        raw = image_path.read_bytes()
        if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 10_000_000:
            raise ValueError("本示例只接受小于 10 MB 的 PNG；这是示例自身的范围。")
        return {"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": "读取图片表格中 A、B、C 对应的数值。只依据图片；空白或无法辨认的值填 null，不要猜测。"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw).decode(), "detail": IMAGE_DETAIL}}]}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "table_values", "strict": STRICT_SCHEMA, "schema": SCHEMA}},
            "reasoning_effort": "low", "max_tokens": 4096, "stream": False}

    # 3.1 定义字段和输出约束
    def grade(content, expected):
        try:
            obj = json.loads(content)
        except (ValueError, TypeError):
            return {"parse_ok": False, "schema_ok": False, "correct_fields": 0, "all_correct": False}
        valid = isinstance(obj, dict) and set(obj) == set(SCHEMA["required"]) and all(v is None or type(v) is int for v in obj.values())
        correct = sum(k in obj and type(obj[k]) is type(v) and obj[k] == v for k, v in expected.items()) if valid else 0
        return {"parse_ok": True, "schema_ok": valid, "correct_fields": correct,
                "evaluated_fields": len(expected), "all_correct": valid and correct == len(expected), "parsed": obj}

    # 3.2 发出一次请求并查看字段
    def read_image(item):
        data, elapsed = chat(request_for(ASSET_DIR / item["file"], MODEL), api_key, REGION)
        row = {"file": item["file"], "elapsed_seconds": elapsed, **response_record(data)}
        row["checks"] = grade(row["content"], item["expected"])
        row["success"] = (row["finish_reason"] == "stop" and not row["refusal"]
                          and row["checks"]["all_correct"])
        return row

    # 3.2 发出一次请求并查看字段
    clear_result = read_image(IMAGES[0])
    print(json.dumps(clear_result, ensure_ascii=False, indent=2))

    if not full:
        Path("baseline.json").write_text(
            json.dumps(clear_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    # 4.1 让缺失值有明确表达
    missing_result = read_image(IMAGES[1])
    print(json.dumps(missing_result, ensure_ascii=False, indent=2))

    # 5. 读取本次结果
    results = [clear_result, missing_result]
    for row in results:
        check = row["checks"]
        print(row["file"], {
            "JSON可解析": check["parse_ok"], "字段类型符合要求": check["schema_ok"],
            "正确字段数": check["correct_fields"], "对象符合要求": row["success"],
            "完整响应耗时_秒": round(row["elapsed_seconds"], 2),
        })
    output_dir = Path("vision_results")
    output_dir.mkdir(exist_ok=True)
    save_json(output_dir / "records.json", results)

    # 6. 换一张图片，再接入自己的字段
    my_result = read_image(IMAGES[2])
    print(json.dumps(my_result, ensure_ascii=False, indent=2))
    save_json(output_dir / "my_image.json", my_result)

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
