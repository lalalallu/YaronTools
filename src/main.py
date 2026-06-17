#!/usr/bin/env python3
"""
YaronTools - 统一图形化管理工具入口
集成: 文件浏览、配置编辑、PCD编辑 三大功能模块
"""
import sys
import os

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from ui.main_window import UnifiedMainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YaronTools")
    app.setApplicationVersion("2.0.0")
    app.setStyle("Fusion")

    window = UnifiedMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
