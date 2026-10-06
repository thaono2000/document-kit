from __future__ import annotations

from pathlib import Path
from .util import run, which, extract_json_object, DocumentKitError

class CursorAgent:
    def __init__(self, command: str, workspace: Path, model: str = "", timeout: int = 1800):
        self.command = command
        self.workspace = workspace
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        return which(self.command) is not None

    def ask_json(self, prompt: str) -> dict:
        if not self.available():
            raise DocumentKitError(
                f"Cursor CLI '{self.command}' not found. Install Cursor CLI or run with --plan-only."
            )
        cmd = [self.command, "--workspace", str(self.workspace), "--mode=ask", "-p", prompt, "--output-format", "text"]
        if self.model:
            cmd.extend(["--model", self.model])
        cp = run(cmd, timeout=self.timeout)
        return extract_json_object(cp.stdout)
