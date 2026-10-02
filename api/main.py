"""HTTP service for Lab 1: a process we will later wrap in namespaces/cgroups."""

from __future__ import annotations

import os
import threading
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse

app = FastAPI(title="api")


_held: list[bytearray] = []
_burn_started = False
_burn_lock = threading.Lock()


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/eat")
def eat(mb: Annotated[int, Query(ge=1, le=4096)]) -> dict[str, int]:
    buf = bytearray(mb * 1024 * 1024)
    # Touch each page so RSS grows and cgroup memory.max can OOM.
    for i in range(0, len(buf), 4096):
        buf[i] = 1
    _held.append(buf)
    total_mb = sum(len(chunk) for chunk in _held) // (1024 * 1024)
    return {"allocated_mb": mb, "held_mb": total_mb, "pid": os.getpid()}


def _burn_core() -> None:
    while True:
        _ = 1000**1000


@app.get("/burn")
def burn() -> dict[str, int | str]:
    global _burn_started
    with _burn_lock:
        if not _burn_started:
            threading.Thread(target=_burn_core, daemon=True).start()
            _burn_started = True
            status = "started"
        else:
            status = "already_running"
    return {"status": status, "pid": os.getpid()}
