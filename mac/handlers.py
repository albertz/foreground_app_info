import glob
import json
import os
import subprocess
from typing import Any, Optional

import AppKit
import ScriptingBridge


def is_app_running(bundle_id: str) -> bool:
    """
    Checks if an application with the given bundle identifier is currently running.

    :param bundle_id: The application bundle identifier (e.g., "com.google.Chrome").
    :return: True if the app is running, False otherwise.
    """
    apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
    return any(app.bundleIdentifier() == bundle_id for app in apps)


def get_running_app(bundle_id: str) -> Optional[Any]:
    """
    Retrieves the ScriptingBridge application object for a running application.

    :param bundle_id: The application bundle identifier.
    :return: The SBApplication object if the app is running, otherwise None.
    """
    if not is_app_running(bundle_id):
        return None
    return ScriptingBridge.SBApplication.applicationWithBundleIdentifier_(bundle_id)


def get_chrome_url() -> Optional[str]:
    """
    Retrieves the URL of the active tab in the frontmost Google Chrome window.

    :return: The URL as a string, or None if not found or Chrome is not running.
    """
    chrome = get_running_app("com.google.Chrome")
    if chrome and chrome.windows():
        front_window = chrome.windows()[0]
        active_tab = front_window.activeTab()
        if active_tab:
            return active_tab.URL()
    return None


def get_safari_url() -> Optional[str]:
    """
    Retrieves the URL of the current tab in the frontmost Safari window.

    :return: The URL as a string, or None if not found or Safari is not running.
    """
    safari = get_running_app("com.apple.Safari")
    if safari and safari.windows():
        front_window = safari.windows()[0]
        current_tab = front_window.currentTab()
        if current_tab:
            return current_tab.URL()
    return None


def get_firefox_url() -> Optional[str]:
    """
    Retrieves the URL of the active tab in Firefox by reading its session store.

    :return: The URL as a string, or None if not found.
    """
    try:
        sessionfns = []
        profile_path = os.path.expanduser("~") + "/Library/Application Support/Firefox/Profiles/*"
        for sessionfn in glob.glob(profile_path + "/sessionstore.js"):
            sessionfns += [(os.stat(sessionfn).st_mtime, sessionfn)]
        for sessionfn in glob.glob(profile_path + "/sessionstore-backups/recovery.jsonlz4"):
            sessionfns += [(os.stat(sessionfn).st_mtime, sessionfn)]

        if not sessionfns:
            return None

        sessionfn = max(sessionfns)[1]
        if sessionfn.endswith(".jsonlz4"):
            return None

        with open(sessionfn, "r") as f:
            content = f.read()
            try:
                s = json.loads(content)
            except json.JSONDecodeError:
                s = eval(content, {"false": False, "true": True, "null": None})

        selectedWindow = s.get("selectedWindow", 1)
        windows = s.get("windows", [])
        if not windows or selectedWindow > len(windows):
            return None

        w = windows[selectedWindow - 1]
        selectedTab = w.get("selected", 1)
        tabs = w.get("tabs", [])
        if not tabs or selectedTab > len(tabs):
            return None

        t = tabs[selectedTab - 1]
        entries = t.get("entries", [])
        if not entries:
            return None

        return entries[-1].get("url")
    except Exception:
        raise


def get_finder_url() -> Optional[str]:
    """
    Retrieves the path of the frontmost Finder window as a file URL.

    :return: The file URL as a string, or None if not found or Finder is not running.
    """
    finder = get_running_app("com.apple.Finder")
    if finder and finder.windows():
        front_window = finder.windows()[0]
        target = front_window.target()
        if target:
            return str(target.URL())
    return None


def get_terminal_url() -> Optional[str]:
    """
    Retrieves the current working directory of the frontmost Terminal tab as a file URL.

    :return: The file URL as a string, or None if not found or Terminal is not running.
    """
    terminal = get_running_app("com.apple.Terminal")
    if terminal and terminal.windows():
        front_window = terminal.windows()[0]
        selected_tab = front_window.selectedTab()
        tty = selected_tab.tty()
        res = subprocess.check_output(["fuser", tty], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        pids = res.split()
        if pids:
            pid = pids[0]
            cwd = subprocess.check_output(
                ["lsof", "-a", "-p", pid, "-d", "cwd", "-n", "-Fn"], stderr=subprocess.DEVNULL
            ).decode("utf-8")
            for line in cwd.splitlines():
                if line.startswith("n"):
                    return "file://" + line[1:]
    return None


def get_xcode_url() -> Optional[str]:
    """
    Retrieves the file URL of the frontmost Xcode document.

    :return: The file URL as a string, or None if not found or Xcode is not running.
    """
    xcode = get_running_app("com.apple.dt.Xcode")
    if xcode and xcode.windows():
        if xcode.documents():
            doc = xcode.documents()[0]
            if hasattr(doc, "file"):
                return "file://" + str(doc.file())
    return None


def get_camino_url() -> Optional[str]:
    """
    Retrieves the URL of the current tab in the frontmost Camino browser window.

    :return: The URL as a string, or None if not found or Camino is not running.
    """
    camino = get_running_app("org.mozilla.camino")
    if camino and camino.browserWindows():
        return camino.browserWindows()[0].currentTab().URL()
    return None


HANDLERS = {
    "Google Chrome": get_chrome_url,
    "Safari": get_safari_url,
    "Firefox": get_firefox_url,
    "Finder": get_finder_url,
    "Terminal": get_terminal_url,
    "Xcode": get_xcode_url,
    "Camino": get_camino_url,
}
