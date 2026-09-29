# Step 5 Preview 推理强度调参：比较结果质量、耗时与用量

**简体中文** | [English](../en/README.md)

> 中英文版本介绍相同的模型能力和主要流程；示例输入、提示词、输出字段和校验细节可能不同，请以所读版本的代码为准。配套 Python 脚本与 Notebook 对应中文版。

## 1. 认识模型与推理强度

Step 5 Preview 是支持文本、图片和视频输入、生成文本结果的多模态模型。应用通过 API 提供消息、材料和工具，它据此完成理解、推理与回答。[模型概览](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview)

推理强度是开发者为任务选择的推理投入档位。在 Chat Completions 接口中使用 `reasoning_effort` 配置；它与回答长短、语言风格属于不同的控制项。实际开发需要结合答案质量、等待时间和 token 用量选择档位。[推理参数说明](https://platform.stepfun.com/docs/zh/guides/developer/reasoning)

本篇面向会使用 Python 函数与 JSON 的开发者。我们从一次文本请求开始，随后固定输入与输出要求，对比 `low`、`medium`、`high`。你可以把请求函数与比较方法直接接到自己的任务集。

**本文路线：** 配置客户端 → 运行单条基线 → 调整推理档位 → 读取耗时与用量 → 替换任务。

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

在项目中新建 `reasoning_demo.py`，将本文的 **Python 代码块按顺序放进这个文件**；`bash` 和 `powershell` 代码块只在终端执行。完成定义与调用后运行：

```bash
python reasoning_demo.py
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

## 3. 先完成一个最小请求

### 3.1 准备输入与明确答案

三个输入分别覆盖筛选求和、条件排序、集合计数。`answer` 只用于本地核对，不会发给模型。最终回答统一为只有 `answer` 字段的 JSON 对象，便于程序读取。

```python
MODEL = "step-5-preview"
MAX_TOKENS = 4096
SAMPLES = [
    {"id": "sum_even", "prompt": "把 18、7、26、13、12 中的偶数相加。只返回 JSON，字段 answer 为整数。", "answer": 56},
    {"id": "order", "prompt": "A、B、C、D 各出现一次。D 在 A 前，A 在 B 前，B 在 C 前。按从左到右的顺序排列。只返回 JSON，字段 answer 为四个字母组成的字符串，不含空格。", "answer": "DABC"},
    {"id": "count", "prompt": "在 1 到 30（包含两端）的整数中，能被 3 或 5 整除、但不能同时被二者整除的数共有几个？只返回 JSON，字段 answer 为整数。", "answer": 12},
]
```

### 3.2 设置请求参数与结果处理

先设置发送给模型的参数，再编写本地结果处理。两部分独立保留，便于在项目中单独替换。

**参数组：推理档位与输出预算。** `effort` 传入 `reasoning_effort`；`max_tokens` 给输出设置上限。`response_format` 固定为 JSON 对象，提示要求同时约定 `answer` 字段，便于后续对照。

```python
def request_for(sample, effort, model, max_tokens):
    return {"model": model, "messages": [
        {"role": "system", "content": "完成给定任务，最终回答只输出要求的 JSON 对象。"},
        {"role": "user", "content": sample["prompt"]}],
        "reasoning_effort": effort, "response_format": {"type": "json_object"},
        "max_tokens": max_tokens, "stream": False}
```

`low`、`medium`、`high` 是离散档位，不是具体思考秒数。比较档位时固定 `max_tokens`；若要研究输出预算，另开一组只修改该上限。响应中的 `finish_reason` 用于确认是否完整结束。

**结果处理。** 下面只负责核对结果与记录用量，不再增加新的模型参数。`answer` 的参考值保留在本地。

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

关注输出中的 `content`、`success`、`elapsed_seconds` 和 `usage`。这道求和题的参考结果是 `{"answer": 56}`；`success` 为真表示本次最终回答完整，且满足既定字段和答案要求。这里的耗时从发出 HTTP 请求计到完整响应读取结束。

## 4. 只调整推理强度，比较三组结果

`reasoning_effort` 使用 `low`、`medium`、`high` 三档；接口依据见 [Step 5 Preview 模型说明](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview)。以下对照固定模型、输入、提示要求、输出格式和输出上限，仅改变推理强度。

`REPEATS = 1` 会再发送九次请求。适合先了解流程；需要观察波动时，在自己的任务集上增加重复次数。固定随机种子打乱顺序，避免某一档请求全部集中在实验末尾。

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

## 5. 读懂结果，选择适合任务的配置

先看每档完成了多少次，再同时看结果质量、耗时与用量。三个问题只能说明本组输入的表现；正式选参时应换成有代表性的任务集，并保留原始次数。`total_tokens` 缺失时记为缺失，不能按零用量处理。

```python
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
```

先找达到自己质量要求的档位，再在这些档位中比较耗时与用量。提高推理强度不构成每个输入都更准确或更快的承诺。`max_tokens` 在本篇固定为 4096；调整它时应另开一组比较，并关注 `finish_reason` 是否完整结束。

完整响应耗时包含网络和服务端处理时间；这里没有测量首 token 延迟。费用可依据请求当日的[官方计价规则](https://platform.stepfun.ai/docs/en/guides/pricing/details)另行估算，保留用量字段便于回溯。

## 6. 换成自己的任务

先做一次小改造：把第一题中的 12 改为 14，参考答案随之变为 58。下面完整执行这条新输入，继续沿用相同的请求和核对方法。

```python
my_sample = {
    "id": "sum_even_changed",
    "prompt": "把 18、7、26、13、14 中的偶数相加。只返回 JSON，字段 answer 为整数。",
    "answer": 58,
}
my_result = run_case(my_sample, "high")
print(json.dumps(my_result, ensure_ascii=False, indent=2))
save_json(output_dir / "my_task.json", my_result)
```

替换为项目任务时，更新 `SAMPLES` 的输入与参考答案；如果目标产物不再是单字段 JSON，应同时修改提示要求与 `grade()`。先跑单条，再跑多档对照，最后按自己的质量和响应时间要求选择配置。你带走的是请求、记录和比较方法，以及本次运行生成的结果文件。

## 7. 配套代码与运行脚手架

本案例提供 Notebook、可编辑 Python 脚本及运行脚手架，便于逐步学习、运行示例和接入自己的项目。完整文件见[案例目录](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-reasoning)，环境准备和启动步骤见[运行指南](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/README.md)。

| 配套资源 | 用途 |
| --- | --- |
| [Jupyter Notebook](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/01_Step5_%E6%8E%A8%E7%90%86%E5%BC%BA%E5%BA%A6%E8%B0%83%E5%8F%82.ipynb) | 按单元格阅读和执行案例，观察每一步的输入与结果。 |
| [Python 示例脚本](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/reasoning_demo.py) | 在终端运行最小示例或完整实验，也可修改后复用到自己的项目。 |
| [macOS 启动入口](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/%E5%90%AF%E5%8A%A8.command) · [Windows 启动入口](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/%E5%90%AF%E5%8A%A8.bat) · [启动菜单](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/launcher.py) | 准备案例运行环境，并选择最小示例、完整实验及 API 区域。 |
| [环境配置目录](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-reasoning/setup) · [锁定依赖](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/setup/requirements.lock) | 包含环境准备脚本、依赖版本和环境检查程序。 |

使用启动脚手架时，请从当前仓库获取完整案例目录，并保留启动文件、`setup/` 和素材之间的相对路径；首次准备环境需要联网。配套 Notebook、Python 脚本和启动菜单对应中文版，英文版的提示词、示例输入和部分结果字段可能不同。

更新日期：2026-09-29。正文代码面向普通 Python 项目；配套 Notebook 为同内容的可选形式。模型标识与接口字段保留英文。
