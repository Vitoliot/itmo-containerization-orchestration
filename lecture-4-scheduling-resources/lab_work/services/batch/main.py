"""Batch / «ночная аналитика»: бесконечно жрёт CPU и память, ничего полезного не делает.

Параметры через env (потом прокинем из values.yaml):
  MEM_MB     — сколько MiB держать в памяти (по умолчанию 64)
  WORKERS    — число busy-loop потоков по CPU (по умолчанию 1)
  STEP_MB    — шаг донабора памяти, чтобы рост был плавным (по умолчанию 8)
"""

from __future__ import annotations

import os
import threading
import time


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return max(0, int(raw))


def burn_cpu() -> None:
    """Глупый busy-loop: крутит CPU без sleep."""
    x = 0
    while True:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        _ = x * x


def hold_memory(target_mb: int, step_mb: int) -> None:
    """Набирает и удерживает ~target_mb MiB (байты в list, чтобы GC не съел)."""
    chunks: list[bytearray] = []
    held = 0
    step = max(1, step_mb) * 1024 * 1024
    target = target_mb * 1024 * 1024

    print(f"batch: growing memory toward {target_mb} MiB (step {step_mb} MiB)", flush=True)
    while held < target:
        size = min(step, target - held)
        chunks.append(bytearray(size))
        held += size
        print(f"batch: held ~{held // (1024 * 1024)} MiB", flush=True)
        time.sleep(0.2)

    print(f"batch: holding {held // (1024 * 1024)} MiB, CPU burn continues", flush=True)
    # Держим ссылку на chunks, чтобы память не освободилась
    while True:
        time.sleep(60)
        _ = len(chunks)


def main() -> None:
    mem_mb = _env_int("MEM_MB", 64)
    workers = max(1, _env_int("WORKERS", 1))
    step_mb = max(1, _env_int("STEP_MB", 8))

    print(f"batch: start MEM_MB={mem_mb} WORKERS={workers} STEP_MB={step_mb}", flush=True)

    for i in range(workers):
        t = threading.Thread(target=burn_cpu, name=f"cpu-{i}", daemon=True)
        t.start()

    hold_memory(mem_mb, step_mb)


if __name__ == "__main__":
    main()
