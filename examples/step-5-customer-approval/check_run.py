"""Offline service fixtures around the published SDK and real persisted workers."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import run
from pushary.errors import PusharyError


def service_request(self: object, method: str, path: str, *, body: object = None, **kwargs: object) -> dict[str, object]:
    if not isinstance(body, dict):
        raise AssertionError("Expected request body")
    with sqlite3.connect(os.environ["CHECK_SERVICE"], timeout=20) as db:
        if path == "/decisions":
            key = body["idempotencyKey"]
            db.execute("insert or ignore into decisions values (?, ?, 'pending')", (key, json.dumps(body)))
            original, answer = db.execute("select body,answer from decisions where id=?", (key,)).fetchone()
            assert json.loads(original) == body
            return {"decisionId": key, "status": "answered" if answer in ("yes", "no") else answer,
                    "answered": answer in ("yes", "no"), "type": "confirm", "value": answer}
        if path == "/authorizations/consume":
            original, answer = db.execute("select body,answer from decisions where id=?", (body["authorizationId"],)).fetchone()
            assert answer == "yes"
            for field in ("externalId", "toolName", "toolTarget", "actor", "parameters"):
                assert body[field] == json.loads(original)[field]
            try:
                db.execute("insert into permits values (?)", (body["authorizationId"],))
            except sqlite3.IntegrityError:
                raise PusharyError("Replay", 409, {"refusal": "already_consumed"})
            db.commit()
            if os.environ.get("CHECK_CRASH_BEFORE_EFFECT"):
                os._exit(24)
            if os.environ.get("CHECK_LOST_PERMIT"):
                raise TimeoutError("Lost response")
            if os.environ.get("CHECK_EXPIRED"):
                patch("run.time.time", return_value=9999999999).start()
            return {"permitId": body["authorizationId"]}
        if path.endswith("/receipt"):
            if os.environ.get("CHECK_CRASH"):
                os._exit(23)
            return {}
        raise AssertionError(path)


def model_response(payload: dict[str, object]) -> object:
    with sqlite3.connect(os.environ["CHECK_SERVICE"], timeout=20) as db:
        db.execute("insert into model_requests values (?)", (json.dumps(payload),))
    if payload["tool_choice"] == "none":
        return json.loads(os.environ.get("CHECK_FINAL", '{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"Orders released."}}]}'))
    return json.loads(os.environ["CHECK_PROPOSAL"])


def proposal(count: int = 1) -> dict[str, object]:
    calls = [{"id": f"call-{number}", "type": "function", "function": {
        "name": "release_order", "arguments": json.dumps({"order_id": f"order-{number}", "amount_cents": 1900})}}
        for number in range(1, count + 1)]
    return {"choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "reasoning_content": "Review the requested orders.", "tool_calls": calls}}]}


class OrderApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "run"
        self.service = self.root / "service.db"
        with sqlite3.connect(self.service) as db:
            db.executescript("create table decisions(id primary key, body, answer); create table permits(id primary key); create table model_requests(body);")
        self.env = {**os.environ, "PUSHARY_API_KEY": "pk_offline.sk_offline", "CHECK_SERVICE": str(self.service), "CHECK_PROPOSAL": json.dumps(proposal())}

    def worker(self, mode: str, tenant: str = "tenant", customer: str = "customer", **env: str) -> subprocess.Popen[bytes]:
        return subprocess.Popen([sys.executable, __file__, mode, str(self.folder), tenant, customer],
                                env={**self.env, **env}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def finish(self, worker: subprocess.Popen[bytes], success: bool = True) -> object:
        stdout, stderr = worker.communicate(timeout=30)
        self.assertEqual(worker.returncode == 0, success, stderr.decode())
        return json.loads(stdout) if success else None

    def sql(self, query: str, parameters: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.service) as db:
            return db.execute(query, parameters).fetchall()

    def start(self, count: int = 1) -> None:
        result = self.finish(self.worker("start", CHECK_PROPOSAL=json.dumps(proposal(count))))
        self.assertIsInstance(result, dict)
        self.assertIn("blocked", result)
        self.assertEqual(self.effects(), 0)

    def approve(self) -> None:
        self.sql("update decisions set answer='yes'")

    def effects(self) -> int:
        if not (self.folder / "orders.db").exists():
            return 0
        with sqlite3.connect(self.folder / "orders.db") as db:
            return db.execute("select count(*) from released").fetchone()[0]

    def test_restart_and_replay_preserve_the_exact_conversation(self) -> None:
        self.start(2)
        self.assertEqual(len(self.sql("select * from decisions")), 2)
        self.finish(self.worker("start"), False)
        self.finish(self.worker("resume"))
        self.assertEqual(len(self.sql("select * from decisions")), 2)
        self.approve()
        result = self.finish(self.worker("resume"))
        self.assertIn("result", result)
        self.assertEqual(self.effects(), 2)
        self.assertEqual(self.finish(self.worker("resume")), result)
        requests = self.sql("select body from model_requests")
        self.assertEqual(len(requests), 2)
        final = json.loads(requests[-1][0])
        self.assertEqual(final["messages"][2], proposal(2)["choices"][0]["message"])
        self.assertEqual([message["tool_call_id"] for message in final["messages"][3:]], ["call-1", "call-2"])
        self.assertEqual(final["tool_choice"], "none")

    def test_partial_approval_does_not_replay_the_first_order(self) -> None:
        self.start(2)
        self.sql("update decisions set answer='yes' where json_extract(body,'$.toolTarget')='order-1'")
        partial = self.finish(self.worker("resume"))
        self.assertIn("blocked", partial)
        self.assertEqual(partial.get("result"), [{"order_id": "order-1", "amount_cents": 1900, "status": "released"}])
        self.assertEqual(self.effects(), 1)
        self.assertEqual(len(self.sql("select * from model_requests")), 1)
        self.approve()
        self.assertIn("result", self.finish(self.worker("resume")))
        self.assertEqual(self.effects(), 2)
        self.assertEqual(len(self.sql("select * from permits")), 2)

    def test_final_model_cannot_start_another_action(self) -> None:
        self.start()
        self.approve()
        outcome = self.finish(self.worker("resume", CHECK_FINAL=json.dumps(proposal(2))))
        self.assertIn("summary_error", outcome)
        self.assertEqual(outcome.get("result"), [{"order_id": "order-1", "amount_cents": 1900, "status": "released"}])
        self.assertEqual(self.effects(), 1)
        self.assertEqual(len(self.sql("select * from permits")), 1)
        self.assertIn("result", self.finish(self.worker("resume")))
        self.assertEqual(self.effects(), 1)

    def test_refusal_never_executes(self) -> None:
        self.start()
        for answer in ("no", "expired", "cancelled", "pending"):
            self.sql("update decisions set answer=?", (answer,))
            self.assertIn("blocked", self.finish(self.worker("resume")))
            self.assertEqual(self.effects(), 0)
            self.assertEqual(self.sql("select * from permits"), [])

    def test_recipient_and_tenant_cannot_change_on_resume(self) -> None:
        self.start()
        self.approve()
        self.finish(self.worker("resume", tenant="other"), False)
        self.finish(self.worker("resume", customer="other"), False)
        self.assertEqual(self.sql("select * from permits"), [])

    def test_saved_proposal_cannot_change(self) -> None:
        self.start()
        self.approve()
        with sqlite3.connect(self.folder / "orders.db") as db:
            row = db.execute("select payload from operation").fetchone()
            value = json.loads(row[0])
            value["customer"] = "other"
            db.execute("update operation set payload=?", (json.dumps(value),))
        self.finish(self.worker("resume"), False)
        self.assertEqual(self.effects(), 0)
        self.assertEqual(self.sql("select * from permits"), [])

    def test_lost_permit_response_stays_blocked(self) -> None:
        self.start()
        self.approve()
        self.assertIn("blocked", self.finish(self.worker("resume", CHECK_LOST_PERMIT="1")))
        self.assertIn("blocked", self.finish(self.worker("resume")))
        self.assertEqual(self.effects(), 0)
        self.assertEqual(len(self.sql("select * from permits")), 1)

    def test_crash_after_permit_before_commit_never_reexecutes(self) -> None:
        self.start()
        self.approve()
        crashed = self.worker("resume", CHECK_CRASH_BEFORE_EFFECT="1")
        crashed.communicate(timeout=30)
        self.assertEqual(crashed.returncode, 24)
        self.assertEqual(self.effects(), 0)
        self.assertIn("blocked", self.finish(self.worker("resume")))
        self.assertEqual(self.effects(), 0)
        self.assertEqual(len(self.sql("select * from permits")), 1)

    def test_expiry_after_permit_stops_effect(self) -> None:
        self.start()
        self.approve()
        self.finish(self.worker("resume", CHECK_EXPIRED="1"), False)
        self.assertEqual(self.effects(), 0)
        self.assertIn("blocked", self.finish(self.worker("resume")))

    def test_concurrent_workers_do_not_repeat_effects(self) -> None:
        self.start()
        self.approve()
        workers = [self.worker("resume") for _ in range(2)]
        for worker in workers:
            self.finish(worker)
        self.assertEqual(self.effects(), 1)
        self.assertEqual(len(self.sql("select * from permits")), 1)

    def test_crash_after_commit_does_not_repeat_order_change(self) -> None:
        self.start()
        self.approve()
        crashed = self.worker("resume", CHECK_CRASH="1")
        crashed.communicate(timeout=30)
        self.assertEqual(crashed.returncode, 23)
        self.assertEqual(self.effects(), 1)
        self.assertIn("result", self.finish(self.worker("resume")))
        self.assertEqual(self.effects(), 1)

    def test_malformed_or_unexpected_proposals_fail_before_asking(self) -> None:
        invalid = [None, {}, {"choices": []}]
        for mutation in ("wrong_order", "wrong_tool", "extra_recipient", "duplicate_call", "truncated"):
            value = proposal(2)
            message = value["choices"][0]["message"]
            if mutation == "wrong_order":
                message["tool_calls"][0]["function"]["arguments"] = '{"order_id":"other","amount_cents":1900}'
            elif mutation == "wrong_tool":
                message["tool_calls"][0]["function"]["name"] = "execute_shell"
            elif mutation == "extra_recipient":
                message["tool_calls"][0]["function"]["arguments"] = '{"order_id":"order-1","amount_cents":1900,"customer":"other"}'
            elif mutation == "duplicate_call":
                message["tool_calls"][1]["id"] = "call-1"
            else:
                value["choices"][0]["finish_reason"] = "length"
            invalid.append(value)
        for number, value in enumerate(invalid):
            self.folder = self.root / f"invalid-{number}"
            self.finish(self.worker("start", CHECK_PROPOSAL=json.dumps(value)), False)
            self.assertEqual(self.sql("select * from decisions"), [])
            self.assertEqual(self.effects(), 0)


class StepHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reply = b'{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"Done"}}]}'
        self.status = 200
        self.requests: list[tuple[str, str | None, object]] = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                fixture.requests.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length))))
                self.send_response(fixture.status)
                self.end_headers()
                self.wfile.write(fixture.reply)

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        endpoint = "http://127.0.0.1:" + str(server.server_port) + "/v1"
        endpoints = patch.dict(run.BASE_URLS, {"global": endpoint})
        credentials = patch.dict(os.environ, {"STEP_API_KEY": "offline-model-key", "STEPFUN_REGION": "global"})
        endpoints.start()
        credentials.start()
        self.addCleanup(endpoints.stop)
        self.addCleanup(credentials.stop)

    def test_posts_the_model_contract_to_the_selected_region(self) -> None:
        response = run.step_chat(run.model_request([{"role": "user", "content": "Hello"}], "none"))
        self.assertEqual(run.parse_final(response), "Done")
        self.assertEqual(len(self.requests), 1)
        path, authorization, payload = self.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(authorization, "Bearer offline-model-key")
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["model"], "step-5-preview")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Hello"}])
        self.assertEqual(payload["tool_choice"], "none")
        self.assertFalse(payload["stream"])

    def test_http_failure_does_not_retry(self) -> None:
        self.status = 429
        with self.assertRaises(urllib.error.HTTPError):
            run.step_chat({})
        self.assertEqual(len(self.requests), 1)

    def test_rejects_oversized_and_malformed_responses(self) -> None:
        for reply in (b"x" * 1_000_001, b"not JSON"):
            self.reply = reply
            with self.assertRaises(ValueError):
                run.step_chat({})

    def test_invalid_region_and_missing_key_never_send_a_request(self) -> None:
        with patch.dict(os.environ, {"STEPFUN_REGION": "invalid"}):
            with self.assertRaises(ValueError):
                run.step_chat({})
        with patch.dict(os.environ, {"STEP_API_KEY": ""}):
            with self.assertRaises(ValueError):
                run.step_chat({})
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    if sys.argv[1:] == ["--demo"]:
        demo = OrderApprovalTests()
        demo.setUp()
        try:
            print("OFFLINE DEMO: StepFun and phone delivery are simulated; the SDK and SQLite workers are real.")
            print("1. Propose orders and request customer approval:")
            print(json.dumps(demo.finish(demo.worker("start", CHECK_PROPOSAL=json.dumps(proposal(2)))), indent=2))
            print("Order changes before approval:", demo.effects())
            demo.approve()
            print("2. Customer fixture answers yes. Resume in a new process:")
            print(json.dumps(demo.finish(demo.worker("resume")), indent=2))
            print("3. Repeat resume; the stored result is returned:")
            print(json.dumps(demo.finish(demo.worker("resume")), indent=2))
            print("Order changes:", demo.effects(), "| Permits consumed:", len(demo.sql("select * from permits")))
        finally:
            demo.doCleanups()
    elif len(sys.argv) == 5:
        with patch("pushary.client.PusharyServer._request", service_request), patch("run.step_chat", model_response):
            print(json.dumps(run.run_demo(sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4])))
    else:
        unittest.main()
