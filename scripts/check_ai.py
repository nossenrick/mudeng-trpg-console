r"""Minimal end-to-end check for the local AI proxy.

Usage:
    .\.venv\Scripts\python.exe scripts\check_ai.py
    .\.venv\Scripts\python.exe scripts\check_ai.py http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys

import httpx


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
    with httpx.Client(timeout=130.0, trust_env=False) as client:
        health = client.get(f"{base}/api/health")
        health.raise_for_status()
        print("health:", health.json())

        config = client.get(f"{base}/api/ai/config")
        config.raise_for_status()
        data = config.json()
        print("config:", {key: data.get(key) for key in ("endpoint", "model", "hasKey", "keyHint")})
        if not data.get("hasKey"):
            print("FAIL: server has no AI key. Set it in the UI or ai_config.json.")
            return 1

        response = client.post(
            f"{base}/api/ai/chat",
            json={
                "messages": [
                    {"role": "system", "content": "只返回 JSON。"},
                    {"role": "user", "content": '返回 {"ok": true}'},
                ],
                "jsonMode": True,
                "maxTokens": 400,
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = json.loads(payload.get("content", "{}"))
        print("chat:", {"elapsedMs": payload.get("elapsedMs"), "model": payload.get("model"), "content": content})
        if content.get("ok") is not True:
            print("FAIL: unexpected model output")
            return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
