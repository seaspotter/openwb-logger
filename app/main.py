from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import close_pool, init_pool
from .fetcher import fetcher
from .web import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("openwb_logger")


async def _poll_loop() -> None:
    while True:
        await fetcher.fetch_once()
        await asyncio.sleep(settings.fetch_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting openwb-logger: source=%s interval=%ss retention=%sd",
        settings.log_url, settings.fetch_interval_seconds, settings.retention_days,
    )
    await init_pool()
    task = asyncio.create_task(_poll_loop())
    yield
    task.cancel()
    await close_pool()


app = FastAPI(title="openwb-logger", lifespan=lifespan)
app.include_router(router)
