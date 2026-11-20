from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "幕灯 · AI 跑团主持台"


def show_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x10)
    except Exception:
        pass


def free_port(start: int = 8000, end: int = 8010) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"{start}-{end} 端口都被占用")


def wait_ready(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.8) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    port = free_port()
    log_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MudengTRPG"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher.log"

    try:
        import uvicorn
        from server import app

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name="trpg-server", daemon=True)
        thread.start()
        print(f"{APP_NAME} 正在启动，请稍候…", flush=True)
        if not wait_ready(port):
            raise RuntimeError("服务端在 30 秒内没有启动")
        print(f"已启动：http://127.0.0.1:{port}/", flush=True)
        try:
            import json
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/network", timeout=2) as response:
                network = json.loads(response.read().decode("utf-8"))
            for url in network.get("urls") or []:
                print(f"联机地址：{url}", flush=True)
        except Exception:
            pass
        print("关闭这个窗口即可停止跑团服务。", flush=True)
        webbrowser.open(f"http://127.0.0.1:{port}/")
        while thread.is_alive():
            time.sleep(0.5)
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "=" * 60 + "\n")
            handle.write(traceback.format_exc())
        show_error(f"启动失败：{exc}\n\n日志：{log_path}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
