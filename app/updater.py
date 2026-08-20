"""Self-update via git: docker-compose.yml bind-mounts the whole repo onto
WORKDIR (/app), so `git pull` here updates the live code directly -- a
process restart then picks it up, no image rebuild needed for pure
code/template changes. If requirements.txt or the Dockerfile changed, we
deliberately do NOT auto-restart, since the new dependency wouldn't be
installed until the image itself is rebuilt.

No Docker socket, no sibling container, no root access to the host: this
container just restarts itself (`os._exit(0)`), and docker-compose's own
`restart: unless-stopped` brings it back up with the freshly pulled code.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from fastapi import BackgroundTasks

REPO_DIR = "/app"


def self_update_available() -> bool:
    """False for a plain image deployment without the bind-mount (no /app/
    .git to update), so the UI can hide the Update controls entirely
    instead of showing a confusing raw git error."""
    return (Path(REPO_DIR) / ".git").exists()


def _run(*args: str, timeout: int = 60) -> tuple[int, str, str]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_current_commit() -> str | None:
    """Local-only (no network), cheap enough to call on every settings-panel
    open -- unlike check_for_update() below, which does a git fetch."""
    code, out, _ = _run("git", "-C", REPO_DIR, "rev-parse", "--short", "HEAD")
    return out if code == 0 else None


def check_for_update() -> dict:
    if not self_update_available():
        return {
            "current": None, "latest": None, "update_available": False,
            "error": "Kein Git-Checkout unter /app (Bind-Mount fehlt?). Siehe DEPLOYMENT.md.",
        }
    try:
        code, _, err = _run("git", "-C", REPO_DIR, "fetch", timeout=30)
        if code != 0:
            return {"current": get_current_commit(), "latest": None,
                    "update_available": False, "error": err}
        current = get_current_commit()
        code, latest, _ = _run("git", "-C", REPO_DIR, "rev-parse", "--short", "@{u}")
        if code != 0:
            return {
                "current": current, "latest": None, "update_available": False,
                "error": "Kein Upstream-Branch konfiguriert (git branch --set-upstream-to=...).",
            }
        return {
            "current": current, "latest": latest,
            "update_available": current != latest, "error": None,
        }
    except subprocess.TimeoutExpired:
        return {"current": get_current_commit(), "latest": None,
                "update_available": False, "error": "git fetch: Zeitüberschreitung"}


def _restart_process() -> None:
    time.sleep(1)  # let the HTTP response actually reach the browser first
    os._exit(0)  # docker-compose's `restart: unless-stopped` brings it back with the new code


def run_update(background_tasks: BackgroundTasks) -> dict:
    if not self_update_available():
        return {
            "ok": False,
            "message": "Kein Git-Checkout unter /app -- Self-Update nicht möglich.",
            "restarting": False,
        }
    try:
        code, before, err = _run("git", "-C", REPO_DIR, "rev-parse", "HEAD")
        if code != 0:
            return {"ok": False, "message": err, "restarting": False}

        code, _, err = _run("git", "-C", REPO_DIR, "pull", "--ff-only")
        if code != 0:
            return {"ok": False, "message": err, "restarting": False}

        code, after, _ = _run("git", "-C", REPO_DIR, "rev-parse", "HEAD")
        if before == after:
            return {"ok": True, "message": "Bereits aktuell.", "restarting": False}

        code, changed, _ = _run("git", "-C", REPO_DIR, "diff", "--name-only", before, after)
        if "requirements.txt" in changed or "Dockerfile" in changed:
            return {
                "ok": True,
                "message": (
                    "Aktualisiert, aber requirements.txt oder das Dockerfile haben sich "
                    "geändert -- ein Rebuild ist nötig: docker compose up -d --build"
                ),
                "restarting": False,
            }

        background_tasks.add_task(_restart_process)
        return {"ok": True, "message": "Aktualisiert. Startet neu...", "restarting": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "git pull: Zeitüberschreitung", "restarting": False}
