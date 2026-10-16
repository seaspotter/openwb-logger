"""openwb-logger
--------------------------------
Polls openWB's ramdisk logs into TimescaleDB for full retained history.

Copyright (C) 2026 the project author(s).
Licensed under the GNU Affero General Public License v3.0 or later.
See the LICENSE file in the repository root for the full text.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from .db import close_pool, get_pool, init_pool
from .fetcher import fetcher
from .mcp_server import mcp
from .runtime_settings import get_settings
from .web import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("openwb_logger")


async def _poll_loop() -> None:
    pool = get_pool()
    while True:
        rt = await fetcher.fetch_once(pool)
        await asyncio.sleep(rt["fetch_interval_seconds"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        pool = await init_pool()
        rt = await get_settings(pool)
        logger.info(
            "Starting openwb-logger: source=%s%s sources=%s interval=%ss retention=%sd",
            rt["openwb_base_url"], rt["openwb_ramdisk_path"], rt["enabled_sources"],
            rt["fetch_interval_seconds"], rt["retention_days"],
        )
        task = asyncio.create_task(_poll_loop())
        # Mounting the MCP server (see below) disables its own built-in
        # lifespan, so its session manager has to be entered here instead
        # -- otherwise its first request fails.
        await stack.enter_async_context(mcp.session_manager.run())
        yield
        task.cancel()
        await close_pool()


app = FastAPI(title="openwb-logger", lifespan=lifespan)
app.include_router(router)
app.mount("/mcp", mcp.streamable_http_app(
    # streamable_http_path="/" so this lands at exactly /mcp once
    # mounted above, not /mcp/mcp (streamable_http_app()'s own default
    # path is already "/mcp", meant for when it's the *only* app being
    # served standalone, unmounted).
    streamable_http_path="/",
    # Disables mcp's DNS-rebinding Host-header check -- confirmed live
    # as a real bug once already (see DEPLOYMENT.md/CHANGELOG): it
    # auto-enables whenever transport_security isn't given and the
    # (unused-here) `host` param defaults to "127.0.0.1", rejecting
    # every real LAN Host header with a 421. That default assumes this
    # runs its own standalone server bound to loopback; this one is
    # mounted inside the main FastAPI app instead and reached the same
    # way as the rest of it -- explicitly no-auth-by-default, LAN-trust
    # (see mcp_server.py's module docstring) -- so the Host-based
    # allowlist doesn't fit here any more than on any other route.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
))
# Vendored third-party JS only (htmx) -- the rest of the frontend stays
# inlined in index.html, matching this project's one-file-no-build-step
# approach (see CLAUDE.md). A real static dir, not a CDN, so it works
# offline on a LAN and survives a self-update the same way the rest of
# the app does.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
