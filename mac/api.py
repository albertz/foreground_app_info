import AppKit
import Quartz
import ApplicationServices
from typing import Tuple
from .handlers import HANDLERS
from Foundation import NSRunLoop, NSDate


def _suppress_dock_icon():
    """
    Suppresses the Python application icon in the dock for CLI scripts.
    """
    # Check if we are in a generic python process
    bundle = AppKit.NSBundle.mainBundle()
    info = bundle.infoDictionary()
    if info:
        bundle_id = info.get("CFBundleIdentifier")
        if not bundle_id or bundle_id.startswith("org.python."):
            # User suggestion: set LSUIElement to "1" in infoDictionary before sharedApplication()
            info["LSUIElement"] = "1"
            app = AppKit.NSApplication.sharedApplication()
            # NSApplicationActivationPolicyAccessory = 1
            app.setActivationPolicy_(1)


_suppress_dock_icon()


def get_frontmost_app_info() -> Tuple[str, str]:
    """
    Retrieves the name and window title of the frontmost application.

    :return: A tuple (app_name, window_title).
    """
    # Tick run loop to allow NSWorkspace to update
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

    workspace = AppKit.NSWorkspace.sharedWorkspace()
    front_app = workspace.frontmostApplication()
    if not front_app:
        active_app = workspace.activeApplication()
        if active_app:
            app_name = active_app.get("NSApplicationName", "")
            pid = active_app.get("NSApplicationProcessIdentifier", -1)
        else:
            return "", ""
    else:
        app_name = front_app.localizedName()
        pid = front_app.processIdentifier()

    # Get window title using Quartz Window Services for this specific PID
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

    window_title = ""
    if window_list:
        for window in window_list:
            if window.get("kCGWindowLayer") == 0 and window.get("kCGWindowOwnerPID") == pid:
                window_title = window.get("kCGWindowName", "")
                if window_title:
                    break

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
        import inspect

        sig = inspect.signature(handler)
        if len(sig.parameters) >= 2:
            res = handler(app_name, window_title)
        else:
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
