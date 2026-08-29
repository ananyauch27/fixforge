from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import start_session, resume_session

app = FastAPI(title="FixForge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    bug: str
    project_path: str = "../demo_project"


class ApproveRequest(BaseModel):
    session_id: str
    approved: bool
    edited_content: str | None = None  # let a human tweak the fix before applying it


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """
    Starts a new debugging session. The agent investigates on its own and
    will either finish, or pause with status "awaiting_approval" once it
    wants to write a fix — in which case call /approve next.
    """
    return start_session(req.bug, req.project_path)


@app.post("/approve")
def approve(req: ApproveRequest):
    """
    Resumes a paused session after a human reviews the proposed fix.
    Set approved=false to send the agent back to re-diagnose instead.
    Optionally pass edited_content to apply a human-modified version of
    the fix instead of the agent's exact proposal.
    """
    try:
        return resume_session(req.session_id, req.approved, req.edited_content)
    except (ValueError, KeyError):
        raise HTTPException(status_code=404, detail="Unknown or non-pending session_id")


@app.get("/health")
def health():
    return {"status": "ok"}
