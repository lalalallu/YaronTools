"""
Windows 原生工具函数 - 文件名清洗、长路径、去重、文件定位与通知
"""
import os
import subprocess
import sys

_INVALID_CHARS = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *[f"COM{i}" for i in range(1, 10)],
    *[f"LPT{i}" for i in range(1, 10)],
}


def sanitize_filename(name: str) -> str:
    """清洗文件名：替换 Windows 非法字符、处理保留名与结尾点/空格"""
    cleaned = "".join("_" if ch in _INVALID_CHARS or ord(ch) < 32 else ch for ch in name)
    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        cleaned = "file"
    stem = cleaned.split(".")[0]
    if stem.upper() in _RESERVED_NAMES:
        cleaned = "_" + cleaned
    return cleaned


def to_long_path(path: str) -> str:
    """长路径支持：路径超过传统上限时为绝对路径添加 \\\\?\\ 前缀（含 UNC 处理）"""
    if not os.path.isabs(path):
        return path
    if len(path) >= 248 or len(os.path.dirname(path)) >= 248:
        abspath = os.path.abspath(path)
        if abspath.startswith("\\\\?\\"):
            return abspath
        if abspath.startswith("\\\\"):
            return "\\\\?\\UNC\\" + abspath[2:]
        return "\\\\?\\" + abspath
    return path


def unique_path(path: str) -> str:
    """路径已存在时在扩展名前追加 (n) 后缀，返回不冲突的路径"""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{root} ({counter}){ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def open_path(path: str):
    """使用系统默认程序打开文件"""
    os.startfile(os.path.abspath(path))


def show_in_explorer(path: str):
    """在资源管理器中定位文件"""
    subprocess.run(["explorer", "/select,", os.path.abspath(path)])


def send_toast(title: str, msg: str):
    """发送 Windows Toast 通知（失败静默，不影响下载流程）"""
    try:
        from winotify import Notification
        toast = Notification(app_id="YaronTools", title=title, msg=msg, icon=sys.executable)
        toast.show()
    except Exception:
        pass


class TaskbarProgress:
    """Windows 任务栏进度条封装（基于 comtypes 驱动 ITaskbarList3）"""

    TBPF_NOPROGRESS = 0
    TBPF_NORMAL = 0x2

    def __init__(self, hwnd: int):
        """
        初始化任务栏进度

        Args:
            hwnd: 主窗口原生句柄
        """
        self._hwnd = int(hwnd)
        self._taskbar = None
        try:
            from ctypes import c_ulonglong, c_void_p, c_int
            from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
            from comtypes.client import CreateObject

            class _ITaskbarList3(IUnknown):
                _iid_ = GUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
                _methods_ = [
                    COMMETHOD([], HRESULT, "HrInit"),
                    COMMETHOD([], HRESULT, "AddTab", (["in"], c_void_p, "hwnd")),
                    COMMETHOD([], HRESULT, "DeleteTab", (["in"], c_void_p, "hwnd")),
                    COMMETHOD([], HRESULT, "ActivateTab", (["in"], c_void_p, "hwnd")),
                    COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], c_void_p, "hwnd")),
                    COMMETHOD([], HRESULT, "SetProgressValue",
                              (["in"], c_void_p, "hwnd"),
                              (["in"], c_ulonglong, "ullCompleted"),
                              (["in"], c_ulonglong, "ullTotal")),
                    COMMETHOD([], HRESULT, "SetProgressState",
                              (["in"], c_void_p, "hwnd"),
                              (["in"], c_int, "tbpFlags")),
                ]

            _CLSID_TaskbarList = GUID("{56FDF344-FD6D-11D0-958A-006097C9A090}")
            self._taskbar = CreateObject(_CLSID_TaskbarList, interface=_ITaskbarList3)
            self._taskbar.HrInit()
        except Exception:
            self._taskbar = None

    def is_available(self) -> bool:
        """任务栏进度是否可用"""
        return self._taskbar is not None

    def set_value(self, value: int):
        """更新进度（0-100），正常状态"""
        if self._taskbar is None:
            return
        try:
            self._taskbar.SetProgressValue(self._hwnd, int(value), 100)
            self._taskbar.SetProgressState(self._hwnd, self.TBPF_NORMAL)
        except Exception:
            pass

    def hide(self):
        """清除任务栏进度显示"""
        if self._taskbar is None:
            return
        try:
            self._taskbar.SetProgressState(self._hwnd, self.TBPF_NOPROGRESS)
        except Exception:
            pass
