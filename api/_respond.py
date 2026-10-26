"""Shared JSON-response helper for the plain-stdlib Vercel Python functions in api/."""

import json


def respond(handler, status: int, payload: dict, headers: dict | None = None) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)
