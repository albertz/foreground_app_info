"""
App info
"""

from typing import Optional, Any, Dict
import os
import sys
import re

mydir = os.path.dirname(__file__)


def local_filename_from_url(filename: str) -> Optional[str]:
    """
    :param filename: a URL, which may be a file:// URL
    :return: the local filename if the URL is a file:// URL, otherwise None
    """
    if not filename.startswith("file://"):
        return None

    def removestart(s, t):
        return s[len(t) :] if s.startswith(t) else s

    filename = removestart(filename, "file://localhost")
    filename = removestart(filename, "file://")
    from urllib.parse import unquote

    return unquote(filename)


def get_app_info() -> Optional[Dict[str, Any]]:
    """
    Returns information about the current foreground application.

    :return: a dict with keys "appName", "windowTitle", "url", "idleTime" (in seconds), or None if failed to get info
    """
    if sys.platform == "darwin":
        return _get_app_info_mac()
    elif sys.platform == "win32":
        return _get_app_info_win32()
    else:
        raise Exception(f"missing support for your platform {sys.platform}")


def resolve_macos_container_path(localfn: str) -> str:
    """
    Resolves symlinks for macOS application containers (sandboxed apps).

    :param localfn: The local filename to resolve.
    :return: The resolved path.
    """
    m = re.match(r"(.*/Library/Containers/[^/]*/Data/[^/]*)(.*)", localfn)
    if m and os.path.islink(m.groups()[0]):
        return (
            os.path.normpath(os.path.join(os.path.dirname(m.groups()[0]), os.readlink(m.groups()[0]))) + m.groups()[1]
        )
    return localfn


def normalize_text(text: str) -> str:
    """
    Cleans up the text by stripping invisible characters like the Left-to-Right Mark (\\u200e)
    which is often present in localized application names (e.g., WhatsApp).
    """
    if not text:
        return ""
    # Strip LRM (\u200e) and whitespace
    return text.replace("\u200e", "").strip()


def _get_app_info_mac():
    try:
        from . import mac
    except ImportError:
        import mac
    appname, windowtitle = mac.get_frontmost_app_info()
    appname = normalize_text(appname)
    windowtitle = normalize_text(windowtitle)
    idletime = mac.get_idle_time()
    url = mac.get_app_url(appname, windowtitle)

    localfn = local_filename_from_url(url)
    if localfn is not None:
        url = "file://" + resolve_macos_container_path(localfn)
    return {"appName": appname, "windowTitle": windowtitle, "url": url, "idleTime": idletime}


def _get_app_info_win32():
    import win32gui

    # TODO: or maybe win32gui.GetFocus() ?
    hwnd = win32gui.GetForegroundWindow()

    # Request privileges to enable "debug process", so we can
    # later use PROCESS_VM_READ, retardedly required to
    # GetModuleFileNameEx()
    import win32security
    import win32con
    import win32process
    import win32api

    priv_flags = win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY
    hToken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), priv_flags)
    # enable "debug process"
    privilege_id = win32security.LookupPrivilegeValue(None, win32security.SE_DEBUG_NAME)
    win32security.AdjustTokenPrivileges(hToken, 0, [(privilege_id, win32security.SE_PRIVILEGE_ENABLED)])

    # Open the process, and query it's filename
    processid = win32process.GetWindowThreadProcessId(hwnd)
    pshandle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, processid[1])
    exename = win32process.GetModuleFileNameEx(pshandle, 0)

    # clean up
    win32api.CloseHandle(pshandle)
    win32api.CloseHandle(hToken)

    return {"appName": exename, "windowTitle": win32gui.GetWindowText(hwnd), "url": None, "idleTime": None}
