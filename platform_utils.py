"""跨平台小工具：打开文件夹、选字体、判断拖放可用性。"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

UI_FONT_CANDIDATES = {
    "win32": ("Microsoft YaHei",),
    "darwin": ("PingFang SC", "Hiragino Sans GB"),
    "linux": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "DejaVu Sans"),
}


def ui_font() -> str:
    """Tk 用的界面字体族名。"""
    key = "win32" if IS_WIN else ("darwin" if IS_MAC else "linux")
    return UI_FONT_CANDIDATES.get(key, ("TkDefaultFont",))[0]


def open_path(path) -> None:
    """在文件管理器里打开目录（失败不抛异常）。"""
    path = str(path)
    try:
        if IS_WIN:
            os.startfile(path)  # noqa: S606
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def has_dragdrop() -> bool:
    try:
        import tkinterdnd2  # noqa: F401
        return True
    except Exception:
        return False
