# Step 5 Preview 工具调用：从函数定义到结果回传

**简体中文** | [English](../en/README.md)

> 中英文版本介绍相同的模型能力和主要流程；示例输入、提示词、输出字段和校验细节可能不同，请以所读版本的代码为准。配套 Python 脚本与 Notebook 对应中文版。

## 1. 认识模型与工具调用

Step 5 Preview 接收消息并生成回复，也可以在回复中提出工具调用请求。应用把可用函数描述放入 `tools`，模型返回函数名与参数，应用执行后再把结果传回，模型据此继续处理。[模型概览](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview) · [工具调用机制](https://platform.stepfun.ai/docs/en/api-reference/tool-call)

这条分工决定了工具集成的核心：模型负责选择调用，程序负责参数检查、实际执行与结果回传。例如接入计算或数据查询时，真实数据来自本地函数或后端服务；对话中的调用标识负责连接请求与结果。

本篇面向会写 Python 函数、希望把模型接入现有服务的开发者。我们实现一个加法／除法工具，重点解释工具描述、`tool_choice`、调用次数限制与消息回传。

**本文路线：** 初始化客户端 → 定义工具接口 → 编写执行函数 → 完成调用循环 → 替换业务函数。

## 2. 前置条件与环境准备

### 2.1 前置条件

**需要掌握：** Python 函数、字典与 JSON；了解一次请求如何返回结果。不要求预先接入特定开发框架。

**需要准备：**

- Python 3.10 或以上版本、一个终端和任意代码编辑器。
- [StepFun 开放平台](https://platform.stepfun.com/)账号，已创建 API Key，并确认可以调用 `step-5-preview`。
- 可以访问所用区域 API 的网络环境。真实调用会使用账户额度。

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

在项目中新建 `tool_demo.py`，将本文的 **Python 代码块按顺序放进这个文件**；`bash` 和 `powershell` 代码块只在终端执行。完成定义与调用后运行：

```bash
python tool_demo.py
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

import math
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
```

`chat()` 将聊天响应解析成字典，`response_record()` 提取最终内容和用量，`save_json()` 保存本次结果。已有项目可以把这三项放到自己的响应处理层；它们不改变发送给模型的能力参数。

```python
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
```

```python
api_key = get_key()
```

## 3. 实现一次完整工具调用

### 3.1 告诉模型有什么工具

`TOOL` 是发给模型的接口描述，包含名称、用途和参数。这里限制为两种操作和两个数值，读者可以直接看清模型发来的参数如何映射到 Python 函数。

```python
TOOL = {"type": "function", "function": {"name": "calculate",
    "description": "对两个有限数值做加法或除法。需要算术运算时使用；不处理问候。除数不能为零。",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["add", "divide"]},
        "a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["operation", "a", "b"], "additionalProperties": False}}}
```

### 3.2 实现程序真正执行的函数

`execute()` 根据工具名找到实现，再检查参数并执行。结果统一为可序列化的对象，供下一轮模型读取。程序只执行明确定义的运算，不运行模型生成的任意代码。

```python
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
```

### 3.3 把调用、执行和回传连起来

每轮模型请求都会携带已有消息和工具描述。收到 `tool_calls` 后，先保留这条助手消息，再逐条执行并附加 `role="tool"` 消息；`tool_call_id` 把结果与原调用关联。没有新的工具调用时读取最终回答。

先定义最终结果的读取规则，再配置调用策略与循环上限。`trace` 记录响应和耗时，`tool_calls` 记录实际执行的参数与结果。

```python
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
```

**参数组：模型选择工具与客户端预算。** `tool_choice="auto"` 让模型根据输入决定是否调用工具。`max_rounds`、`max_tool_calls` 是本地循环限制，分别限制模型请求轮数与实际执行次数，不会作为模型参数发送。它们可以按项目的时延和成本要求独立调整。

```python
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
```

每次模型选择工具后，程序先追加原助手消息，再追加带有匹配 `tool_call_id` 的结果。这个顺序使下一轮请求能够理解工具结果对应哪个调用。网络异常会向调用入口抛出，由业务层决定如何处理。

### 3.4 运行一个两步运算

请求先求 18 + 6，再除以 4。完整结果应为 6；工具执行记录可以看到程序算出的中间值与最终值。

```python
MODEL = "step-5-preview"
task = {"text": "请用工具计算 (18 + 6) / 4。", "answer": 6, "needs_tool": True}
call_api = lambda payload: chat(payload, api_key, REGION)
result = run_loop(task, call_api, model=MODEL, **TOOL_OPTIONS)
print(json.dumps(result, ensure_ascii=False, indent=2))
```

## 4. 理解调用策略与循环状态

| 关键位置 | 作用 | 集成时保留什么 |
| --- | --- | --- |
| `tool_choice="auto"` | 让模型结合任务决定是否调用 | 工具描述要明确适用范围 |
| `messages.append(assistant)` | 保留模型请求调用工具的那条消息 | 后续回传与它保持连续 |
| `tool_call_id` | 将一个结果绑定到一个调用 | 每个调用都回传对应结果 |
| `reasoning_content` | 服务端返回时，按协议带回下一轮 | 不把它当最终答案展示 |
| `max_rounds`、`max_tool_calls` | 给循环明确的结束条件 | 根据项目预算设置上限 |

再发一个普通问候，观察 `auto` 策略：任务不需要计算时，模型可以直接给最终回答。

```python
greeting_task = {"text": "你好。请只回复问候，不调用计算工具。", "answer": "你好", "needs_tool": False}
greeting = run_loop(greeting_task, call_api, model=MODEL, **TOOL_OPTIONS)
print(json.dumps(greeting, ensure_ascii=False, indent=2))
```

问候结果的 `tool_calls` 应为空；措辞可以不同。此处核对的是任务是否需要工具，以及模型是否按这个条件行动。

## 5. 从实际执行记录理解结果

对计算任务同时看三项：最终值为 6、工具确实被执行、执行结果支持最终值。下面把最关心的内容提取出来，并保存完整轨迹，便于在自己的项目中追踪调用过程。

```python
print("最终回答：", result.get("final"))
print("实际工具调用次数：", len(result["tool_calls"]))
for item in result["tool_calls"]:
    print(item["name"], item["arguments"], "→", item["result"])
print("是否符合这条任务的要求：", result["success"])
output_dir = Path("tool_results")
output_dir.mkdir(exist_ok=True)
save_json(output_dir / "calculation.json", result)
save_json(output_dir / "greeting.json", greeting)
```

`trace` 中每轮耗时是完整模型响应耗时。工具执行本身在本例中是本地算术；接入远程查询时，可以在 `execute()` 中另行记录工具耗时。最终回答的格式、实际执行过程和循环轮数对应不同问题，应分别观察。

## 6. 替换输入，再接入自己的工具

先把输入改为 (20 + 8) / 4，参考答案改为 7，再运行原来的循环。

```python
my_task = {"text": "请用工具计算 (20 + 8) / 4。", "answer": 7, "needs_tool": True}
my_result = run_loop(my_task, call_api, model=MODEL, **TOOL_OPTIONS)
print(json.dumps(my_result, ensure_ascii=False, indent=2))
save_json(output_dir / "my_task.json", my_result)
```

接自己的工具时，同步修改 `TOOL` 的名称与 Schema、`execute()` 的分发和实现，以及最终结果的业务核对规则。继续保留消息回传、调用标识和轮数限制。这样模型负责决定调用，本地服务负责执行，应用可以基于真实工具结果继续处理。

接口依据：[StepFun 工具调用](https://platform.stepfun.ai/docs/en/api-reference/tool-call)。

更新日期：2026-09-29。正文代码面向普通 Python 项目；配套 Notebook 为同内容的可选形式。模型标识与接口字段保留英文。
