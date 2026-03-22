import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, List, Optional

import AppKit
import ScriptingBridge
import lz4.block


def _get_actual_bundle_id(bundle_id: str) -> Optional[str]:
    """
    Finds the actual bundle identifier of a running application case-insensitively.
    """
    apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
    return next(
        (app.bundleIdentifier() for app in apps 
         if app.bundleIdentifier() and app.bundleIdentifier().lower() == bundle_id.lower()), 
        None
    )


def is_app_running(bundle_id: str) -> bool:
    """
    Checks if an application with the given bundle identifier is currently running.

    :param bundle_id: The application bundle identifier (e.g., "com.google.Chrome").
    :return: True if the app is running, False otherwise.
    """
    return _get_actual_bundle_id(bundle_id) is not None


def get_running_app(bundle_id: str) -> Optional[Any]:
    """
    Retrieves the ScriptingBridge application object for a running application.

    :param bundle_id: The application bundle identifier.
    :return: The SBApplication object if the app is running, otherwise None.
    """
    actual_bundle_id = _get_actual_bundle_id(bundle_id)
    if not actual_bundle_id:
        return None
    return ScriptingBridge.SBApplication.applicationWithBundleIdentifier_(actual_bundle_id)


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


def get_firefox_url(app_name: str, window_title: str) -> Optional[str]:
    """
    Retrieves the URL of the active tab in Firefox by reading its session store
    and matching the window title.

    :param app_name: The name of the application.
    :param window_title: The current window title.
    :return: The URL as a string, or None if not found.
    """
    sessionfns = []
    profile_path = os.path.expanduser("~") + "/Library/Application Support/Firefox/Profiles/*"
    # Modern Firefox uses .jsonlz4, older used .js
    patterns = [
        "/sessionstore.js",
        "/sessionstore.jsonlz4",
        "/sessionstore-backups/recovery.jsonlz4",
        "/sessionstore-backups/recovery.js",
    ]
    for pattern in patterns:
        for sessionfn in glob.glob(profile_path + pattern):
            sessionfns += [(os.stat(sessionfn).st_mtime, sessionfn)]

    if not sessionfns:
        return None

    # Take the most recently modified session store
    sessionfn = max(sessionfns)[1]

    if sessionfn.endswith(".jsonlz4"):
        with open(sessionfn, "rb") as f:
            header = f.read(8)
            if header != b"mozLz40\0":
                return None
            uncompressed_size = int.from_bytes(f.read(4), byteorder="little")
            compressed_data = f.read()
            content = lz4.block.decompress(compressed_data, uncompressed_size=uncompressed_size)
            s = json.loads(content)
    else:
        with open(sessionfn, "r") as f:
            content = f.read()
            try:
                s = json.loads(content)
            except json.JSONDecodeError:
                # Very old Firefox used a format that was sometimes valid Python but not JSON
                s = eval(content, {"false": False, "true": True, "null": None})

    # Try to find a tab matching the window title
    # Firefox window title is usually just the tab title
    best_tab = None
    latest_timestamp = -1

    for w in s.get("windows", []):
        for t in w.get("tabs", []):
            entries = t.get("entries", [])
            if not entries:
                continue
            
            tab_title = entries[-1].get("title")
            timestamp = t.get("lastAccessed", 0)
            
            # Match by title if possible
            if tab_title and tab_title == window_title:
                # Found exact match
                return entries[-1].get("url")
            
            # Keep track of latest tab as fallback
            if timestamp > latest_timestamp:
                latest_timestamp = timestamp
                best_tab = t

    if best_tab:
        entries = best_tab.get("entries", [])
        if entries:
            return entries[-1].get("url")

    return None


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


def _get_cwd_from_tty(tty: str) -> Optional[str]:
    """
    Retrieves the current working directory of the process using the given TTY.
    """
    if not tty:
        return None
    # fuser returns non-zero if no process is found, which is expected
    res = subprocess.run(["fuser", tty], capture_output=True, text=True, check=False).stdout.strip()
    pids = res.split()
    if pids:
        pid = pids[0]
        # lsof might also fail if process just exited
        res = subprocess.run(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-n", "-Fn"], capture_output=True, text=True, check=False
        ).stdout
        for line in res.splitlines():
            if line.startswith("n"):
                return "file://" + line[1:]
    return None


def get_terminal_url() -> Optional[str]:
    """
    Retrieves the current working directory of the frontmost Terminal tab as a file URL.

    :return: The file URL as a string, or None if not found or Terminal is not running.
    """
    terminal = get_running_app("com.apple.Terminal")
    if not terminal or not terminal.windows():
        return None

    front_window = terminal.windows()[0]
    selected_tab = front_window.selectedTab()
    return _get_cwd_from_tty(selected_tab.tty())


def get_iterm_url() -> Optional[str]:
    """
    Retrieves the current working directory of the frontmost iTerm2 session as a file URL.

    :return: The file URL as a string, or None if not found or iTerm2 is not running.
    """
    iterm = get_running_app("com.googlecode.iterm2")
    if not iterm:
        return None

    win = iterm.currentWindow()
    if not win:
        return None
    
    session = win.currentSession()
    if not session:
        return None
        
    return _get_cwd_from_tty(session.tty())


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


def get_jetbrains_url(app_name: str, window_title: str) -> Optional[str]:
    """
    Retrieves the file URL for a JetBrains IDE (PyCharm, IntelliJ, etc.) by parsing its window title
    and matching it against recent projects.

    :param app_name: The name of the application.
    :param window_title: The current window title.
    :return: The file URL as a string, or None if not found.
    """
    # Separator can be " – " (en dash), " — " (em dash), or " - " (hyphen)
    parts = re.split(r" [–—-] ", window_title, 1)
    if len(parts) < 2:
        return None

    project_name = parts[0].strip()
    file_part = parts[1].strip()

    # Sometimes the title has [ProjectName] at the end
    if " [" in file_part:
        file_part = file_part.split(" [")[0].strip()

    path = None
    if file_part.startswith("/") or file_part.startswith("~"):
        path = os.path.expanduser(file_part)
    else:
        # Use recentProjects.xml trick
        jetbrains_dir = os.path.expanduser("~/Library/Application Support/JetBrains")
        # Find the most recent recentProjects.xml across all JetBrains products
        recent_projects_files = glob.glob(os.path.join(jetbrains_dir, "*", "options", "recentProjects.xml"))
        
        # Sort by mtime to check newest first
        recent_projects_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

        for recent_projects_file in recent_projects_files:
            if not os.path.isfile(recent_projects_file):
                continue
            tree = ET.parse(recent_projects_file)
            root = tree.getroot()
            for entry in root.findall(".//entry"):
                key = entry.get("key")
                if not key:
                    continue

                # Check if it's the opened project
                value = entry.find("value")
                if value is not None:
                    meta = value.find("RecentProjectMetaInfo")
                    if meta is not None and meta.get("opened") == "true":
                        project_path = key.replace("$USER_HOME$", os.path.expanduser("~"))
                        if os.path.basename(project_path) == project_name:
                            # Found the project path
                            # Try to find the actual file by appending file_part
                            potential_path = os.path.join(project_path, file_part)
                            if os.path.exists(potential_path):
                                path = potential_path
                                break
                            
                            # If file_part is a path relative to project
                            # (JetBrains sometimes shows it like that)
                            potential_path = os.path.join(project_path, *file_part.split("/"))
                            if os.path.exists(potential_path):
                                path = potential_path
                                break
                            
                            # Fallback: search for the filename in the project directory
                            filename_only = os.path.basename(file_part)
                            for root_dir, _, files in os.walk(project_path):
                                if filename_only in files:
                                    path = os.path.join(root_dir, filename_only)
                                    break
                            
                            if not path:
                                path = project_path
                            break
            if path:
                break

    if path:
        return "file://" + path
    return None


def get_zotero_url(app_name: str, window_title: str) -> Optional[str]:
    """
    Retrieves the file URL for a Zotero item by matching the window title against the database.

    :param app_name: The name of the application.
    :param window_title: The current window title.
    :return: The file URL as a string, or None if not found.
    """
    if not window_title.endswith(" - Zotero"):
        return None

    title_part = window_title[:-9]
    zotero_db = os.path.expanduser("~/Zotero/zotero.sqlite")
    if not os.path.exists(zotero_db):
        return None

    result = None
    # Connect to a copy of the database to avoid locking issues
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        shutil.copy2(zotero_db, tmp_name)
        conn = sqlite3.connect(tmp_name)
        cur = conn.cursor()

        # Search for any item whose title matches the window title part
        query = """
        SELECT i.itemID, idv.value
        FROM items i
        JOIN itemData id ON i.itemID = id.itemID
        JOIN fields f ON id.fieldID = f.fieldID
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE f.fieldName = 'title'
        """
        cur.execute(query)
        all_items = cur.fetchall()

        matching_item_id = None
        for item_id, item_title in all_items:
            if item_title and (item_title in title_part or title_part in item_title):
                matching_item_id = item_id
                break

        if matching_item_id:
            # Check for DOI or URL first
            query = """
            SELECT f.fieldName, idv.value
            FROM itemData id
            JOIN fields f ON id.fieldID = f.fieldID
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            WHERE id.itemID = ? AND f.fieldName IN ('DOI', 'url')
            """
            cur.execute(query, (matching_item_id,))
            fields = dict(cur.fetchall())
            
            if "DOI" in fields and fields["DOI"]:
                doi = fields["DOI"]
                if doi.startswith("http"):
                    result = doi
                else:
                    result = f"https://doi.org/{doi}"
            
            if not result and "url" in fields and fields["url"]:
                result = fields["url"]

            if not result:
                # Fallback to local PDF attachment
                query = """
                SELECT i.key, ia.path
                FROM items i
                JOIN itemAttachments ia ON i.itemID = ia.itemID
                WHERE ia.parentItemID = ? AND ia.contentType = 'application/pdf'
                """
                cur.execute(query, (matching_item_id,))
                attachment = cur.fetchone()
                if attachment:
                    key, path = attachment
                    if path and path.startswith("storage:"):
                        filename = path[len("storage:"):]
                        result = "file://" + os.path.expanduser(f"~/Zotero/storage/{key}/{filename}")
                    elif path:
                        result = "file://" + os.path.expanduser(path)
        
        if not result:
            # Fallback: search in attachments if item not found by title
            query = "SELECT i.key, ia.path FROM items i JOIN itemAttachments ia ON i.itemID = ia.itemID"
            cur.execute(query)
            all_attachments = cur.fetchall()
            for key, path in all_attachments:
                if path and path.endswith(".pdf"):
                    clean_path = path[len("storage:"):] if path.startswith("storage:") else path
                    if clean_path in title_part:
                        result = "file://" + os.path.expanduser(f"~/Zotero/storage/{key}/{clean_path}")
                        break
        conn.close()
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

    return result


def get_slack_url() -> Optional[str]:
    """
    Retrieves the URL of the current Slack channel from the AXWebArea element.

    :return: The URL as a string, or None if not found or Slack is not running.
    """
    import ApplicationServices

    if not is_app_running("com.tinyspeck.slackmacgap"):
        return None

    # Slack is an Electron app, it often exposes the URL in an AXWebArea element
    # We need to find it recursively in the focused window
    workspace = AppKit.NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == "com.tinyspeck.slackmacgap":
            pid = app.processIdentifier()
            app_ref = ApplicationServices.AXUIElementCreateApplication(pid)
            error, window = ApplicationServices.AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
            if error == 0:
                return _find_ax_web_area_url(window)
    return None


def _find_ax_web_area_url(element, depth=0, max_depth=15) -> Optional[str]:
    if depth > max_depth:
        return None

    import ApplicationServices

    error, role = ApplicationServices.AXUIElementCopyAttributeValue(element, "AXRole", None)
    if error == 0 and role == "AXWebArea":
        error, url = ApplicationServices.AXUIElementCopyAttributeValue(element, "AXURL", None)
        if error == 0 and url:
            return str(url)

    error, children = ApplicationServices.AXUIElementCopyAttributeValue(element, "AXChildren", None)
    if error == 0 and children:
        for child in children:
            res = _find_ax_web_area_url(child, depth + 1, max_depth)
            if res:
                return res
    return None


def get_spotify_url() -> Optional[str]:
    """
    Retrieves the URI of the current track in Spotify using ScriptingBridge.

    :return: The Spotify URI as a string (e.g., spotify:track:...), or None if not found or Spotify is not running.
    """
    spotify = get_running_app("com.spotify.client")
    if not spotify:
        return None

    current_track = spotify.currentTrack()
    if not current_track:
        return None
        
    return current_track.spotifyUrl()


def get_steam_url() -> Optional[str]:
    """
    Retrieves the current Steam URL by querying its internal Chromium history database.

    :return: The latest URL from Steam's history, or None if not found or no recent activity.
    """
    import ApplicationServices

    helper_bundle = "com.valvesoftware.steam.helper"
    if not is_app_running(helper_bundle):
        return None

    # Only query history if a Steam window is actually focused
    workspace = AppKit.NSWorkspace.sharedWorkspace()
    steam_focused = False
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == helper_bundle:
            pid = app.processIdentifier()
            app_ref = ApplicationServices.AXUIElementCreateApplication(pid)
            error, window = ApplicationServices.AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
            if error == 0 and window:
                steam_focused = True
                break
    
    if not steam_focused:
        return None

    history_db = os.path.expanduser("~/Library/Application Support/Steam/config/htmlcache/Default/History")
    if not os.path.exists(history_db):
        return None

    # Connect to a copy of the database to avoid locking issues
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_name = tmp.name
    
    result = None
    try:
        shutil.copy2(history_db, tmp_name)
        conn = sqlite3.connect(tmp_name)
        cur = conn.cursor()
        # Chromium uses WebKit/Google Chrome style history
        query = "SELECT url FROM urls ORDER BY last_visit_time DESC LIMIT 1"
        cur.execute(query)
        row = cur.fetchone()
        if row:
            result = row[0]
        conn.close()
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

    return result


def get_kitty_url(app_name: str, window_title: str) -> Optional[str]:
    """
    Retrieves the current working directory of the frontmost Kitty window.

    :param app_name: The name of the application.
    :param window_title: The current window title.
    :return: The file URL as a string, or None if not found.
    """
    bundle_id = "net.kovidgoyal.kitty"
    if not is_app_running(bundle_id):
        return None

    # Kitty is not scriptable, so we find its child shell processes.
    workspace = AppKit.NSWorkspace.sharedWorkspace()
    kitty_pid = None
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == bundle_id:
            kitty_pid = app.processIdentifier()
            break
    
    if not kitty_pid:
        return None

    def _get_all_children_recursive(pid: int) -> List[int]:
        res = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False).stdout
        pids = []
        for p in res.splitlines():
            p = p.strip()
            if p.isdigit():
                pids.append(int(p))
        
        all_pids = list(pids)
        for p in pids:
            all_pids.extend(_get_all_children_recursive(p))
        return all_pids

    child_pids = _get_all_children_recursive(kitty_pid)
    for pid in child_pids:
        # Check if this process is a shell
        comm = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, check=False).stdout.strip()
        if not comm:
            continue
        if any(shell in comm.lower() for shell in ["fish", "zsh", "bash", "sh"]):
            # Get CWD of this shell
            res = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-n", "-Fn"], capture_output=True, text=True, check=False).stdout
            for line in res.splitlines():
                if line.startswith("n"):
                    cwd = line[1:]
                    # Basic title matching: if window title is a suffix of CWD or vice versa
                    # or if title is '~' and CWD is home
                    if window_title == "~" and cwd == os.path.expanduser("~"):
                        return "file://" + cwd
                    if window_title in cwd or cwd in window_title:
                        return "file://" + cwd
                    # Fallback: just return the first shell CWD found
                    return "file://" + cwd

    return None


HANDLERS = {
    "Google Chrome": get_chrome_url,
    "Safari": get_safari_url,
    "Firefox": get_firefox_url,
    "Finder": get_finder_url,
    "Terminal": get_terminal_url,
    "iTerm": get_iterm_url,
    "iTerm2": get_iterm_url,
    "Xcode": get_xcode_url,
    "Camino": get_camino_url,
    "PyCharm": get_jetbrains_url,
    "IntelliJ IDEA": get_jetbrains_url,
    "WebStorm": get_jetbrains_url,
    "CLion": get_jetbrains_url,
    "PHPStorm": get_jetbrains_url,
    "GoLand": get_jetbrains_url,
    "RubyMine": get_jetbrains_url,
    "AppCode": get_jetbrains_url,
    "DataGrip": get_jetbrains_url,
    "Rider": get_jetbrains_url,
    "Android Studio": get_jetbrains_url,
    "Zotero": get_zotero_url,
    "zotero": get_zotero_url,
    "Slack": get_slack_url,
    "Spotify": get_spotify_url,
    "Steam": get_steam_url,
    "kitty": get_kitty_url,
    "Kitty": get_kitty_url,
}
