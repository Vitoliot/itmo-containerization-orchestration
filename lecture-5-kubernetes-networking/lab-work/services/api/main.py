"""Shop API: Lab 2 observability + Lab 5 real PostgreSQL orders."""
from __future__ import annotations
import json
import logging
import os
import socket
import time
import random
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

class JSONLogs(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = trace.get_current_span().get_span_context()
        return json.dumps({
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "shop-api",
            "pod": socket.gethostname(),
            "trace_id": f"{ctx.trace_id:032x}" if ctx.is_valid else "0" * 32,
        }, ensure_ascii=False)

handler = logging.StreamHandler()
handler.setFormatter(JSONLogs())
logger = logging.getLogger("shop.api")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
provider = TracerProvider(resource=Resource.create({"service.name": "shop-api"}))
if endpoint:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
        endpoint=endpoint, insecure=endpoint.startswith("http://"))))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("shop-api")

REQUESTS = Counter("api_http_requests_total", "API requests", ["method", "route", "status_code"])
ERRORS = Counter("api_http_errors_total", "API 5xx errors", ["method", "route", "status_code"])
DURATION = Histogram("api_http_request_duration_seconds", "API latency", ["method", "route"])

DDL = """CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  item TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
)"""

def connect():
    return psycopg.connect(connect_timeout=3, row_factory=dict_row)

def ensure_schema():
    for attempt in range(30):
        try:
            with connect() as conn:
                conn.execute(DDL)
            logger.info("schema_ready")
            return
        except psycopg.Error as exc:
            logger.warning("postgres_wait attempt=%d error=%s", attempt + 1, type(exc).__name__)
            time.sleep(2)
    raise RuntimeError("PostgreSQL not available for schema initialization")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(ensure_schema)
    yield

app = FastAPI(title="Shop API", lifespan=lifespan)

@app.middleware("http")
async def telemetry(request: Request, call_next):
    begin = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", request.url.path)
        elapsed = time.perf_counter() - begin
        if request.url.path != "/metrics":
            labels = (request.method, route, str(status))
            REQUESTS.labels(*labels).inc()
            DURATION.labels(request.method, route).observe(elapsed)
            if status >= 500:
                ERRORS.labels(*labels).inc()
        logger.info("request %s %s status=%d ms=%.2f", request.method, route, status, elapsed * 1000)

@app.get("/health", response_class=PlainTextResponse)
def health():
    if os.environ.get("HEALTH_FAIL", "false").lower() == "true":
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return "ok"

@app.get("/whoami")
def whoami():
    return {"pod": socket.gethostname()}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/fail")
def fail():
    logger.error("intentional_failure")
    return JSONResponse(status_code=500, content={"error": "intentional failure"})

@app.get("/slow")
def slow():
    with tracer.start_as_current_span("slow-op"):
        delay = random.uniform(1.0, 3.0)
        time.sleep(delay)
        return {"delay_seconds": round(delay, 3)}

@app.get("/load")
async def load(requests: Annotated[int, Query(ge=1, le=250)] = 50):
    # This intentionally calls localhost, so NOT suitable for Service failover testing.
    async with httpx.AsyncClient(timeout=3) as client:
        out = await asyncio.gather(*(client.get("http://127.0.0.1:8080/health") for _ in range(requests)), return_exceptions=True)
    return {"succeeded": sum(isinstance(v, httpx.Response) and v.status_code == 200 for v in out)}

class OrderIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)

@app.post("/order", status_code=201)
def create_order(order: OrderIn):
    try:
        with tracer.start_as_current_span("insert-order"):
            with connect() as conn:
                row = conn.execute("INSERT INTO orders (item) VALUES (%s) RETURNING id, item, status", (order.item,)).fetchone()
        return row
    except psycopg.Error:
        logger.exception("order_creation_failed")
        raise HTTPException(status_code=503, detail="database unavailable")

@app.get("/orders")
def list_orders():
    try:
        with connect() as conn:
            return conn.execute("SELECT id, item, status, created_at, processed_at FROM orders ORDER BY id DESC LIMIT 50").fetchall()
    except psycopg.Error:
        logger.exception("orders_list_failed")
        raise HTTPException(status_code=503, detail="database unavailable")

@app.get("/orders/{order_id}")
def get_order(order_id: int):
    try:
        with connect() as conn:
            row = conn.execute("SELECT id, item, status, created_at, processed_at FROM orders WHERE id=%s", (order_id,)).fetchone()
    except psycopg.Error:
        logger.exception("order_read_failed")
        raise HTTPException(status_code=503, detail="database unavailable")
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return row

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
