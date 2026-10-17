# Step 5 tool calling: let the customer approve before an order changes

Step 5 Preview takes messages and function definitions and returns text or
structured tool-call proposals. Your application executes the functions. That
is where customer approval belongs.

This recipe puts the decision on the customer's phone. Step 5 proposes an order
change, Pushary asks the customer, and your backend changes the order only after
approval. If the worker restarts, it resumes the saved request.

You will build this with Python, two synthetic orders and the existing Pushary
SDK. The demo writes to a local SQLite table. It does not take a payment or send
a shipment. Start with the offline demo below; it needs no accounts or keys.

## Prepare your environment

Use Python 3.9 or newer. The only dependency is the published, pinned
`pushary==2.4.0` SDK; HTTP, JSON and SQLite use the Python standard library.
StepFun and Pushary are independent services. Live execution needs StepFun API
access and a Pushary Partner workspace with a connected test customer's phone.

From `examples/step-5-customer-approval` (the parent of this article's `en` directory), on macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python check_run.py --demo
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python check_run.py --demo
```

The offline demo needs no accounts or credentials. It explicitly simulates the
StepFun response and phone answer while running the published SDK and separate
SQLite-backed worker processes. It prints zero order changes before approval,
two changes afterward, and still two after replay. This is reproducible local
evidence, not a live phone or model-provider test.

For live execution, obtain a key from the [StepFun platform](https://platform.stepfun.ai/)
and your [Pushary Partner workspace](https://pushary.com/sign-up?plan=partner&utm_source=github&utm_medium=oss-adapter&utm_campaign=pushary-stepfun&utm_content=readme).
Your backend must already have [enrolled the test customer](https://github.com/Pushary/pushary-python#quick-start-two-calls).
Use the customer's application ID, not an email invented by the model.

Inject `STEP_API_KEY` and `PUSHARY_API_KEY` as environment variables from your
secret manager. For local macOS/Linux use hidden terminal input:

```bash
read -r -s STEP_API_KEY
export STEP_API_KEY
read -r -s PUSHARY_API_KEY
export PUSHARY_API_KEY
export STEPFUN_REGION=global
```

For PowerShell, use hidden input:

```powershell
$env:STEP_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'StepFun API key' -AsSecureString)).Password
$env:PUSHARY_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Pushary API key' -AsSecureString)).Password
$env:STEPFUN_REGION = 'global'
```

The global API is `https://api.stepfun.ai/v1`; `STEPFUN_REGION=cn` selects
`https://api.stepfun.com/v1`. Use a key provisioned for your selected region.
The example requests `step-5-preview`, low reasoning effort, a 4,096-token output
limit, a 90-second HTTP socket timeout and at most two proposed order calls.
It makes one proposal request and one final-summary request on the successful
path. It does not automatically retry HTTP requests.

## Build the smallest complete flow

Save the following four Python blocks, in order, as `run.py`. The adjacent
`run.py` contains exactly these blocks and is ready to run. Each block owns a
single part of the application boundary.

### Define the model request and validate proposals

```python
"""Step 5 tool proposals, customer approval and a persisted local order effect."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from pushary.adapters import AdapterKernel, decision_fingerprint

REVISION = "stepfun-order-v1"
MODEL = "step-5-preview"
APPROVAL_SECONDS = 3600
MAX_RESPONSE_BYTES = 1_000_000
ORDERS = {"order-1": 1900, "order-2": 1900}
BASE_URLS = {"global": "https://api.stepfun.ai/v1", "cn": "https://api.stepfun.com/v1"}
TOOL = {"type": "function", "function": {
    "name": "release_order",
    "description": "Propose releasing a local demo order. The application requires customer approval.",
    "parameters": {"type": "object", "properties": {
        "order_id": {"type": "string", "enum": list(ORDERS)},
        "amount_cents": {"type": "integer", "enum": [1900]}},
        "required": ["order_id", "amount_cents"], "additionalProperties": False}}}
INITIAL_MESSAGES = [
    {"role": "system", "content": "Propose release_order for each requested order. The application obtains customer approval. Never claim an order changed without a successful tool result."},
    {"role": "user", "content": "Release order-1 and order-2, each for 1900 cents. These are local demonstration orders."},
]


def json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Expected a JSON object")
    return dict(value)


def bounded_text(value: object, maximum: int = 100) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Expected bounded text")
    return value


def identity(value: object) -> str:
    text = bounded_text(value)
    if not re.fullmatch(r"[A-Za-z0-9_.:@-]+", text):
        raise ValueError("Use identities from authenticated application state")
    return text


@dataclass(frozen=True)
class OrderCall:
    call_id: str
    order_id: str
    amount_cents: int

    def result(self) -> dict[str, object]:
        return {"order_id": self.order_id, "amount_cents": self.amount_cents, "status": "released"}


@dataclass(frozen=True)
class Proposal:
    assistant: dict[str, object]
    calls: tuple[OrderCall, ...]


def parse_order_call(value: object) -> OrderCall:
    call = json_object(value)
    function = json_object(call.get("function"))
    if call.get("type") != "function" or function.get("name") != "release_order":
        raise ValueError("Unsupported tool")
    arguments = json_object(json.loads(bounded_text(function.get("arguments"), 1000)))
    if set(arguments) != {"order_id", "amount_cents"}:
        raise ValueError("Unexpected tool arguments")
    order_id = bounded_text(arguments["order_id"])
    amount = arguments["amount_cents"]
    if type(amount) is not int or order_id not in ORDERS or amount != ORDERS[order_id]:
        raise ValueError("Order proposal differs from the application catalog")
    return OrderCall(identity(call.get("id")), order_id, amount)


def response_choice(value: object) -> dict[str, object]:
    response = json_object(value)
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Expected one complete model choice")
    return json_object(choices[0])


def parse_proposal(value: object) -> Proposal:
    choice = response_choice(value)
    message = json_object(choice.get("message"))
    if choice.get("finish_reason") not in ("tool_calls", "stop") or message.get("role") != "assistant" or message.get("refusal"):
        raise ValueError("Model did not return a complete proposal")
    requested = message.get("tool_calls")
    if not isinstance(requested, list) or not 1 <= len(requested) <= len(ORDERS):
        raise ValueError("Expected one or two order proposals")
    calls = tuple(parse_order_call(call) for call in requested)
    if len({call.call_id for call in calls}) != len(calls) or len({call.order_id for call in calls}) != len(calls):
        raise ValueError("Repeated tool call or order")
    assistant = {key: message[key] for key in ("role", "content", "tool_calls", "reasoning_content") if key in message}
    for field in ("content", "reasoning_content"):
        text = assistant.get(field)
        if text is not None and (not isinstance(text, str) or len(text) > MAX_RESPONSE_BYTES):
            raise ValueError("Invalid assistant text")
    return Proposal(assistant, calls)


def parse_final(value: object) -> str:
    choice = response_choice(value)
    message = json_object(choice.get("message"))
    if choice.get("finish_reason") != "stop" or message.get("role") != "assistant" or message.get("tool_calls") or message.get("refusal"):
        raise ValueError("Final answer incomplete or requested another action")
    return bounded_text(message.get("content"), MAX_RESPONSE_BYTES)


def step_chat(payload: dict[str, object]) -> object:
    region = os.environ.get("STEPFUN_REGION", "global")
    if region not in BASE_URLS:
        raise ValueError("STEPFUN_REGION must be global or cn")
    key = bounded_text(os.environ.get("STEP_API_KEY"), 1000)
    request = urllib.request.Request(BASE_URLS[region] + "/chat/completions",
        data=json.dumps(payload, allow_nan=False).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Model response exceeded the byte limit")
    return json.loads(body)


def model_request(messages: list[dict[str, object]], tool_choice: str) -> dict[str, object]:
    return {"model": MODEL, "messages": messages, "tools": [TOOL], "tool_choice": tool_choice,
            "reasoning_effort": "low", "max_tokens": 4096, "stream": False}
```

The parser accepts only the known function, catalog order IDs, integer amounts, unique call IDs and a completed response. Unknown arguments, including a model-selected recipient, stop before any approval request. The original assistant message retains `reasoning_content` and each raw tool argument string.

### Save the proposal before asking for approval

```python
@dataclass(frozen=True)
class Operation:
    tenant: str
    customer: str
    run_id: str
    expires_at: int
    proposal: Proposal

    def payload(self) -> dict[str, object]:
        return {"revision": REVISION, "tenant": self.tenant, "customer": self.customer,
                "run_id": self.run_id, "expires_at": self.expires_at, "assistant": self.proposal.assistant}


def load_operation(db: sqlite3.Connection, tenant: str, customer: str) -> Operation:
    row = db.execute("select payload,digest from operation where id=1").fetchone()
    if row is None:
        raise ValueError("No saved proposal; reconcile this run")
    payload = json_object(json.loads(bounded_text(row[0], MAX_RESPONSE_BYTES)))
    if decision_fingerprint(payload) != row[1] or set(payload) != {"revision", "tenant", "customer", "run_id", "expires_at", "assistant"}:
        raise ValueError("Saved operation changed")
    if payload["revision"] != REVISION or payload["tenant"] != tenant or payload["customer"] != customer:
        raise ValueError("Operation does not belong to this caller or code revision")
    deadline = payload["expires_at"]
    if type(deadline) is not int or deadline <= 0:
        raise ValueError("Invalid approval deadline")
    proposal = parse_proposal({"choices": [{"finish_reason": "tool_calls", "message": payload["assistant"]}]})
    return Operation(tenant, customer, identity(payload["run_id"]), deadline, proposal)


def start_operation(folder: Path, tenant: str, customer: str) -> None:
    folder.mkdir(mode=0o700)
    with sqlite3.connect(folder / "orders.db") as db:
        db.executescript("create table operation(id integer primary key check(id=1), payload text not null, digest text not null, final text);"
                         "create table released(call_id text primary key, order_id text unique not null, result text not null);")
        proposal = parse_proposal(step_chat(model_request(INITIAL_MESSAGES, "auto")))
        operation = Operation(tenant, customer, uuid.uuid4().hex, int(time.time()) + APPROVAL_SECONDS, proposal)
        payload = operation.payload()
        db.execute("insert into operation(id,payload,digest) values (1,?,?)", (json.dumps(payload), decision_fingerprint(payload)))
```

The operation binds the trusted tenant, customer, run ID, deadline and assistant proposal. Saving occurs before contacting Pushary. A hash catches accidental storage changes; it is not a signature against someone who controls the database. Resume also checks the caller and code revision.

### Consume a one-use permit before changing the order

```python
def release_approved_order(db: sqlite3.Connection, operation: Operation, call: OrderCall) -> dict[str, object]:
    if time.time() >= operation.expires_at:
        raise TimeoutError("Approval expired before execution")
    result = call.result()
    db.execute("insert into released values (?,?,?)", (call.call_id, call.order_id, json.dumps(result)))
    db.commit()
    return result


def read_releases(db: sqlite3.Connection, operation: Operation) -> dict[str, dict[str, object]]:
    released = {}
    for call in operation.proposal.calls:
        row = db.execute("select order_id,result from released where call_id=?", (call.call_id,)).fetchone()
        if row is not None:
            result = json_object(json.loads(row[1]))
            if row[0] != call.order_id or result != call.result():
                raise ValueError("Saved effect differs from the approved proposal")
            released[call.call_id] = result
    return released


def approve_order(db: sqlite3.Connection, operation: Operation, call: OrderCall) -> str | None:
    if time.time() >= operation.expires_at:
        return "Approval expired"
    protect = AdapterKernel("StepFun order cookbook").create_protect(
        policy=False, timeout_seconds=0, expires_in_seconds=APPROVAL_SECONDS, require_reachable=True)

    def execute() -> dict[str, object]:
        return release_approved_order(db, operation, call)

    result = protect("order.release", execute, external_id=operation.customer,
        run_id=operation.run_id, call_id=call.call_id, target=call.order_id, actor=operation.tenant,
        question=f"Release demo {call.order_id} for {call.amount_cents} cents?",
        facts={"order_id": call.order_id, "amount_cents": call.amount_cents,
               "pushary_binding": decision_fingerprint(operation.payload())})
    return None if result.ok else bounded_text(result.reason, 2000)
```

The SDK asks a confirm question and consumes an execution permit before calling the effect. Missing, refused, expired or unconfirmed permission leaves the order unchanged. The effect commits its result before the SDK reports the receipt, so a crash during receipt delivery does not repeat the order change.

### Return the matching tool results and resume safely

```python
def finish_operation(db: sqlite3.Connection, operation: Operation, released: dict[str, dict[str, object]]) -> dict[str, object]:
    db.execute("begin immediate")
    row = db.execute("select final from operation where id=1").fetchone()
    if row is None:
        raise ValueError("Saved operation missing")
    results = list(released.values())
    if row[0] is None:
        messages = [*INITIAL_MESSAGES, operation.proposal.assistant]
        for call in operation.proposal.calls:
            messages.append({"role": "tool", "tool_call_id": call.call_id, "content": json.dumps(released[call.call_id])})
        try:
            answer = parse_final(step_chat(model_request(messages, "none")))
        except Exception as error:
            db.rollback()
            return {"result": results, "summary_error": type(error).__name__}
        db.execute("update operation set final=? where id=1", (answer,))
    else:
        answer = bounded_text(row[0], MAX_RESPONSE_BYTES)
    db.commit()
    return {"result": results, "assistant": answer}


def run_demo(mode: str, folder: Path, tenant: str, customer: str) -> dict[str, object]:
    tenant, customer = identity(tenant), identity(customer)
    if mode == "start":
        start_operation(folder, tenant, customer)
    elif mode != "resume":
        raise ValueError("Use start or resume")
    if not (folder / "orders.db").is_file():
        raise ValueError("Saved run not found")
    with sqlite3.connect(folder / "orders.db", timeout=120) as db:
        operation = load_operation(db, tenant, customer)
        released = read_releases(db, operation)
        blocked = {}
        for call in operation.proposal.calls:
            if call.call_id not in released:
                reason = approve_order(db, operation, call)
                if reason is not None:
                    blocked[call.call_id] = reason
        released = read_releases(db, operation)
        blocked = {call_id: reason for call_id, reason in blocked.items() if call_id not in released}
        if blocked:
            return {"result": list(released.values()), "blocked": blocked}
        return finish_operation(db, operation, released)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("Usage: python run.py start|resume STATE_DIRECTORY TENANT TEST_CUSTOMER_ID")
    try:
        print(json.dumps(run_demo(sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4])))
    except Exception:
        raise SystemExit("Stopped. Some orders may already have changed. Inspect the saved operation and execution permits before retrying.")
```

Each tool result uses its original `tool_call_id`. The final request disables tools, and the response parser rejects further tool calls. A model summary is presentation; the `released` table is the evidence of what happened.

## Run and read the result

Run from this directory with a new state directory. `demo-store` and
`TEST_CUSTOMER_ID` stand for identities from your authenticated backend; the
CLI demonstrates that boundary but does not authenticate a caller itself.

```bash
.venv/bin/python run.py start ./order-run-1 demo-store TEST_CUSTOMER_ID
```

Every normal response contains `result`, the list of orders already changed.
The first response normally has an empty list and `blocked` keyed by tool-call ID. Check the
customer's phone and approve or refuse each proposed order. Then launch a new
worker with the same directory and trusted identities:

```bash
.venv/bin/python run.py resume ./order-run-1 demo-store TEST_CUSTOMER_ID
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python`.

A successful response has a `result` list with the released order IDs, amounts
and statuses, plus the model's `assistant` text. The model may propose one or
two orders; read the actual result list instead of assuming both executed.
Repeating `resume` returns the saved result without another order change or
another successful model request. Pending and refused approvals remain blocked. `resume` checks the same saved
decision; it never starts a fresh action merely because the SDK says the prior
attempt was blocked.
Each order is independent: approving one can release it while the other remains
pending. The response shows that completed order in `result` and the remaining
call in `blocked`.

If the final model request fails or tries to request another action, `result`
still shows the completed orders and `summary_error` gives the error class.
`resume` can retry that summary without repeating the order changes. Error
messages and HTTP response bodies are never included in this field.

Inspect the persisted business evidence with SQLite:

```sql
SELECT call_id, order_id, result FROM released;
```

Run the failure checks independently of live credentials:

```bash
.venv/bin/python check_run.py -v
```

These checks exercise the published SDK with simulated service responses, real
SQLite writes and separate Python workers. They cover partial approvals,
refusals, malformed model proposals, changed identities and state, concurrent
resume, lost permit responses, expiry after authorization, receipt-time crashes,
a crash between permit consumption and the order commit, and a final model
response that tries to request another action. HTTP checks send real requests
to a local fixture server to verify the endpoint, credentials header, request
body, response-size limit and handling of malformed or failed responses.

## Understand the choices and recovery limits

| Choice | Why it matters | What to inspect |
| --- | --- | --- |
| Application-owned customer and tenant | Model arguments cannot redirect the approval | The persisted operation and recipient on the phone |
| Original assistant message and call IDs | Resuming returns each result to the correct request | The tool results in the final StepFun request |
| One-hour application deadline | A delayed approval cannot execute indefinitely | `expires_at` in the stored operation |
| `policy=False` and confirm questions | This lesson always requires an explicit human answer | No effect while pending or refused |
| Shared SDK execution permit | An affirmative answer alone is insufficient for execution | Permit consumption and execution receipt |
| Persisted business result | A later worker recognizes an already-completed action | One `released` row per order |
| Final `tool_choice="none"` | The summary cannot silently initiate another operation | Additional tool calls are rejected |

Use protected persistent storage. The state directory is created with mode
0700 where supported. The SDK's remote permit serializes execution of each
approved action. SQLite records the effect and result together. The final
summary holds a write transaction to avoid concurrent duplicate model requests;
that tradeoff is limited to this run's private database. Use this example on one
host; it is not a distributed execution service.

A lost permit response or crash after permit consumption but before the local
commit leaves the operation uncertain and blocked. Reconcile the permit and
the business record; do not delete state, issue a fresh approval automatically,
or reset a consumed permit to force a retry. A crash after the local commit can
resume from the stored result, although the remote execution receipt may still
need reconciliation. A failed final model request can be retried with `resume`
after checking state; it does not repeat completed order effects.

If execution stops unexpectedly, the CLI tells you that some orders may already
have changed. Inspect saved state and service-side execution records before
retrying. It never prints credentials or service bodies. A trusted
administrator who can edit Python or SQLite is outside this approval boundary.
The recipe does not intercept arbitrary tools or claim protection for a whole
agent runtime.

## Adapt it to your application

For a one-order demo, change `ORDERS` to `{"order-1": 1900}` and change
`INITIAL_MESSAGES` to request only `order-1`. The allowed order IDs and call budget
follow the catalog. For different amounts, update the tool schema's
`amount_cents` enum as well as the trusted catalog, then bump `REVISION` before
starting fresh operations. Never migrate pending approvals across revisions.

For a real order service, load the order and recipient from authenticated
application state, replace the SQLite effect with your transactional order
operation, and make that operation idempotent by business order ID. Pass the
same saved call identity on resume. Keep authorization immediately before the
effect, and recheck the current order version there. A remote API call and local
SQLite commit are not one transaction; use your service's idempotency and
reconciliation facilities before making external changes.

The two orders and all offline responses are synthetic fixtures authored for
this recipe. No customer data or measured model-performance claim is included.

References, checked 2026-10-17:

- [StepFun tool-calling cookbook](https://platform.stepfun.ai/cookbook/step-5-tool-calling)
- [StepFun cookbook source and contribution guide](https://github.com/stepfun-ai/Step-Cookbook)
- [Pushary Python SDK](https://github.com/Pushary/pushary-python)

This independently maintained example is not an official StepFun integration.
