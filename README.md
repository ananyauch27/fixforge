# FixForge — Autonomous Software Debugging Agent

FixForge is an AI agent that investigates a real bug report against an
actual codebase, diagnoses the root cause, applies a fix, and **verifies
the fix by running the test suite itself** — rather than just describing
what might be wrong.

Built for The Agent Harness Hackathon.

## Why this is an agent, not a chatbot

The LLM does not answer from a single prompt. It decides, step by step,
which tool to call next (list files → read files → write a fix → run
tests), observes each tool's real output, and only stops once it has a
verified result or runs out of steps. That loop lives in `backend/agent.py`.

## Architecture

```
User bug report
      |
   FastAPI /analyze
      |
  Agent loop (Claude + tool use)
      |
 ┌────┴────┬───────────┬────────────┐
 list_files read_file  write_file  run_tests
      |
  Verified fix + root cause summary
```

## Setup

Runs on **Groq's free tier** (llama-3.3-70b-versatile) — no credit card, no
trial expiry. Sign up at [console.groq.com](https://console.groq.com), grab
an API key from **API Keys → Create API Key**.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY
```

## Run it

```bash
cd backend
export GROQ_API_KEY=gsk_...
uvicorn main:app --reload --port 8000
```

## Two-phase flow: investigate freely, pause before writing

The agent can call `list_files`, `read_file`, and `run_tests` on its own.
The moment it wants to change code, the session **pauses** with
`status: "awaiting_approval"` and returns the proposed diff — nothing is
written to disk yet.

**1. Start the session:**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"bug": "POST /users returns 422 Unprocessable Entity", "project_path": "../demo_project"}'
```

This returns something like:

```json
{
  "session_id": "5c2e...",
  "status": "awaiting_approval",
  "proposed_fix": {
    "filename": "app.py",
    "content": "... corrected file contents ..."
  },
  "transcript": [ ... ]
}
```

**2. Approve (or reject) it:**

```bash
curl -X POST http://localhost:8000/approve \
  -H "Content-Type: application/json" \
  -d '{"session_id": "5c2e...", "approved": true}'
```

If `approved: true`, the fix is written and the agent runs the tests to
verify it, then returns a final summary. If `approved: false`, the agent
is told the fix was rejected and goes back to re-diagnose. You can also
pass `edited_content` to apply your own tweaked version of the fix
instead of the agent's exact proposal.

## Demo script (for judges, ~2 minutes)

1. Show `demo_project/` — a small FastAPI app with a real bug: the test
   sends `username` but the API model requires `email`.
2. Run the curl command above (or trigger it from the UI).
3. Walk through the returned transcript: the agent lists files, reads
   `app.py` and `test_users.py`, identifies the field mismatch, writes a
   fix, and re-runs `pytest` to confirm it passes.
4. Show the final summary block (`ROOT_CAUSE`, `FIX_APPLIED`,
   `TEST_RESULT`, `CONFIDENCE`).
5. Show the GitHub PR where Qodo reviewed this code (see below).

## Qodo Code Review Evidence

<!--
Fill this in before submission:
- Link to at least one representative merged PR with meaningful hackathon code
- 1-2 lines on what Qodo found and what you changed or dismissed
- Make sure the PR history shows the Qodo review + a follow-up review
-->

Qodo was used to review the agent implementation through GitHub Pull
Requests. Qodo identified [ISSUE FOUND] in `agent.py` / `tools.py`. This
was fixed by [WHAT YOU CHANGED], and a follow-up review confirmed the fix
before merging.

PR: https://github.com/ananyauch27/fixforge/pull/1
## Roadmap (if time allows)

- Accept a GitHub issue URL directly instead of free-text bug reports
- Auto-open a PR with the fix instead of writing directly to disk
- Add a `search_files(keyword)` tool for larger codebases
- Simple React UI showing the live step-by-step transcript
