"""Minimal reliable background consumer using FOR UPDATE SKIP LOCKED."""
import asyncio
import json
import logging
import socket
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import psycopg
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from prometheus_client import Counter, CONTENT_TYPE_LATEST, generate_latest

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('shop-worker')
processed = Counter('shop_worker_orders_processed_total', 'Processed orders')
errors = Counter('shop_worker_processing_errors_total', 'Processing failures')
stop = threading.Event()

def worker_loop():
    while not stop.is_set():
        try:
            with psycopg.connect(connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM orders WHERE status='pending' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1")
                    row = cur.fetchone()
                    if row:
                        cur.execute("UPDATE orders SET status='processed', processed_at=now() WHERE id=%s", (row[0],))
                if row:
                    processed.inc()
                    log.info(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'event':'order_processed', 'id':row[0], 'pod':socket.gethostname()}))
        except psycopg.Error as e:
            errors.inc()
            log.warning(json.dumps({'event':'db_error', 'type':type(e).__name__, 'pod':socket.gethostname()}))
        stop.wait(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop.clear()
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()
    yield
    stop.set()
    await asyncio.to_thread(thread.join, 5)

app = FastAPI(title='Shop Worker', lifespan=lifespan)

@app.get('/health', response_class=PlainTextResponse)
def health():
    return 'ok'

@app.get('/metrics')
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
