"""Step 5 Preview 推理强度调参：比较结果质量、耗时与用量
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

    # 3.1 准备输入与明确答案
    MODEL = "step-5-preview"
    MAX_TOKENS = 4096
    SAMPLES = [
        {"id": "sum_even", "prompt": "把 18、7、26、13、12 中的偶数相加。只返回 JSON，字段 answer 为整数。", "answer": 56},
        {"id": "order", "prompt": "A、B、C、D 各出现一次。D 在 A 前，A 在 B 前，B 在 C 前。按从左到右的顺序排列。只返回 JSON，字段 answer 为四个字母组成的字符串，不含空格。", "answer": "DABC"},
        {"id": "count", "prompt": "在 1 到 30（包含两端）的整数中，能被 3 或 5 整除、但不能同时被二者整除的数共有几个？只返回 JSON，字段 answer 为整数。", "answer": 12},
    ]

    # 3.2 设置请求参数与结果处理
    def request_for(sample, effort, model, max_tokens):
        return {"model": model, "messages": [
            {"role": "system", "content": "完成给定任务，最终回答只输出要求的 JSON 对象。"},
            {"role": "user", "content": sample["prompt"]}],
            "reasoning_effort": effort, "response_format": {"type": "json_object"},
            "max_tokens": max_tokens, "stream": False}

    # 3.2 设置请求参数与结果处理
    def grade(content, expected) -> bool:
        try:
            value = json.loads(content)
            return (isinstance(value, dict) and set(value) == {"answer"}
                    and type(value["answer"]) is type(expected) and value["answer"] == expected)
        except (TypeError, ValueError):
            return False

    def run_case(sample, effort, repeat=1):
        payload = request_for(sample, effort, MODEL, MAX_TOKENS)
        data, elapsed = chat(payload, api_key, REGION)
        row = {"sample_id": sample["id"], "effort": effort, "repeat": repeat,
               "expected": sample["answer"], "elapsed_seconds": elapsed,
               **response_record(data)}
        row["success"] = (row["finish_reason"] == "stop" and not row["refusal"]
                          and grade(row["content"], sample["answer"]))
        return row

    # 3.2 设置请求参数与结果处理
    baseline = run_case(SAMPLES[0], "low")
    print(json.dumps(baseline, ensure_ascii=False, indent=2))

    if not full:
        Path("baseline.json").write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    # 4. 只调整推理强度，比较三组结果
    import random
    import statistics

    EFFORTS = ["low", "medium", "high"]
    REPEATS = 1
    jobs = [(sample, effort, repeat + 1)
            for sample in SAMPLES for effort in EFFORTS for repeat in range(REPEATS)]
    random.Random(42).shuffle(jobs)
    records = []
    output_dir = Path("reasoning_results")
    output_dir.mkdir(exist_ok=True)
    save_json(output_dir / "config.json", {
        "model": MODEL, "region": REGION, "max_tokens": MAX_TOKENS,
        "samples": SAMPLES, "efforts": EFFORTS, "repeats": REPEATS, "order_seed": 42,
    })
    for sample, effort, repeat in jobs:
        row = run_case(sample, effort, repeat)
        records.append(row)
        save_json(output_dir / "records.json", records)
        print(sample["id"], effort, row["success"], round(row["elapsed_seconds"], 2))

    # 5. 读懂结果，选择适合任务的配置
    summary = []
    for effort in EFFORTS:
        group = [row for row in records if row["effort"] == effort]
        timings = [row["elapsed_seconds"] for row in group]
        tokens = [(row.get("usage") or {}).get("total_tokens") for row in group]
        summary.append({
            "推理强度": effort, "实际次数": len(group),
            "符合要求次数": sum(row["success"] for row in group),
            "完整响应耗时中位数_秒": statistics.median(timings) if timings else None,
            "已报告总token": sum(n for n in tokens if n is not None),
            "用量缺失次数": sum(n is None for n in tokens),
        })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    save_json(output_dir / "summary.json", summary)

    # 6. 换成自己的任务
    my_sample = {
        "id": "sum_even_changed",
        "prompt": "把 18、7、26、13、14 中的偶数相加。只返回 JSON，字段 answer 为整数。",
        "answer": 58,
    }
    my_result = run_case(my_sample, "high")
    print(json.dumps(my_result, ensure_ascii=False, indent=2))
    save_json(output_dir / "my_task.json", my_result)

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
