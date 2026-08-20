"""Self-update: `git pull` the mounted repo checkout, then rebuild and
recreate the running stack over the Docker socket.

This deliberately does NOT run `docker compose up -d --build` in this same
process/container: that command's own job is to stop-and-replace the very
container running it, which would kill this process (and anything it
spawned inside the same container's PID namespace) partway through the
recreate step. Instead it launches a short-lived *sibling* container (via
the mounted docker.sock -- "Docker-outside-of-Docker") that runs the
rebuild independently on the host, immune to this container's own restart.

Because that sibling container is created by the host daemon, not by us,
any bind mount it needs must be given as a host-absolute path -- hence
HOST_REPO_DIR (see app/config.py), distinct from REPO_DIR (this
container's own view of the same checkout, used only for `git pull`).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime

from .config import settings
from .db import get_state, set_state

logger = logging.getLogger("openwb_logger.updater")

_STATE_KEY = "update_status"
_UPDATER_IMAGE = "docker:27-cli"


class UpdateError(Exception):
    pass


@dataclass
class UpdateResult:
    started_at: str
    ok: bool
    step: str
    detail: str


def self_update_available() -> bool:
    return bool(settings.host_repo_dir)


async def _run(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="replace").strip()


async def run_update(pool) -> UpdateResult:
    """Pulls the latest code, then hands off the rebuild+recreate to a
    detached sibling container so it survives this container being
    replaced. Persists the outcome (of the part we can observe) so the UI
    can show it after the restart."""
    started_at = datetime.now().isoformat(timespec="seconds")

    if not settings.host_repo_dir:
        result = UpdateResult(
            started_at=started_at, ok=False, step="config",
            detail="HOST_REPO_DIR is not set; self-update is disabled. See DEPLOYMENT.md.",
        )
        await set_state(pool, _STATE_KEY, asdict(result))
        return result

    code, out = await _run("git", "-C", settings.repo_dir, "pull", "--ff-only")
    if code != 0:
        result = UpdateResult(started_at=started_at, ok=False, step="git pull", detail=out)
        await set_state(pool, _STATE_KEY, asdict(result))
        return result

    logger.info("git pull: %s", out)

    code, out = await _run(
        "docker", "run", "-d", "--rm",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{settings.host_repo_dir}:/repo",
        "-w", "/repo",
        _UPDATER_IMAGE,
        "docker", "compose", "up", "-d", "--build",
    )
    if code != 0:
        result = UpdateResult(
            started_at=started_at, ok=False, step="launch rebuild",
            detail=out,
        )
        await set_state(pool, _STATE_KEY, asdict(result))
        return result

    result = UpdateResult(
        started_at=started_at, ok=True, step="rebuild launched",
        detail=f"git pull: {out or '(already up to date)'}. "
               "Rebuild running in a detached helper container -- this app "
               "will restart shortly once it completes.",
    )
    await set_state(pool, _STATE_KEY, asdict(result))
    return result


async def get_update_status(pool) -> dict | None:
    return await get_state(pool, _STATE_KEY, default=None)


async def get_current_commit() -> str | None:
    code, out = await _run("git", "-C", settings.repo_dir, "rev-parse", "--short", "HEAD")
    return out if code == 0 else None
