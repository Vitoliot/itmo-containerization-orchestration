from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


PORT = int(os.getenv("PORT", "8080"))


def write_log(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


class Handler(BaseHTTPRequestHandler):
    def send_text(
        self,
        status_code: int,
        body: str,
    ) -> None:
        data = body.encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()

        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_text(200, "ok")
            return

        self.send_text(404, "not found")

    def do_POST(self) -> None:
        if self.path != "/alerts":
            self.send_text(404, "not found")
            return

        content_length = int(
            self.headers.get("Content-Length", "0")
        )

        raw_body = self.rfile.read(content_length)

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            write_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "invalid_alertmanager_payload",
                    "body": raw_body.decode("utf-8", errors="replace"),
                }
            )

            self.send_text(400, "invalid json")
            return

        alerts = body.get("alerts", [])

        write_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "alertmanager_webhook",
                "status": body.get("status"),
                "receiver": body.get("receiver"),
                "alerts_count": len(alerts),
                "group_labels": body.get("groupLabels"),
            }
        )

        for alert in alerts:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            write_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "alert",
                    "status": alert.get("status"),
                    "alertname": labels.get("alertname"),
                    "severity": labels.get("severity"),
                    "service": labels.get("service"),
                    "summary": annotations.get("summary"),
                    "description": annotations.get("description"),
                    "starts_at": alert.get("startsAt"),
                    "ends_at": alert.get("endsAt"),
                    "labels": labels,
                }
            )

        self.send_text(200, "ok")

    def log_message(
        self,
        format: str,
        *args: Any,
    ) -> None:
        # Не пишем стандартные access-логи http.server.
        pass


def main() -> None:
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler,
    )

    write_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "server_started",
            "port": PORT,
        }
    )

    server.serve_forever()


if __name__ == "__main__":
    main()