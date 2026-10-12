import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, Response


app = FastAPI(title="worker")


@app.get("/health", response_class=PlainTextResponse)
def health() -> Response:
    if os.getenv("HEALTH_FAIL", "false").lower() == "true":
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "reason": "HEALTH_FAIL is enabled"},
        )
    return "ok"
