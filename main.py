"""
天球可视化系统 - 桌面启动器（PyWebView + FastAPI）
自动选端口 / 等待就绪 / 异常可见 / 全屏启动
"""
import os
import sys
import socket
import threading
import time
import traceback

import uvicorn
import webview
from fastapi.staticfiles import StaticFiles


def get_resource_path(relative_path):
    """兼容开发环境与 PyInstaller 打包环境"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# backend 加入导入路径
_backend_dir = get_resource_path("backend")
if os.path.isdir(_backend_dir) and _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 导入 FastAPI 应用（backend/main.py）
try:
    from server import app as fastapi_app
except Exception:
    traceback.print_exc()
    input("❌ 后端导入失败，按回车退出...")
    sys.exit(1)

# 挂载前端静态文件
_frontend_dir = get_resource_path("frontend")
if os.path.isdir(_frontend_dir):
    fastapi_app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
    print(f"✅ 前端已挂载: {_frontend_dir}")
else:
    print(f"❌ 找不到前端目录: {_frontend_dir}")


def _port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_ready(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


_server_error = []


def _run_server(port):
    try:
        uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    except Exception:
        _server_error.append(traceback.format_exc())
        
# ===== 暴露给前端 JS 的原生能力 =====
class Api:
    def quit(self):
        """红色 ✕：强制结束整个程序"""
        os._exit(0)

    def toggle_fullscreen(self):
        """⛶：切换窗口全屏 / 还原"""
        try:
            webview.windows[0].toggle_fullscreen()
        except Exception:
            pass

def main():
    port = 8000
    while not _port_free(port) and port < 8100:   # 端口被占自动顺延
        port += 1
    print(f"🚀 正在启动本地服务器 (端口 {port}) ...")
    threading.Thread(target=_run_server, args=(port,), daemon=True).start()

    if not _wait_ready(port):
        print("❌ 服务器启动失败:")
        print(_server_error[0] if _server_error else "未知错误")
        input("按回车退出...")
        sys.exit(1)
    print("✅ 服务器就绪")

    webview.create_window(
        title='3D Celestial Sphere - AI Stargazing',
        url=f'http://127.0.0.1:{port}/index.html',
        fullscreen=True,
        resizable=True,
        text_select=True,
        js_api=Api(),          # ← 新增这一行
    )
    webview.start()
    print("👋 应用已关闭。")


if __name__ == '__main__':
    main()