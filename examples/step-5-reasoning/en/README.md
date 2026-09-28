# Step 5 Preview: Tune reasoning effort to compare quality, latency, and usage

[简体中文](../zh-CN/README.md) | **English**

## 1. Understand the model and reasoning effort

Step 5 Preview is a multimodal model that accepts text, image, and video inputs and generates text. Applications provide messages, source material, and tools through the API for the model to interpret, reason over, and answer. [Model overview](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview)

Reasoning effort is the level of reasoning computation you select for a task. Configure it with `reasoning_effort` in the Chat Completions API. It is separate from controls for response length and writing style. Choose a level by considering answer quality, waiting time, and token usage together. [Reasoning parameters](https://platform.stepfun.com/docs/zh/guides/developer/reasoning)

This guide is for developers familiar with Python functions and JSON. You will start with one text request, then compare `low`, `medium`, and `high` while keeping the input and output requirements fixed. You can reuse the request function and comparison method with your own task set.

**Workflow:** Configure the client → Run a baseline request → Adjust reasoning effort → Read timing and usage → Replace the task.

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

If the variable is unset, the script prompts for the key with input hidden.

Set `REGION = "cn"` for the China region, which uses `.com` endpoints, or `"global"` for the international region, which uses `.ai` endpoints. Use a key issued for the selected region.

Create `reasoning_demo.py` in your project and **copy this guide's Python code blocks into that file in order**. Run the `bash` and `powershell` blocks only in a terminal. After adding the definitions and calls, run:

```bash
python reasoning_demo.py
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

## 3. Make a minimal request

### 3.1 Prepare inputs and reference answers

The three inputs cover filtered summation, ordering under constraints, and set counting. The reference `answer` is used only for local checks and is not sent to the model. Each final response must be a JSON object containing only the `answer` field, so the program can read it consistently.

```python
MODEL = "step-5-preview"
MAX_TOKENS = 4096
SAMPLES = [
    {"id": "sum_even", "prompt": "Add the even numbers in this list: 18, 7, 26, 13, 12. Return only a JSON object with an integer answer field.", "answer": 56},
    {"id": "order", "prompt": "Arrange A, B, C, and D from left to right, using each letter once. D must precede A, A must precede B, and B must precede C. Return only a JSON object whose answer field is the four-letter sequence without spaces.", "answer": "DABC"},
    {"id": "count", "prompt": "How many integers from 1 through 30 inclusive are divisible by either 3 or 5, but not both? Return only a JSON object with an integer answer field.", "answer": 12},
]
```

### 3.2 Configure request parameters and result handling

First define the parameters sent to the model, then implement local result handling. Keep them separate so either part can be replaced independently in your project.

**Parameter group: reasoning effort and output budget.** `effort` supplies `reasoning_effort`, and `max_tokens` sets the output limit. `response_format` is fixed to a JSON object, and the prompt specifies an `answer` field to support the comparison.

```python
def request_for(sample, effort, model, max_tokens):
    return {"model": model, "messages": [
        {"role": "system", "content": "Complete the task and return only the requested JSON object as your final answer."},
        {"role": "user", "content": sample["prompt"]}],
        "reasoning_effort": effort, "response_format": {"type": "json_object"},
        "max_tokens": max_tokens, "stream": False}
```

Keep `max_tokens` fixed when comparing effort levels. To study the output budget, run a separate comparison that changes only that limit. Use the response's `finish_reason` to determine whether generation completed normally.

**Result handling.** The following code checks the answer and records usage without adding model parameters. The reference value for `answer` stays local.

```python
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
```



```python
baseline = run_case(SAMPLES[0], "low")
print(json.dumps(baseline, ensure_ascii=False, indent=2))
```

Inspect `content`, `success`, `elapsed_seconds`, and `usage` in the output. The reference result for this summation task is `{"answer": 56}`. A true `success` value means the final response completed normally and meets the specified field and answer requirements. The elapsed time runs from sending the HTTP request through reading the full response.

## 4. Compare three reasoning effort levels

`reasoning_effort` accepts `low`, `medium`, and `high`; see the [Step 5 Preview model documentation](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview). This comparison holds the model, inputs, prompt requirements, output format, and output limit constant and changes only reasoning effort.

With `REPEATS = 1`, the following code sends nine additional requests. This is enough to learn the workflow. To observe variability, increase the number of repetitions on your own task set. A fixed random seed shuffles the request order so that requests for one level are not all concentrated at the end of the experiment.

```python
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
```

## 5. Interpret the results and choose a configuration

Start with the number of completed runs at each level, then consider answer quality, elapsed time, and usage together. These measurements describe performance on this input set only. For a project decision, use a representative task set and retain the underlying counts. If `total_tokens` is absent, record it as missing rather than zero.

```python
summary = []
for effort in EFFORTS:
    group = [row for row in records if row["effort"] == effort]
    timings = [row["elapsed_seconds"] for row in group]
    tokens = [(row.get("usage") or {}).get("total_tokens") for row in group]
    summary.append({
        "reasoning_effort": effort, "completed_runs": len(group),
        "successful_runs": sum(row["success"] for row in group),
        "median_full_response_seconds": statistics.median(timings) if timings else None,
        "reported_total_tokens": sum(n for n in tokens if n is not None),
        "runs_with_missing_usage": sum(n is None for n in tokens),
    })
print(json.dumps(summary, ensure_ascii=False, indent=2))
save_json(output_dir / "summary.json", summary)
```

First identify the levels that meet your quality requirements, then compare their latency and usage. Increasing reasoning effort does not guarantee greater accuracy or lower latency for every input. This guide fixes `max_tokens` at 4096. Test changes to that value separately and check `finish_reason` for normal completion.

Full-response time includes network and server processing time. This example does not measure time to first token. Estimate cost separately using the [official pricing](https://platform.stepfun.ai/docs/en/guides/pricing/details) applicable on the request date, and retain usage fields for traceability.

## 6. Use your own tasks

Start with a small change: replace 12 with 14 in the first question, which changes the reference answer to 58. The following code runs that new input with the same request and checking methods.

```python
my_sample = {
    "id": "sum_even_changed",
    "prompt": "Add the even numbers in this list: 18, 7, 26, 13, 14. Return only a JSON object with an integer answer field.",
    "answer": 58,
}
my_result = run_case(my_sample, "high")
print(json.dumps(my_result, ensure_ascii=False, indent=2))
save_json(output_dir / "my_task.json", my_result)
```

To use project-specific tasks, update the inputs and reference answers in `SAMPLES`. If the target output is no longer a single-field JSON object, update both the prompt requirements and `grade()`. Run one input first, then compare effort levels, and choose a configuration against your quality and response-time requirements. The reusable outputs are the request, recording, and comparison methods, along with the result files produced by your run.

Last updated: 2026-09-28.
