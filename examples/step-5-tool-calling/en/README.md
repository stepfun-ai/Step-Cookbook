# Step 5 Preview: Implement a complete tool-calling loop

[简体中文](../zh-CN/README.md) | **English**

> The Chinese and English guides cover the same model capabilities and main workflows. Sample inputs, prompts, output fields, and validation details may differ; follow the code in the guide you are reading. The companion Python scripts and Notebooks follow the Chinese guide.

## 1. Understand the model and tool calling

Step 5 Preview accepts messages and generates replies, and it can also request tool calls in its response. An application supplies descriptions of available functions in `tools`. The model returns a function name and arguments, the application executes the function and sends back the result, and the model continues from there. [Model overview](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview) · [Tool-calling protocol](https://platform.stepfun.ai/docs/en/api-reference/tool-call)

This division of responsibilities is central to tool integration: the model chooses calls, while the program validates arguments, executes functions, and returns results. For calculations or data queries, actual values come from local functions or backend services. Call identifiers in the conversation connect each request to its result.

This guide is for developers who write Python functions and want to connect a model to existing services. You will implement a tool for addition and division, focusing on tool descriptions, `tool_choice`, call limits, and result messages.

**Workflow:** Initialize the client → Define the tool interface → Implement execution → Complete the calling loop → Replace the business function.

## 2. Prerequisites and setup

### 2.1 Prerequisites

**Required knowledge:** Familiarity with Python functions, dictionaries, and JSON.

- Python 3.10 or later.
- A StepFun API key with access to `step-5-preview`.

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

Create `tool_demo.py` in your project and **copy this guide's Python code blocks into that file in order**. Run the `bash` and `powershell` blocks only in a terminal. After adding the definitions and calls, run:

```bash
python tool_demo.py
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

import math
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
        raise RuntimeError(f"HTTP {exc.code}: Check the region, permissions, quota, and request fields. This example does not retry automatically.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError(f"Connection failed or a network operation exceeded the {HTTP_TIMEOUT_SECONDS}-second timeout.") from None
    elapsed = time.perf_counter() - start
    return body, elapsed, content_type
```

`chat()` parses a chat response into a dictionary, `response_record()` extracts the final content and usage, and `save_json()` saves the results. In an existing project, these can form part of your response-handling layer. They do not change the capability parameters sent to the model.

```python
def chat(payload: dict, key: str, region: str = "cn") -> tuple[dict, float]:
    body, elapsed, _ = post(payload, key, region)
    data = json.loads(body)
    if not isinstance(data, dict) or not data.get("choices"):
        raise ValueError("The response is missing a nonempty choices array.")
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

## 3. Implement a complete tool call

### 3.1 Describe the available tool

`TOOL` is the interface description sent to the model. It includes the function name, purpose, and parameters. The example limits the interface to two operations and two numeric arguments so you can see how model-supplied arguments map to a Python function.

```python
TOOL = {"type": "function", "function": {"name": "calculate",
    "description": "Add or divide two finite numbers. Use for arithmetic, not greetings. The divisor must be nonzero.",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["add", "divide"]},
        "a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["operation", "a", "b"], "additionalProperties": False}}}
```

### 3.2 Implement the function your program executes

`execute()` dispatches by tool name, validates the arguments, and performs the operation. It returns a serializable object for the model to read in the next turn. The program executes only the explicitly defined operations, not arbitrary code generated by the model.

```python
def execute(name, arguments):
    try:
        if name != "calculate":
            raise ValueError("Unknown tool.")
        args = json.loads(arguments)
        if not isinstance(args, dict) or set(args) != {"operation", "a", "b"}:
            raise ValueError("Provide exactly operation, a, and b; no additional fields are allowed.")
        a, b = args["a"], args["b"]
        if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e12 for v in [a, b]):
            raise ValueError("Both operands must be finite numbers with an absolute value no greater than 1e12.")
        if args["operation"] == "add":
            value = a + b
        elif args["operation"] == "divide" and b != 0:
            value = a / b
        elif args["operation"] == "divide":
            return {"ok": False, "error": "The divisor must be nonzero."}
        else:
            raise ValueError("operation must be add or divide.")
        return {"ok": True, "value": value}
    except (ValueError, TypeError, OverflowError) as exc:
        return {"ok": False, "error": str(exc)}
```

### 3.3 Connect the request, execution, and result

Each model request includes the conversation so far and the tool description. When `tool_calls` arrives, first preserve that assistant message, then execute each call and append a `role="tool"` message. `tool_call_id` associates the result with the original call. When there are no new tool calls, read the final answer.

Define the final-result handling rules first, then configure the calling strategy and loop limits. `trace` records responses and elapsed time; `tool_calls` records the arguments and results of actual executions.

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
            same = isinstance(answer, str) and answer.strip().casefold().startswith(task["answer"].casefold())
    except (ValueError, TypeError, KeyError):
        same = False
    behavior = bool(calls) == task["needs_tool"]
    if task["needs_tool"]:
        behavior = behavior and any(c["result"].get("ok") and
                                   c["result"].get("value") == task["answer"] for c in calls)
    return {"success": bool(complete and same and behavior), "trace": trace,
            "tool_calls": calls, "final": message.get("content")}
```

**Parameter group: tool selection and client budgets.** `tool_choice="auto"` lets the model decide whether to call a tool based on the input. `max_rounds` and `max_tool_calls` are local loop limits for model-request rounds and actual tool executions, respectively. They are not sent as model parameters. Adjust them independently to meet your project's latency and cost requirements.

```python
TOOL_OPTIONS = {"tool_choice": "auto", "max_rounds": 5, "max_tool_calls": 8}

def run_loop(task, call_api, model="step-5-preview", max_rounds=5,
             tool_choice="auto", max_tool_calls=8):
    messages = [
        {"role": "system", "content": "Use the calculate tool for arithmetic. Claim a tool execution only when it actually occurred, and report tool failures accurately. Return only a JSON object with answer and explanation fields. Set answer to a number, a greeting string, or null if the task cannot be completed."},
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
            raise RuntimeError("The tool-calling response did not complete normally.")
        if len(requested) > 4 or len(calls) + len(requested) > max_tool_calls:
            raise RuntimeError("The tool-call limit was exceeded.")
        assistant = {k: message[k] for k in ("role", "content", "tool_calls", "reasoning_content") if k in message}
        assistant["role"] = "assistant"
        messages.append(assistant)
        for item in requested:
            if not item.get("id") or not isinstance(item.get("function"), dict):
                raise ValueError("A tool call is missing its ID or function details.")
            function = item["function"]
            result = execute(function.get("name"), function.get("arguments"))
            calls.append({"id": item["id"], "name": function.get("name"),
                          "arguments": function.get("arguments"), "result": result})
            messages.append({"role": "tool", "tool_call_id": item["id"],
                             "content": json.dumps(result, ensure_ascii=False)})
    raise RuntimeError("The maximum number of model-request rounds was reached.")
```

After the model selects a tool, the program appends the original assistant message, then the result with its matching `tool_call_id`. This order allows the next request to associate the result with the correct call. Network errors propagate to the calling entry point, where your application decides how to handle them.

### 3.4 Run a two-step calculation

Ask the model to add 18 and 6, then divide by 4. The final result should be 6. The tool execution records expose the intermediate and final values computed by the program.

```python
MODEL = "step-5-preview"
task = {"text": "Use the tool to calculate (18 + 6) / 4.", "answer": 6, "needs_tool": True}
call_api = lambda payload: chat(payload, api_key, REGION)
result = run_loop(task, call_api, model=MODEL, **TOOL_OPTIONS)
print(json.dumps(result, ensure_ascii=False, indent=2))
```

## 4. Understand the calling strategy and loop state

| Component | Purpose | Integration requirement |
| --- | --- | --- |
| `tool_choice="auto"` | Let the model decide whether the task needs a tool | Clearly describe when the tool applies |
| `messages.append(assistant)` | Preserve the assistant message requesting the tool call | Keep the following result messages attached to it in the conversation |
| `tool_call_id` | Associate one result with one call | Return a corresponding result for every call |
| `reasoning_content` | Pass it into the next request as required by the protocol when returned by the server | Do not present it as the final answer |
| `max_rounds`, `max_tool_calls` | Give the loop explicit stopping conditions | Set limits that match your project budget |

Send a simple greeting to observe the `auto` strategy. When a task needs no calculation, the model can return a final answer directly.

```python
greeting_task = {"text": "Say hello without calling the calculation tool.", "answer": "Hello", "needs_tool": False}
greeting = run_loop(greeting_task, call_api, model=MODEL, **TOOL_OPTIONS)
print(json.dumps(greeting, ensure_ascii=False, indent=2))
```

The greeting result should have an empty `tool_calls` list and an `answer` starting with "Hello", ignoring case. The check verifies both the greeting and the absence of tool calls.

## 5. Inspect actual execution records

For the calculation task, check three things together: the final value is 6, the tool was actually executed, and the execution results support that value. The following code extracts those details and saves the full trace so you can track calls in your own project.

```python
print("Final answer:", result.get("final"))
print("Executed tool calls:", len(result["tool_calls"]))
for item in result["tool_calls"]:
    print(item["name"], item["arguments"], "→", item["result"])
print("Task requirements met:", result["success"])
output_dir = Path("tool_results")
output_dir.mkdir(exist_ok=True)
save_json(output_dir / "calculation.json", result)
save_json(output_dir / "greeting.json", greeting)
```

Each elapsed time in `trace` measures the full model response. Tool execution here is local arithmetic. For a remote query, you can measure tool latency separately inside `execute()`. Final-answer format, actual execution, and loop-round count answer different questions and should be inspected separately.

## 6. Replace the input and integrate your own tool

First change the input to (20 + 8) / 4, update the reference answer to 7, and run the existing loop.

```python
my_task = {"text": "Use the tool to calculate (20 + 8) / 4.", "answer": 7, "needs_tool": True}
my_result = run_loop(my_task, call_api, model=MODEL, **TOOL_OPTIONS)
print(json.dumps(my_result, ensure_ascii=False, indent=2))
save_json(output_dir / "my_task.json", my_result)
```

To integrate your own tool, update the name and schema in `TOOL`, the dispatch and implementation in `execute()`, and the business rules used to check the final result. Retain result messages, call identifiers, and round limits. The model selects calls, your service executes them, and the application continues using actual tool results.

API reference: [StepFun tool calling](https://platform.stepfun.ai/docs/en/api-reference/tool-call).

## 7. Companion code and starter project

This example includes a Jupyter Notebook, an editable Python script, and a starter project for running and adapting the code. Browse the [example directory](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-tool-calling) for all files, or see the [setup and launch guide](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/README.md) for instructions.

| Resource | How to use it |
| --- | --- |
| [Jupyter Notebook](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/03_Step5_%E5%B7%A5%E5%85%B7%E8%B0%83%E7%94%A8.ipynb) | Work through the example cell by cell and inspect the inputs and results at each step. |
| [Python example script](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/tool_demo.py) | Run the minimal example or full experiment from a terminal, or adapt the code for your application. |
| [macOS launcher](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/%E5%90%AF%E5%8A%A8.command) · [Windows launcher](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/%E5%90%AF%E5%8A%A8.bat) · [launcher menu](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/launcher.py) | Prepare the runtime, then choose the minimal example or full experiment and the API region. |
| [Environment configuration](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-tool-calling/setup) · [locked dependencies](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/setup/requirements.lock) | Inspect the setup scripts, dependency versions, and environment checks. |

To use the launchers, obtain the complete example directory from the current repository and keep its relative paths intact. Initial setup requires an internet connection. The supplied Notebook, Python script, launch menu, and setup guide currently follow the Chinese version. To reproduce this guide's English prompts, sample inputs, and result fields, use the Python code blocks in this guide.

Last updated: 2026-09-29.
