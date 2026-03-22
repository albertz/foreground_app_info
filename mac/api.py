import AppKit
import Quartz
import ApplicationServices
from typing import Tuple
from .handlers import HANDLERS
from Foundation import NSRunLoop, NSDate


def get_frontmost_app_info() -> Tuple[str, str]:
    """
    Retrieves the name and window title of the frontmost application.

    :return: A tuple (app_name, window_title).
    """
    # Tick run loop to allow NSWorkspace to update
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

    # Get window list using Quartz Window Services to find frontmost PID
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

    pid = -1
    window_title = ""
    if window_list:
        for window in window_list:
            if window.get("kCGWindowLayer") == 0:
                pid = window.get("kCGWindowOwnerPID")
                window_title = window.get("kCGWindowName", "")
                if pid is not None:
                    break

    workspace = AppKit.NSWorkspace.sharedWorkspace()
    app_name = ""
    if pid != -1:
        for app in workspace.runningApplications():
            if app.processIdentifier() == pid:
                app_name = app.localizedName()
                break
        if not app_name:
            app_name = f"PID {pid}"
    else:
        # Fallback to NSWorkspace
        front_app = workspace.frontmostApplication()
        if front_app:
            app_name = front_app.localizedName()
            pid = front_app.processIdentifier()
        else:
            active_app = workspace.activeApplication()
            if active_app:
                app_name = active_app.get("NSApplicationName", "")
                pid = active_app.get("NSApplicationProcessIdentifier", -1)

    if not app_name:
        return "", ""

    # If Quartz didn't give a title, try Accessibility API as fallback
    if not window_title and pid != -1:
        app_ref = ApplicationServices.AXUIElementCreateApplication(pid)
        if app_ref:
            error, focused_window = ApplicationServices.AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
            if error == 0 and focused_window:
                error, title = ApplicationServices.AXUIElementCopyAttributeValue(focused_window, "AXTitle", None)
                if error == 0 and title:
                    window_title = str(title)

    return app_name, window_title


def get_idle_time() -> float:
    """
    Returns the system idle time in seconds.

    :return: Idle time in seconds.
    """
    return Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType
    )


def get_app_url(app_name: str, window_title: str) -> str:
    """
    Attempts to retrieve a URL or file path associated with the given application.

    :param app_name: The name of the application.
    :param window_title: The current window title.
    :return: The URL or path as a string, or an empty string if not found.
    """
    handler = HANDLERS.get(app_name)
    if handler:
        res = handler()
        if res:
            return res

    # Generic fallback using Accessibility API (AXDocument)
    workspace = AppKit.NSWorkspace.sharedWorkspace()
    front_app = workspace.frontmostApplication()
    if front_app:
        app_ref = ApplicationServices.AXUIElementCreateApplication(front_app.processIdentifier())
        if app_ref:
            error, focused_window = ApplicationServices.AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)
            if error == 0 and focused_window:
                error, url = ApplicationServices.AXUIElementCopyAttributeValue(focused_window, "AXDocument", None)
                if error == 0 and url:
                    return str(url)

    return ""
