# AI-Native SDLC Orchestrator

An agentic workflow that prepares pull requests. A planner agent reads a branch's diff and sends work to three specialist agents, which write the PR description, generate and run unit tests, and scan the change for security issues. Each agent works in a plan, observe, execute loop, streams its reasoning to a live dashboard over WebSocket, and then the whole run pauses until a human approves, edits or rejects it.

Built with **LangGraph**, **AWS Bedrock**, **FastAPI**, and **React + TypeScript**.

![Review screen](docs/review.png)

## How it works

```
observe_diff -> plan --+--> summarize ------------------------------+
                       +--> tests_plan -> tests_write -> tests_run -+--> human_review -> finalize
                       |                      ^             |       |     (interrupt)
                       |                      +--- retry ---+       |
                       +--> security_rules -> security_review ------+
```

| Agent | Plan | Observe | Execute |
|---|---|---|---|
| **Planner** | Decides which agents the diff needs and what each should focus on | Parses the diff, commit messages and changed symbols | Fans out to the chosen agents in parallel |
| **PR summary** | | Reads the diff and commits | Writes the title, description, risk level, testing notes and reviewer checklist |
| **Test generation** | Finds the top-level Python functions the diff touched | Runs the tests with pytest against a clean checkout of the PR head | Writes a test file; on failure, reads the pytest output and rewrites it, up to 3 attempts. If a failure points at a bug in the code rather than the test, it keeps the test as `xfail` and reports the suspected bug |
| **Security scan** | | Runs 12 deterministic rules (secrets, shell and SQL injection, unsafe deserialization, disabled TLS checks and more) over added lines | The model confirms or dismisses each hit in context and looks for issues the rules can't catch |

`human_review` is a deferred node, so it waits for every branch, including the test retry loop, and then calls LangGraph's `interrupt`. The reviewer can edit the title, dismiss false positives, keep or drop the generated tests, optionally write them into the repo, and add a note. Nothing is written until they approve. Open critical or high findings raise the PR's risk to high.

On approval the run writes `PR_DESCRIPTION.md`, the passing test files and `security-report.json` to `runs/<run-id>/`.

## Quick start

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# dashboard
cd ../frontend && npm install && npm run build

# serve the API and the built dashboard on http://127.0.0.1:8000
cd ../backend && sdlc-orchestrator serve
```

Click **Run the demo**. It creates a small invoicing repo whose feature branch has a real off-by-one bug (`bulk_tier(50)` returns 5 instead of the documented 10) and a file with a hardcoded API key, a `shell=True` call, string-built SQL and disabled TLS verification. You'll see the test agent fail, retry and flag the bug, and the security agent report the four issues.

For frontend development, run `npm run dev` in `frontend/` while the backend is running; Vite proxies `/api` and `/ws` to port 8000.

### Command line

```bash
sdlc-orchestrator run --repo ~/code/my-service --base main --head my-branch   # review in the terminal
sdlc-orchestrator run --demo --yes --json                                     # sample repo, auto-approve
sdlc-orchestrator demo-repo ./sample                                          # create the sample repo
```

## Models

| `LLM_PROVIDER` | What runs |
|---|---|
| `offline` (default) | A deterministic heuristic model that answers every agent task without any credentials. It builds tests from docstring examples and signatures, confirms rule hits and dismisses obvious placeholders. It's what the tests and the demo use. |
| `bedrock` | Claude on AWS Bedrock through the Converse API (`langchain-aws`). Uses your normal AWS credentials. |

```bash
export LLM_PROVIDER=bedrock
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0   # any Bedrock chat model ID or inference profile
```

Other settings: `MAX_TEST_ATTEMPTS` (3), `MAX_TEST_FILES` (3), `TEST_TIMEOUT_S` (60), `RUNS_DIR` (`./runs`).

## API

| Method | Path | |
|---|---|---|
| `GET` | `/api/health` | Version and active model |
| `POST` | `/api/runs` | Start a run: `{"repo": "/path", "base": "main", "head": "HEAD"}`, `{"diff": "..."}` or `{"demo": true}` |
| `GET` | `/api/runs`, `/api/runs/{id}` | List runs, or get a run's events, review payload and report |
| `POST` | `/api/runs/{id}/review` | `{"decision": "approve" \| "reject", "title", "note", "dismissed": [ids], "include_tests", "apply_tests"}` |
| `WS` | `/ws/runs/{id}` | Sends a snapshot, then `event` and `status` messages. Send `{"type": "review", "review": {...}}` to resume |

## Security note

The test agent runs model-written code with your Python interpreter, in a temporary checkout with a timeout. The server binds to `127.0.0.1` by default; don't expose it on a network you don't trust.

## Tests

```bash
cd backend && pytest -q      # diff parsing, rules, offline model, full graph runs, HTTP and WebSocket API
cd frontend && npm test      # reducer, agent lanes, review panel
```

## Project layout

```
backend/sdlc_orchestrator/
  graph.py           LangGraph workflow and agents
  llm.py             Bedrock and offline models
  prompts.py         Agent system prompts
  security_rules.py  Deterministic security rules
  testrunner.py      Clean checkouts and pytest runs
  diff.py            Diff parsing and git helpers
  report.py          PR description rendering
  server.py          FastAPI + WebSocket server
  cli.py             Command line
  demo.py            Sample repository
frontend/src/        React dashboard
```

## Status

Unreleased and in active development. Next up: posting the description and findings straight to a GitHub pull request, test generation for TypeScript with Vitest, and persisting runs across server restarts.
