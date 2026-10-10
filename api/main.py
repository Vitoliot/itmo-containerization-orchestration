from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "api")
SELF_BASE_URL = os.getenv("SELF_BASE_URL", "http://127.0.0.1:8080")


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line and correlate it with the current span."""

    _standard_fields = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        trace_id = (
            format(span_context.trace_id, "032x")
            if span_context.is_valid
            else "0" * 32
        )
        span_id = (
            format(span_context.span_id, "016x")
            if span_context.is_valid
            else "0" * 16
        )

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        }

        for key, value in record.__dict__.items():
            if key not in self._standard_fields and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    # Let our formatter handle uvicorn logs too.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    return logging.getLogger("api")


def _server_request_hook(span: trace.Span, scope: dict[str, Any]) -> None:
    """Persist the request trace id in ASGI scope for request-completion logs."""
    if span and span.get_span_context().is_valid:
        scope["otel_trace_id"] = format(span.get_span_context().trace_id, "032x")


def configure_tracing() -> trace.Tracer:
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=endpoint.startswith("http://"),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    return trace.get_tracer(SERVICE_NAME)


logger = configure_logging()
tracer = configure_tracing()
app = FastAPI(title="api")


REQUESTS = Counter(
    "api_http_requests_total",
    "Total number of HTTP requests.",
    ("method", "route", "status_code"),
)
ERRORS = Counter(
    "api_http_errors_total",
    "Total number of HTTP responses with status >= 500.",
    ("method", "route", "status_code"),
)
DURATION = Histogram(
    "api_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10),
)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        logger.exception(
            "request_failed",
            extra={"method": request.method, "path": request.url.path},
        )
        raise
    finally:
        duration = time.perf_counter() - started
        route = request.scope.get("route")
        route_label = getattr(route, "path", request.url.path)

        # Scraping /metrics should not distort the service RED metrics.
        if request.url.path != "/metrics":
            labels = {
                "method": request.method,
                "route": route_label,
                "status_code": str(status_code),
            }
            REQUESTS.labels(**labels).inc()
            DURATION.labels(method=request.method, route=route_label).observe(duration)
            if status_code >= 500:
                ERRORS.labels(**labels).inc()

        logger.info(
            "request_completed",
            extra={
                "trace_id": request.scope.get("otel_trace_id", "0" * 32),
                "method": request.method,
                "path": request.url.path,
                "route": route_label,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 3),
            },
        )


_held: list[bytearray] = []
_burn_started = False
_burn_lock = threading.Lock()


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/fail")
def fail() -> JSONResponse:
    span = trace.get_current_span()
    span.set_status(Status(StatusCode.ERROR, "intentional failure"))
    span.set_attribute("error.type", "intentional_failure")

    logger.error("intentional_failure")
    return JSONResponse(status_code=500, content={"error": "intentional failure"})


@app.get("/slow")
def slow() -> dict[str, float | str]:
    delay = random.uniform(1.0, 3.0)
    with tracer.start_as_current_span("slow-op") as span:
        span.set_attribute("slow.duration_seconds", delay)
        time.sleep(delay)

    return {"status": "ok", "slept_seconds": round(delay, 3)}


@app.get("/load")
async def load(
    requests: Annotated[int, Query(ge=1, le=500)] = 50,
    concurrency: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, int]:
    """Generate concurrent requests to this service to create an RPS spike."""

    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=SELF_BASE_URL, timeout=10.0) as client:
        async def hit_health() -> bool:
            async with semaphore:
                try:
                    response = await client.get("/health")
                    return response.status_code == 200
                except httpx.HTTPError:
                    return False

        results = await asyncio.gather(*(hit_health() for _ in range(requests)))

    succeeded = sum(results)
    return {
        "requested": requests,
        "succeeded": succeeded,
        "failed": requests - succeeded,
    }


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/eat")
def eat(mb: Annotated[int, Query(ge=1, le=4096)]) -> dict[str, int]:
    buf = bytearray(mb * 1024 * 1024)
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


# FastAPI instrumentation creates a server span for every incoming request.
# It is applied after our middleware so request logs run inside the active span.
FastAPIInstrumentor.instrument_app(app, server_request_hook=_server_request_hook)
# Instrument /load's outgoing HTTP calls too, so trace context propagates to /health.
HTTPXClientInstrumentor().instrument()
