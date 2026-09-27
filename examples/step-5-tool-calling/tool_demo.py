"""Step 5 Preview 工具调用：从函数定义到结果回传
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

    import math

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

    # 3.1 告诉模型有什么工具
    TOOL = {"type": "function", "function": {"name": "calculate",
        "description": "对两个有限数值做加法或除法。需要算术运算时使用；不处理问候。除数不能为零。",
        "parameters": {"type": "object", "properties": {
            "operation": {"type": "string", "enum": ["add", "divide"]},
            "a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["operation", "a", "b"], "additionalProperties": False}}}

    # 3.2 实现程序真正执行的函数
    def execute(name, arguments):
        try:
            if name != "calculate":
                raise ValueError("未知工具")
            args = json.loads(arguments)
            if not isinstance(args, dict) or set(args) != {"operation", "a", "b"}:
                raise ValueError("必须提供 operation、a、b，且不能有额外字段")
            a, b = args["a"], args["b"]
            if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e12 for v in [a, b]):
                raise ValueError("两个操作数必须为绝对值不超过 1e12 的有限数值")
            if args["operation"] == "add":
                value = a + b
            elif args["operation"] == "divide" and b != 0:
                value = a / b
            elif args["operation"] == "divide":
                return {"ok": False, "error": "除数不能为零"}
            else:
                raise ValueError("operation 仅支持 add 或 divide")
            return {"ok": True, "value": value}
        except (ValueError, TypeError, OverflowError) as exc:
            return {"ok": False, "error": str(exc)}

    # 3.3 把调用、执行和回传连起来
    def finish_tool_result(task, choice, calls, trace):
        message = choice["message"]
        complete = choice.get("finish_reason") == "stop" and not message.get("refusal")
        try:
            parsed = json.loads(message.get("content"))
            answer = parsed["answer"]
            if task["needs_tool"]:
                same = type(answer) in (int, float) and answer == task["answer"]
            else:
                same = isinstance(answer, str) and answer.strip().startswith("你好")
        except (ValueError, TypeError, KeyError):
            same = False
        behavior = bool(calls) == task["needs_tool"]
        if task["needs_tool"]:
            behavior = behavior and any(c["result"].get("ok") and
                                       c["result"].get("value") == task["answer"] for c in calls)
        return {"success": bool(complete and same and behavior), "trace": trace,
                "tool_calls": calls, "final": message.get("content")}

    # 3.3 把调用、执行和回传连起来
    TOOL_OPTIONS = {"tool_choice": "auto", "max_rounds": 5, "max_tool_calls": 8}

    def run_loop(task, call_api, model="step-5-preview", max_rounds=5,
                 tool_choice="auto", max_tool_calls=8):
        messages = [
            {"role": "system", "content": "需要算术运算时使用 calculate 工具，不能声称执行未调用的工具。工具失败时如实说明。最终回答仅输出 JSON 对象，包含 answer 和 explanation；answer 是数值、问候字符串或无法完成时的 null。"},
            {"role": "user", "content": task["text"]},
        ]
        trace, calls = [], []
        for round_no in range(1, max_rounds + 1):
            payload = {"model": model, "messages": messages, "tools": [TOOL],
                       "tool_choice": tool_choice, "reasoning_effort": "low",
                       "max_tokens": 4096, "stream": False}
            data, elapsed = call_api(payload)
            choice = data["choices"][0]
            message = choice["message"]
            trace.append({"round": round_no, "elapsed_seconds": elapsed, **response_record(data)})
            requested = message.get("tool_calls") or []
            if not requested:
                return finish_tool_result(task, choice, calls, trace)
            if choice.get("finish_reason") not in ("tool_calls", "stop"):
                raise RuntimeError("工具调用响应未完整结束")
            if len(requested) > 4 or len(calls) + len(requested) > max_tool_calls:
                raise RuntimeError("本次请求超过工具调用预算")
            assistant = {k: message[k] for k in ("role", "content", "tool_calls", "reasoning_content") if k in message}
            assistant["role"] = "assistant"
            messages.append(assistant)
            for item in requested:
                if not item.get("id") or not isinstance(item.get("function"), dict):
                    raise ValueError("工具调用缺少标识或函数参数")
                function = item["function"]
                result = execute(function.get("name"), function.get("arguments"))
                calls.append({"id": item["id"], "name": function.get("name"),
                              "arguments": function.get("arguments"), "result": result})
                messages.append({"role": "tool", "tool_call_id": item["id"],
                                 "content": json.dumps(result, ensure_ascii=False)})
        raise RuntimeError("达到模型请求轮数上限")

    # 3.4 运行一个两步运算
    MODEL = "step-5-preview"
    task = {"text": "请用工具计算 (18 + 6) / 4。", "answer": 6, "needs_tool": True}
    call_api = lambda payload: chat(payload, api_key, REGION)
    result = run_loop(task, call_api, model=MODEL, **TOOL_OPTIONS)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not full:
        Path("baseline.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    # 4. 理解调用策略与循环状态
    greeting_task = {"text": "你好。请只回复问候，不调用计算工具。", "answer": "你好", "needs_tool": False}
    greeting = run_loop(greeting_task, call_api, model=MODEL, **TOOL_OPTIONS)
    print(json.dumps(greeting, ensure_ascii=False, indent=2))

    # 5. 从实际执行记录理解结果
    print("最终回答：", result.get("final"))
    print("实际工具调用次数：", len(result["tool_calls"]))
    for item in result["tool_calls"]:
        print(item["name"], item["arguments"], "→", item["result"])
    print("是否符合这条任务的要求：", result["success"])
    output_dir = Path("tool_results")
    output_dir.mkdir(exist_ok=True)
    save_json(output_dir / "calculation.json", result)
    save_json(output_dir / "greeting.json", greeting)

    # 6. 替换输入，再接入自己的工具
    my_task = {"text": "请用工具计算 (20 + 8) / 4。", "answer": 7, "needs_tool": True}
    my_result = run_loop(my_task, call_api, model=MODEL, **TOOL_OPTIONS)
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
