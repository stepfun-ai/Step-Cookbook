# Step 5 Preview: Turn image content into structured JSON

[简体中文](../zh-CN/README.md) | **English**

## 1. Image understanding and structured outputs

Step 5 Preview can read text and images in the same message and respond with text. “Multimodal” means that the model can combine different input types. This guide uses its image-understanding capability to read tables. [Model and input types](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview)

Applications often need to pass extracted information to other code. JSON Schema describes the target object using field names, types, and required fields; structured outputs use that schema to constrain the response shape. Whether the image was read correctly still requires a task-specific check. [Structured outputs](https://platform.stepfun.com/docs/zh/guides/developer/json-mode)

This guide is for developers integrating image extraction into Python projects. Three small tables illustrate how image encoding, `detail`, a field schema, and `null` for missing values work together. The result is parsed into a Python object.

**Workflow:** Prepare images → Define fields → Send an image-and-text request → Check the returned object → Replace the images and fields.

## 2. Prerequisites and setup

### 2.1 Prerequisites

**Required knowledge:** Familiarity with Python functions, dictionaries, and JSON.

- Python 3.10 or later.
- A StepFun API key with access to `step-5-preview`.
- Sample images: the three PNG files linked below, saved under `assets/vision/` in your project.

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

Create `vision_demo.py` in your project and **copy this guide's Python code blocks into that file in order**. Run the `bash` and `powershell` blocks only in a terminal. After adding the definitions and calls, run:

```bash
python vision_demo.py
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

import base64
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

This guide includes three PNG files. Copy the supplied `assets` directory into your project and run commands with the project directory as your working directory. If you download this article on its own, save the images below under `assets/vision/`. The images are sample data; all image-reading and request code is included below.

- [Complete table: clear.png](../assets/vision/clear.png)
- [Table with C left blank: missing.png](../assets/vision/missing.png)
- [Table with B changed to 9: adapted.png](../assets/vision/adapted.png)

![Complete table: A is 12, B is 7, and C is 5](../assets/vision/clear.png)

## 3. Extract a structured object from one image

### 3.1 Define fields and output constraints

All three fields are required, each value must be an integer or `null`, and additional fields are not allowed. `null` indicates that the image does not provide a readable numeric value. Reference answers are used to check the result and are not included in the request.

```python
MODEL = "step-5-preview"
ASSET_DIR = Path("assets/vision")
IMAGES = [
    {"file": "clear.png", "expected": {"A": 12, "B": 7, "C": 5}},
    {"file": "missing.png", "expected": {"A": 12, "B": 7, "C": None}},
    {"file": "adapted.png", "expected": {"A": 12, "B": 9, "C": 5}},
]
for item in IMAGES:
    if not (ASSET_DIR / item["file"]).is_file():
        raise FileNotFoundError(f"Save the supplied image {item['file']} in {ASSET_DIR}.")
```

**Parameter group: output fields in `response_format`.** When adapting the example to business fields, update the names, types, and missing-value convention here first.

```python
SCHEMA = {"type": "object", "properties": {k: {"type": ["integer", "null"]} for k in ["A", "B", "C"]},
          "required": ["A", "B", "C"], "additionalProperties": False}
```

`required` specifies mandatory fields, and `additionalProperties=False` prevents extra fields. Allowing `null` gives the program an explicit representation for values missing from the image.

**Parameter group: image `detail` and a strict schema.** This example starts with `high` to examine small text in a table. When changing `IMAGE_DETAIL`, compare results for the same image and schema. Keep `STRICT_SCHEMA` true so the API returns the specified field structure.

```python
IMAGE_DETAIL = "high"
STRICT_SCHEMA = True

def request_for(image_path, model):
    raw = image_path.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 10_000_000:
        raise ValueError("This example accepts only PNG files up to 10 MB.")
    return {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Read the values for A, B, and C from the table in the image. Use only the image as evidence. Return null for blank or unreadable values; do not guess."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw).decode(), "detail": IMAGE_DETAIL}}]}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "table_values", "strict": STRICT_SCHEMA, "schema": SCHEMA}},
        "reasoning_effort": "low", "max_tokens": 4096, "stream": False}
```

Image encoding, extraction instructions, and the schema are combined in one request. The result handler below checks JSON parsing, field types, and reference values separately. These checks cover both format and content.

```python
def grade(content, expected):
    try:
        obj = json.loads(content)
    except (ValueError, TypeError):
        return {"parse_ok": False, "schema_ok": False, "correct_fields": 0, "all_correct": False}
    valid = isinstance(obj, dict) and set(obj) == set(SCHEMA["required"]) and all(v is None or type(v) is int for v in obj.values())
    correct = sum(k in obj and type(obj[k]) is type(v) and obj[k] == v for k, v in expected.items()) if valid else 0
    return {"parse_ok": True, "schema_ok": valid, "correct_fields": correct,
            "evaluated_fields": len(expected), "all_correct": valid and correct == len(expected), "parsed": obj}
```

`request_for()` reads the image as bytes and encodes it as a Base64 data URL. Text instructions and the image appear in the same user message. `response_format` specifies a strict schema, and `detail` is set to `high`. The example imposes its own limit of PNG files smaller than 10 MB to keep inputs and outputs easy to inspect.

### 3.2 Send a request and inspect the fields

Define a reusable image-reading function, then process the first image.

```python
def read_image(item):
    data, elapsed = chat(request_for(ASSET_DIR / item["file"], MODEL), api_key, REGION)
    row = {"file": item["file"], "elapsed_seconds": elapsed, **response_record(data)}
    row["checks"] = grade(row["content"], item["expected"])
    row["success"] = (row["finish_reason"] == "stop" and not row["refusal"]
                      and row["checks"]["all_correct"])
    return row
```



```python
clear_result = read_image(IMAGES[0])
print(json.dumps(clear_result, ensure_ascii=False, indent=2))
```

The reference object for this image is `{"A": 12, "B": 7, "C": 5}`. Inspect the actual result in `content`, then `parse_ok`, `schema_ok`, and `correct_fields` under `checks`. These answer three separate questions: can the result be parsed, does it have the expected shape, and do the fields match the image?

## 4. Understand the key choices and handle a blank field

### 4.1 Represent missing values explicitly

The C cell is blank in the second image. Both the prompt and schema allow `null`, so downstream code can handle the missing value explicitly.

![Table with the C cell left blank](../assets/vision/missing.png)

```python
missing_result = read_image(IMAGES[1])
print(json.dumps(missing_result, ensure_ascii=False, indent=2))
```

The reference object for this image is `{"A": 12, "B": 7, "C": null}`. JSON `null` becomes `None` when parsed in Python.

### 4.2 Update three components when changing fields

| Component | Role in this example | When adapting the task |
| --- | --- | --- |
| Extraction instructions | Tell the model what to read from the image | Specify target fields, units, and the missing-value policy |
| `SCHEMA` | Define fields, types, and whether extra fields are allowed | Match the downstream data structure |
| `grade()` and reference answers | Check results against known facts | Define type and value rules for the new fields |

JSON Mode focuses on parseable JSON. This example uses JSON Schema to constrain fields and types further. Once the format meets those constraints, check the field meanings against the image content. For API details, see [structured outputs](https://platform.stepfun.ai/docs/en/guides/developer/json-mode).

## 5. Read the results

Combine the two requests to inspect the number of correct fields and whether each complete object meets the requirements. Two images are enough to illustrate the mechanism. To evaluate a real task, add representative images with different sizes, layouts, and levels of clarity.

```python
results = [clear_result, missing_result]
for row in results:
    check = row["checks"]
    print(row["file"], {
        "parse_ok": check["parse_ok"], "schema_ok": check["schema_ok"],
        "correct_fields": check["correct_fields"], "success": row["success"],
        "full_response_seconds": round(row["elapsed_seconds"], 2),
    })
output_dir = Path("vision_results")
output_dir.mkdir(exist_ok=True)
save_json(output_dir / "records.json", results)
```

## 6. Replace an image and use your own fields

The third image changes B from 7 to 9 while preserving the layout. Reuse the existing function; the result should reflect the changed image content.

```python
my_result = read_image(IMAGES[2])
print(json.dumps(my_result, ensure_ascii=False, indent=2))
save_json(output_dir / "my_image.json", my_result)
```

Place your images in `ASSET_DIR`, then add their filenames and known reference answers to `IMAGES`. If only the image changes, the calling code can stay the same. When adding fields, update the extraction instructions, schema, and checking function together. In an application, retain both structural checks and business-field checks before passing the Python object downstream.

Model and image-input reference: [Step 5 Preview](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview). The three sample images are demonstration assets generated for this project.

Last updated: 2026-09-28.
