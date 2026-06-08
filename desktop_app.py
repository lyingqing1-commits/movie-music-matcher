"""
桌面应用启动器 - 将 Movie Music Matcher 变成原生桌面窗口
==========================================================
双击 run.bat 启动，或运行: python desktop_app.py
"""
import sys
import os
import threading
import webview

# 确保能找到项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as flask_app


def start_flask():
    """在后台线程启动 Flask 服务器"""
    flask_app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


def main():
    # 启动 Flask 后台线程
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # 创建原生桌面窗口
    window = webview.create_window(
        title="Movie Music Matcher - 电影音乐智能匹配",
        url="http://localhost:5000",
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 500),
    )

    # 启动桌面窗口（会阻塞直到窗口关闭）
    webview.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
