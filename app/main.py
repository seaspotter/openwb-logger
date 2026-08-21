from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

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
app.mount("/mcp", mcp.streamable_http_app())
