"""PyInstaller 入口：把本地引擎打成 Windows EXE。

双击无参数运行时，启动本地 Web 界面并打开浏览器；
DSH 插件带 ``serve --port 8899`` 参数启动时，只起服务，不抢浏览器。
"""
from __future__ import annotations

import threading
import webbrowser

from litradar.cli import main as cli_main
from litradar.web import serve


def _open_browser_later(port: int) -> None:
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()


def main() -> None:
    import sys

    if len(sys.argv) == 1:
        _open_browser_later(8899)
        serve(port=8899)
        return
    cli_main()


if __name__ == "__main__":
    main()
