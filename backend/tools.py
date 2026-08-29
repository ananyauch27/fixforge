"""
Tools the FixForge agent can call.
Each function is deliberately simple and sandboxed to a single project_path.
"""
import os
import subprocess


def list_files(project_path: str) -> list[str]:
    """List all .py files in the project (relative paths)."""
    out = []
    for root, _dirs, files in os.walk(project_path):
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.relpath(os.path.join(root, f), project_path))
    return out


def read_file(project_path: str, filename: str) -> str:
    """Read a file's full contents."""
    path = os.path.join(project_path, filename)
    with open(path, "r") as f:
        return f.read()


def write_file(project_path: str, filename: str, content: str) -> str:
    """Overwrite a file with new content. Returns confirmation string."""
    path = os.path.join(project_path, filename)
    with open(path, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} chars to {filename}"


def run_tests(project_path: str) -> dict:
    """Run pytest in the project directory and return pass/fail + output."""
    result = subprocess.run(
        ["python", "-m", "pytest", "-v"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        "passed": result.returncode == 0,
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-1500:],
    }


# Tool schema definitions in OpenAI/Groq function-calling format
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all Python files in the project so you know what exists before reading anything.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a specific file in the project.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Overwrite a file with corrected content. Only call this once you are confident in the fix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the project's test suite (pytest) and return pass/fail plus output. Use this to verify a fix.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
