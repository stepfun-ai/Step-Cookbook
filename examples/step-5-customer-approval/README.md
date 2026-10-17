# Step 5 customer approval before tool execution

[Read the complete English cookbook](en/README.md).

This example saves Step 5 tool-call proposals, requests customer phone approval
through the published Pushary SDK, and resumes a local SQLite order operation
in a new Python process. Synthetic orders only; no external order is changed.

Run commands from this directory. Python 3.9+ is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python check_run.py --demo
.venv/bin/python check_run.py -v
```

The demo and checks simulate StepFun and Pushary HTTP service responses; they
run real SDK code, subprocesses and SQLite transactions. Live use additionally
requires StepFun credentials, a Pushary Partner workspace and an enrolled test
customer. See the article for credentials, regions, complete source, live
commands and recovery limits. This independently maintained recipe does not
claim official StepFun endorsement or completed live-provider validation.
