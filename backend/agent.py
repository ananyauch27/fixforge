"""
FixForge agent core, v3 — running on Groq (free tier, no credit card).

Same two-phase design as before: the agent can freely call list_files,
read_file, and run_tests on its own. The moment it wants to call
write_file, the loop PAUSES and hands the proposed diff back to the
caller for human approval before anything is written to disk.

Groq's API is OpenAI-compatible, so this uses the standard
"tool_calls" / "role": "tool" pattern instead of Anthropic's
"tool_use" / "tool_result" blocks.
"""
import json
import uuid
from groq import Groq
from tools import list_files, read_file, write_file, run_tests, TOOL_SCHEMAS

# llama-3.3-70b-versatile is a good balance of quality + tool-calling
# reliability on Groq's free tier. Swap to "openai/gpt-oss-120b" if you
# want to try an alternative.
# MODEL = "llama-3.3-70b-versatile"
MODEL = "openai/gpt-oss-120b"
MAX_STEPS = 8

client = Groq()  # reads GROQ_API_KEY from env

SYSTEM_PROMPT = """You are FixForge, an autonomous software debugging agent.

You will be given a bug report and access to a project's files via tools.
Your job:
1. Investigate: list files, read the relevant ones (source + tests).
2. Diagnose: figure out the actual root cause. Be specific (file + line/field).
3. Propose a fix: call write_file with the corrected full file content.
   A human will review this before it is applied — write the file exactly
   as you want it to end up, since the tool result you get back will tell
   you whether it was approved or rejected.
4. Verify: once a write is approved and applied, use run_tests to confirm.
5. If tests still fail, or your fix was rejected, re-diagnose and try again.

When finished, respond with a final plain-text summary in this exact format
and do not call any more tools after it:
ROOT_CAUSE: <one or two sentences>
FIX_APPLIED: <what you changed, and in which file>
TEST_RESULT: <PASSED or FAILED, with brief detail>
CONFIDENCE: <0-100>%
"""

# In-memory session store. Fine for a hackathon demo; swap for Redis/DB later.
SESSIONS: dict[str, dict] = {}


def _execute_readonly_tool(name: str, tool_input: dict, project_path: str):
    if name == "list_files":
        return list_files(project_path)
    if name == "read_file":
        return read_file(project_path, tool_input["filename"])
    if name == "run_tests":
        return run_tests(project_path)
    raise ValueError(f"{name} is not a read-only tool")


def _assistant_message_dict(message) -> dict:
    """Convert a Groq SDK message object into a plain dict for re-sending."""
    d = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ]
    return d


def _advance(session_id: str) -> dict:
    """Runs the loop forward until it needs approval, finishes, or hits max steps."""
    session = SESSIONS[session_id]
    messages = session["messages"]
    project_path = session["project_path"]

    for _ in range(MAX_STEPS - session["steps_used"]):
        completion = client.chat.completions.create(
            model=MODEL,
            max_tokens=1500,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = completion.choices[0].message
        messages.append(_assistant_message_dict(msg))
        session["steps_used"] += 1

        if msg.content:
            session["transcript"].append({"type": "reasoning", "content": msg.content})

        tool_calls = msg.tool_calls or []

        if not tool_calls:
            session["status"] = "done"
            session["final_summary"] = msg.content or ""
            return _public_view(session_id)

        write_call = next(
            (c for c in tool_calls if c.function.name == "write_file"), None
        )

        # Execute any read-only tools in this batch immediately
        tool_result_messages = []
        for call in tool_calls:
            if call.function.name == "write_file":
                continue  # handled separately below, needs approval
            args = json.loads(call.function.arguments or "{}")
            result = _execute_readonly_tool(call.function.name, args, project_path)
            session["transcript"].append(
                {"type": "tool_call", "tool": call.function.name, "input": args, "result": result}
            )
            tool_result_messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": str(result)}
            )

        if write_call:
            args = json.loads(write_call.function.arguments or "{}")
            session["status"] = "awaiting_approval"
            session["pending_write"] = {
                "tool_call_id": write_call.id,
                "filename": args["filename"],
                "content": args["content"],
            }
            session["pending_readonly_results"] = tool_result_messages
            session["transcript"].append(
                {"type": "proposed_fix", "filename": args["filename"], "content": args["content"]}
            )
            return _public_view(session_id)

        # No write requested this round — feed read-only results back and loop again
        messages.extend(tool_result_messages)

    session["status"] = "max_steps_reached"
    return _public_view(session_id)


def _public_view(session_id: str) -> dict:
    s = SESSIONS[session_id]
    view = {
        "session_id": session_id,
        "status": s["status"],
        "steps_used": s["steps_used"],
        "transcript": s["transcript"],
    }
    if s["status"] == "awaiting_approval":
        view["proposed_fix"] = {
            "filename": s["pending_write"]["filename"],
            "content": s["pending_write"]["content"],
        }
    if s["status"] == "done":
        view["final_summary"] = s["final_summary"]
    return view


def start_session(bug_report: str, project_path: str) -> dict:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "messages": [{"role": "user", "content": f"Bug report: {bug_report}"}],
        "project_path": project_path,
        "transcript": [],
        "steps_used": 0,
        "status": "running",
    }
    return _advance(session_id)


def resume_session(session_id: str, approved: bool, edited_content: str | None = None) -> dict:
    session = SESSIONS[session_id]
    if session["status"] != "awaiting_approval":
        raise ValueError("Session is not awaiting approval")

    pending = session["pending_write"]
    filename = pending["filename"]
    content = edited_content if edited_content is not None else pending["content"]

    if approved:
        result = write_file(session["project_path"], filename, content)
        session["transcript"].append(
            {"type": "human_decision", "decision": "approved", "filename": filename}
        )
        tool_message = f"Human APPROVED the fix to {filename}. {result}"
    else:
        session["transcript"].append(
            {"type": "human_decision", "decision": "rejected", "filename": filename}
        )
        tool_message = (
            f"Human REJECTED the proposed fix to {filename}. "
            "Reconsider the diagnosis and propose a different fix."
        )

    tool_result_messages = list(session["pending_readonly_results"])
    tool_result_messages.append(
        {"role": "tool", "tool_call_id": pending["tool_call_id"], "content": tool_message}
    )
    session["messages"].extend(tool_result_messages)
    session["status"] = "running"
    session["pending_write"] = None
    session["pending_readonly_results"] = None

    return _advance(session_id)
