FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEM_MB=64 \
    WORKERS=1 \
    STEP_MB=8

WORKDIR /app

COPY main.py ./

USER 10001

CMD ["python", "-u", "main.py"]
