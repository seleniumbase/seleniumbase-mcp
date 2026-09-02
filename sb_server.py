#!/usr/bin/env python3
"""
SeleniumBase SB() MCP Server
=============================
Exposes SeleniumBase's `SB()` context-manager class as MCP tools, using it
WITHOUT the `with` statement — by calling `__enter__`/`__exit__` manually —
since an MCP server's tool calls happen across many separate function calls,
not inside one indented block.

    sb_context = SB(...)
    sb = sb_context.__enter__()
    ...
    sb_context.__exit__(None, None, None)

`sb` (a BaseCase instance) is SeleniumBase's broadest API: everything
Driver-based automation offers, plus drag-and-drop, MFA/TOTP codes,
and file downloads.

Reference:
github.com/seleniumbase/SeleniumBase/blob/master/help_docs/method_summary.md

Model: One persistent SB() session per server process.
Call start_browser once; drive it with the other tools; then close_browser.
"""
from __future__ import annotations
import atexit
import sys
from functools import wraps
from typing import Any, Literal
from mcp.server import MCPServer
from seleniumbase import SB

mcp = MCPServer("seleniumbase-sb")

_sb_context = None
_sb: Any = None


def _get_sb() -> Any:
    if _sb is None:
        raise RuntimeError("No browser session. Call start_browser first.")
    return _sb


def handle_sb_errors(func):
    """Catches SeleniumBase errors and surfaces them as descriptive strings
    so the LLM agent can read them and self-correct."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_type = e.__class__.__name__
            error_msg = str(e).strip()
            return f"Error in {func.__name__}: {error_type} - {error_msg}"
    return wrapper


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def start_browser(
    browser: Literal["chrome", "edge", "firefox", "chromium"] = "chrome",
    headless: bool | None = None,
    uc: bool = True,
    incognito: bool = False,
    guest_mode: bool = False,
    ad_block: bool = False,
    proxy: str | None = None,
) -> str:
    """Start a new SB() session. Must be called before any other tool.
    Args:
        browser: "chrome", "edge", "firefox", or "chromium".
        headless: Controls whether the browser runs without a visible window.
            If True, always run headless. If False, always run headed.
            If omitted (None), the default depends on the operating system:
            Linux defaults to headless because MCP/server environments
            commonly do not have a graphical desktop, while Windows and macOS
            default to headed so that a visible browser window is available.
            Use True or False to explicitly override the OS-specific default
            on any operating system.
        uc: Undetected-Chromedriver (UC Mode) — evades bot detection.
        incognito: Launch in a private/incognito window.
        guest_mode: Launch in Chrome guest mode.
        ad_block: Block ads.
        proxy: Proxy string, e.g. "USER:PASS@SERVER:PORT" or "SERVER:PORT".
    """
    global _sb_context, _sb
    if _sb is not None:
        return (
            "A browser session is already running. Call close_browser first."
        )

    # OS-specific default:
    # - Linux: headless by default for server/container compatibility.
    # - Windows/macOS: headed by default for interactive desktop use.
    # - Explicit True/False always overrides the OS default.
    if headless is None:
        headless = sys.platform.startswith("linux")

    use_chromium = False
    if browser == "chromium":
        use_chromium = True
        browser = "chrome"

    kwargs: dict[str, Any] = {
        "browser": browser, "headless": headless, "test": False
    }
    if use_chromium:
        kwargs["use_chromium"] = True
    if uc:
        kwargs["uc"] = True
    if incognito:
        kwargs["incognito"] = True
    if guest_mode:
        kwargs["guest_mode"] = True
    if proxy:
        kwargs["proxy"] = proxy
    if ad_block:
        kwargs["ad_block"] = True
    try:
        _sb_context = SB(**kwargs)
        _sb = _sb_context.__enter__()
        return (
            f"Started SB() session with browser={browser}, "
            f"headless={headless}, uc={uc}."
        )
    except Exception as e:
        if _sb is not None:
            try:
                _sb.quit()
            except Exception:
                pass
            _sb_context = None
            _sb = None
        return (
            f"Error starting browser: "
            f"{e.__class__.__name__} - {str(e).strip()}"
        )


@mcp.tool()
@handle_sb_errors
def close_browser() -> str:
    global _sb_context, _sb
    if _sb_context is None:
        return "No browser session was running."
    try:
        _sb_context.__exit__(None, None, None)
    finally:
        _sb_context = None
        _sb = None
    return "Browser closed."


# ---------------------------------------------------------------------------
# Page information
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def browser_status() -> dict:
    """Return basic information about the current browser session."""
    if _sb is None:
        return {
            "running": False,
        }

    return {
        "running": True,
        "url": _sb.get_current_url(),
        "title": _sb.get_title(),
    }


@mcp.tool()
@handle_sb_errors
def page_snapshot() -> dict:
    """Return compact information about the current page."""
    sb = _get_sb()

    return {
        "url": sb.get_current_url(),
        "title": sb.get_title(),
        "text": sb.get_text("body"),
    }


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def navigate(url: str) -> str:
    """Navigate to the given URL in the web browser.
    If the URL doesn't start with a protocol (eg: `https://`),
      then `https://` is automatically prefixed in before navigation.
    Waits until the initial HTML document is fully parsed and loaded.
    New pages visited will show up in browser navigation history.
    If the URL is invalid or the page can't load due to an issue,
      then the corresponding errors will be raised."""
    _get_sb().goto(url)
    return f"Navigated to {url}"


@mcp.tool()
@handle_sb_errors
def refresh_page() -> str:
    """Refresh the current page.
    Same as clicking the Reload button in the web browser."""
    _get_sb().refresh()
    return "Page refreshed."


@mcp.tool()
@handle_sb_errors
def go_back() -> str:
    """Go back one page in browser history.
    Same as clicking the Back button in the web browser."""
    _get_sb().go_back()
    return "Navigated back."


@mcp.tool()
@handle_sb_errors
def go_forward() -> str:
    """Go forward one page in browser history.
    Same as clicking the Forward button in the web browser."""
    _get_sb().go_forward()
    return "Navigated forward."


@mcp.tool()
@handle_sb_errors
def get_current_url() -> str:
    """Get the URL of the current page."""
    return _get_sb().get_current_url()


@mcp.tool()
@handle_sb_errors
def get_title() -> str:
    """Get the title of the current page."""
    return _get_sb().get_title()


@mcp.tool()
@handle_sb_errors
def get_origin() -> str:
    """Get the origin (scheme + host) of the current page."""
    return _get_sb().get_origin()


@mcp.tool()
@handle_sb_errors
def get_user_agent() -> str:
    """Get the browser's current user agent string."""
    return _get_sb().get_user_agent()


# ---------------------------------------------------------------------------
# Finding & reading
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def get_text(selector: str = "body") -> str:
    """Get the visible text within an element (default: whole page body).
    Raises an exception if the element isn't found within the default timeout.
    """
    return _get_sb().get_text(selector)


@mcp.tool()
@handle_sb_errors
def get_html_source() -> str:
    """Get the full HTML source of the current page."""
    return _get_sb().get_page_source()


@mcp.tool()
@handle_sb_errors
def get_element_html(selector: str) -> str:
    """Get the outer HTML of a specific element."""
    return _get_sb().get_html(selector)


@mcp.tool()
@handle_sb_errors
def get_attribute(selector: str, attribute: str) -> Any:
    """Get one attribute's value from an element."""
    return _get_sb().get_attribute(selector, attribute)


@mcp.tool()
@handle_sb_errors
def find_elements_count(selector: str) -> int | str:
    """Count how many elements on the page match a selector."""
    return len(_get_sb().find_elements(selector))


@mcp.tool()
@handle_sb_errors
def is_element_present(selector: str) -> bool | str:
    """Check whether an element matching a selector exists in the DOM."""
    return _get_sb().is_element_present(selector)


@mcp.tool()
@handle_sb_errors
def is_element_visible(selector: str) -> bool | str:
    """Check whether an element matching a selector is visible."""
    return _get_sb().is_element_visible(selector)


@mcp.tool()
@handle_sb_errors
def is_element_clickable(selector: str) -> bool | str:
    """Check whether an element matching a selector is clickable."""
    return _get_sb().is_element_clickable(selector)


@mcp.tool()
@handle_sb_errors
def is_text_visible(text: str, selector: str = "html") -> bool | str:
    """Check whether specific text is visible within an element."""
    return _get_sb().is_text_visible(text, selector)


@mcp.tool()
@handle_sb_errors
def is_selected(selector: str) -> bool | str:
    """Check whether a checkbox/radio-button element is selected/checked."""
    return _get_sb().is_selected(selector)


# ---------------------------------------------------------------------------
# Interacting with elements
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def click(selector: str, timeout: int | None = None) -> str:
    """Click an element matched by the given CSS selector.
    Raises an exception if the element isn't found within the timeout."""
    _get_sb().click(selector, timeout=timeout)
    return f"Clicked {selector}"


@mcp.tool()
@handle_sb_errors
def click_if_visible(selector: str) -> str:
    """Click an element only if it's currently visible; no-op otherwise."""
    _get_sb().click_if_visible(selector)
    return f"click_if_visible ran for {selector}"


@mcp.tool()
@handle_sb_errors
def click_visible_elements(selector: str, limit: int = 0) -> str:
    """Click every currently-visible element matching a selector, in order.
    limit=0 means no limit."""
    _get_sb().click_visible_elements(selector, limit=limit)
    return f"Clicked visible elements matching {selector}"


@mcp.tool()
@handle_sb_errors
def click_nth_visible_element(selector: str, number: int) -> str:
    """Click the Nth visible element (1-indexed) matching a selector.
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().click_nth_visible_element(selector, number)
    return f"Clicked visible element #{number} matching {selector}"


@mcp.tool()
@handle_sb_errors
def click_link(link_text: str) -> str:
    """Click a link (<a> tag) by its visible text.
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().click_link(link_text)
    return f"Clicked link with text '{link_text}'"


@mcp.tool()
@handle_sb_errors
def double_click(selector: str) -> str:
    """Double-click an element.
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().double_click(selector)
    return f"Double-clicked {selector}"


@mcp.tool()
@handle_sb_errors
def context_click(selector: str) -> str:
    """Right-click (context-click) an element.
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().context_click(selector)
    return f"Right-clicked {selector}"


@mcp.tool()
@handle_sb_errors
def type_text(
    selector: str,
    text: str,
    clear_first: bool = True,
    timeout: int | float | None = 7,
) -> str:
    """Type text into an input field / textarea.
    Raises an exception if the element isn't found within the timeout.
    Optionally clear the text field first. (Default: True)
    Args:
        selector: The selector for the field.
        text: The text to type.
        clear_first: Clear the field's existing contents before typing.
        timeout: The maximum time to wait for an element in seconds.
    """
    if clear_first:
        _get_sb().type(selector, text, timeout=timeout)
        return f"Typed {text} into {selector} after clearing the field."
    else:
        _get_sb().send_keys(selector, text, timeout=timeout)
        return f"Typed {text} into {selector}"


@mcp.tool()
@handle_sb_errors
def set_value(selector: str, text: str) -> str:
    """Set an input's value directly (e.g. for sliders, fast form fills).
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().set_value(selector, text)
    return f"Set value of {selector}"


@mcp.tool()
@handle_sb_errors
def clear_input(selector: str) -> str:
    """Clear an input field.
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().clear(selector)
    return f"Cleared {selector}"


@mcp.tool()
@handle_sb_errors
def submit(selector: str) -> str:
    """Submit a form via a selector inside it.
    Raises an exception if the element isn't found within the default timeout.
    """
    _get_sb().submit(selector)
    return f"Submitted form via {selector}"


@mcp.tool()
@handle_sb_errors
def select_option_by_text(dropdown_selector: str, option: str) -> str:
    """Select a <select> dropdown option by its visible text.
    Raises an exception if the element or option aren't found
      within the default timeout, which is 7 seconds."""
    _get_sb().select_option_by_text(dropdown_selector, option)
    return f"Selected text '{option}' in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def select_option_by_value(dropdown_selector: str, option: str) -> str:
    """Select a <select> dropdown option by its value attribute.
    Raises an exception if the element or option aren't found
      within the default timeout, which is 7 seconds."""
    _get_sb().select_option_by_value(dropdown_selector, option)
    return f"Selected value '{option}' in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def select_option_by_index(dropdown_selector: str, option: int) -> str:
    """Select a <select> dropdown option by its 0-based index.
    Raises an exception if the element or option aren't found
      within the default timeout, which is 7 seconds."""
    _get_sb().select_option_by_index(dropdown_selector, option)
    return f"Selected index {option} in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def hover_and_click(hover_selector: str, click_selector: str) -> str:
    """Hover over one element (e.g. to open a dropdown), then click another."""
    _get_sb().hover_and_click(hover_selector, click_selector)
    return f"Hovered {hover_selector} then clicked {click_selector}"


@mcp.tool()
@handle_sb_errors
def drag_and_drop(drag_selector: str, drop_selector: str) -> str:
    """Drag one element onto another."""
    _get_sb().drag_and_drop(drag_selector, drop_selector)
    return f"Dragged {drag_selector} onto {drop_selector}"


@mcp.tool()
@handle_sb_errors
def nested_click(parent_selector: str, selector: str) -> str:
    """Click an element nested inside another (e.g. inside an iframe)."""
    _get_sb().nested_click(parent_selector, selector)
    return f"Clicked {selector} inside {parent_selector}"


@mcp.tool()
@handle_sb_errors
def choose_file(selector: str, file_path: str) -> str:
    """Set a <input type="file"> element to upload a local file."""
    _get_sb().choose_file(selector, file_path)
    return f"Set file input {selector} to {file_path}"


# ---------------------------------------------------------------------------
# Waiting
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def wait_for_element(selector: str, timeout: int | None = None) -> str:
    """Wait until an element is visible on the page."""
    _get_sb().wait_for_element(selector, timeout=timeout)
    return f"Element {selector} is visible."


@mcp.tool()
@handle_sb_errors
def wait_for_element_present(selector: str, timeout: int | None = None) -> str:
    """Wait until an element is present in the DOM (may not be visible)."""
    _get_sb().wait_for_element_present(selector, timeout=timeout)
    return f"Element {selector} is present."


@mcp.tool()
@handle_sb_errors
def wait_for_element_not_visible(
    selector: str, timeout: int | None = None
) -> str:
    """Wait until an element is no longer visible."""
    _get_sb().wait_for_element_not_visible(selector, timeout=timeout)
    return f"Element {selector} is no longer visible."


@mcp.tool()
@handle_sb_errors
def wait_for_element_absent(selector: str, timeout: int | None = None) -> str:
    """Wait until an element is removed from the DOM."""
    _get_sb().wait_for_element_absent(selector, timeout=timeout)
    return f"Element {selector} is now absent."


@mcp.tool()
@handle_sb_errors
def wait_for_text(
    text: str, selector: str = "html", timeout: int | None = None
) -> str:
    """Wait until specific text appears within an element."""
    _get_sb().wait_for_text(text, selector, timeout=timeout)
    return f"Text '{text}' appeared in {selector}."


# ---------------------------------------------------------------------------
# Assertions (raise an error, surfaced to the MCP client, if they fail)
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def assert_element(selector: str, timeout: int | None = None) -> str:
    """Assert an element is visible."""
    _get_sb().assert_element(selector, timeout=timeout)
    return f"Confirmed {selector} is visible."


@mcp.tool()
@handle_sb_errors
def assert_element_present(selector: str, timeout: int | None = None) -> str:
    """Assert an element is present in the DOM (may not be visible)."""
    _get_sb().assert_element_present(selector, timeout=timeout)
    return f"Confirmed {selector} is present."


@mcp.tool()
@handle_sb_errors
def assert_element_not_visible(
    selector: str, timeout: int | None = None
) -> str:
    """Assert an element is not visible."""
    _get_sb().assert_element_not_visible(selector, timeout=timeout)
    return f"Confirmed {selector} is not visible."


@mcp.tool()
@handle_sb_errors
def assert_text(
    text: str, selector: str = "html", timeout: int | None = None
) -> str:
    """Assert text is present within an element."""
    _get_sb().assert_text(text, selector, timeout=timeout)
    return f"Confirmed '{text}' is present in {selector}."


@mcp.tool()
@handle_sb_errors
def assert_exact_text(
    text: str, selector: str = "html", timeout: int | None = None
) -> str:
    """Assert an element's text matches exactly."""
    _get_sb().assert_exact_text(text, selector, timeout=timeout)
    return f"Confirmed {selector} text is exactly '{text}'."


@mcp.tool()
@handle_sb_errors
def assert_title(title: str) -> str:
    """Assert the page title matches exactly."""
    _get_sb().assert_title(title)
    return f"Confirmed title is '{title}'."


@mcp.tool()
@handle_sb_errors
def assert_url(url: str) -> str:
    """Assert the current URL matches exactly."""
    _get_sb().assert_url(url)
    return f"Confirmed URL is '{url}'."


@mcp.tool()
@handle_sb_errors
def assert_url_contains(substring: str) -> str:
    """Assert the current URL contains a substring."""
    _get_sb().assert_url_contains(substring)
    return f"Confirmed URL contains '{substring}'."


@mcp.tool()
@handle_sb_errors
def assert_no_404_errors() -> str:
    """Assert that none of the page's links return a 404 status."""
    _get_sb().assert_no_404_errors()
    return "Confirmed no broken (404) links."


@mcp.tool()
@handle_sb_errors
def assert_no_js_errors() -> str:
    """Assert the browser console has no JavaScript errors."""
    _get_sb().assert_no_js_errors()
    return "Confirmed no JS errors."


# ---------------------------------------------------------------------------
# Cookies & storage
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def get_cookies() -> Any:
    """Get all cookies for the current session."""
    return _get_sb().get_cookies()


@mcp.tool()
@handle_sb_errors
def delete_all_cookies() -> str:
    """Delete all cookies."""
    _get_sb().delete_all_cookies()
    return "All cookies deleted."


@mcp.tool()
@handle_sb_errors
def save_cookies(name: str = "cookies.txt") -> str:
    """Save current cookies to a file."""
    _get_sb().save_cookies(name=name)
    return f"Cookies saved to {name}"


@mcp.tool()
@handle_sb_errors
def load_cookies(name: str = "cookies.txt") -> str:
    """Load cookies from a previously saved file."""
    _get_sb().load_cookies(name=name)
    return f"Cookies loaded from {name}"


@mcp.tool()
@handle_sb_errors
def get_local_storage_item(key: str) -> Any:
    """Get a value from the page's localStorage."""
    return _get_sb().get_local_storage_item(key)


@mcp.tool()
@handle_sb_errors
def set_local_storage_item(key: str, value: str) -> str:
    """Set a value in the page's localStorage."""
    _get_sb().set_local_storage_item(key, value)
    return f"Set localStorage[{key!r}]"


@mcp.tool()
@handle_sb_errors
def get_session_storage_item(key: str) -> Any:
    """Get a value from the page's sessionStorage."""
    return _get_sb().get_session_storage_item(key)


@mcp.tool()
@handle_sb_errors
def set_session_storage_item(key: str, value: str) -> str:
    """Set a value in the page's sessionStorage."""
    _get_sb().set_session_storage_item(key, value)
    return f"Set sessionStorage[{key!r}]"


# ---------------------------------------------------------------------------
# Scrolling
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def scroll_into_view(selector: str) -> str:
    """Scroll an element into view."""
    _get_sb().scroll_into_view(selector)
    return f"Scrolled {selector} into view."


@mcp.tool()
@handle_sb_errors
def scroll_to_top() -> str:
    """Scroll to the top of the page."""
    _get_sb().scroll_to_top()
    return "Scrolled to top."


@mcp.tool()
@handle_sb_errors
def scroll_to_bottom() -> str:
    """Scroll to the bottom of the page."""
    _get_sb().scroll_to_bottom()
    return "Scrolled to bottom."


@mcp.tool()
@handle_sb_errors
def scroll_up(amount: int = 25) -> str:
    """Scroll up by a relative amount."""
    _get_sb().scroll_up(amount=amount)
    return f"Scrolled up {amount}."


@mcp.tool()
@handle_sb_errors
def scroll_down(amount: int = 25) -> str:
    """Scroll down by a relative amount."""
    _get_sb().scroll_down(amount=amount)
    return f"Scrolled down {amount}."


# ---------------------------------------------------------------------------
# Windows & tabs & frames
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def get_window_rect() -> dict | str:
    """Get the current window's position and size."""
    return _get_sb().get_window_rect()


@mcp.tool()
@handle_sb_errors
def maximize_window() -> str:
    """Maximize the browser window."""
    _get_sb().maximize_window()
    return "Window maximized."


@mcp.tool()
@handle_sb_errors
def minimize_window() -> str:
    """Minimize the browser window."""
    _get_sb().minimize_window()
    return "Window minimized."


@mcp.tool()
@handle_sb_errors
def open_new_tab(switch_to: bool = True) -> str:
    """Open a new browser tab, optionally switching to it."""
    _get_sb().open_new_tab(switch_to=switch_to)
    return f"Opened new tab (switch_to={switch_to})"


@mcp.tool()
@handle_sb_errors
def switch_to_newest_tab() -> str:
    """Switch to the most recently opened tab."""
    _get_sb().switch_to_newest_tab()
    return "Switched to newest tab."


@mcp.tool()
@handle_sb_errors
def switch_to_default_window() -> str:
    """Switch back to the first/original browser tab."""
    _get_sb().switch_to_default_window()
    return "Switched to default (first) tab."


@mcp.tool()
@handle_sb_errors
def switch_to_frame(selector: str = "iframe") -> str:
    """Switch driver focus into an iframe matched by a CSS selector."""
    _get_sb().switch_to_frame(selector)
    return f"Switched into frame {selector}"


@mcp.tool()
@handle_sb_errors
def switch_to_default_content() -> str:
    """Switch driver focus back out to the main page (out of any iframe)."""
    _get_sb().switch_to_default_content()
    return "Switched back to main page."


# ---------------------------------------------------------------------------
# UC Mode / CDP Mode stealth helpers (require start_browser(uc=True))
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def activate_cdp_mode(url: str | None = None) -> str:
    """Switch the current browser session into CDP Mode, which adds stealth
    capabilities and additional methods that use the Chrome DevTools Protocol.
    You can optionally specify a URL to navigate to. Requires uc=True."""
    _get_sb().activate_cdp_mode(url)
    return f"CDP Mode activated (url={url!r})"


@mcp.tool()
@handle_sb_errors
def solve_captcha() -> str:
    """Attempt to solve a captcha (e.g. Cloudflare Turnstile) on the page."""
    _get_sb().solve_captcha()
    return "Attempted captcha solve."


# ---------------------------------------------------------------------------
# MFA / TOTP
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def get_mfa_code(totp_key: str) -> str:
    """Generate a current TOTP (e.g. Google Authenticator) code from a
    base32 secret key."""
    return _get_sb().get_mfa_code(totp_key)


@mcp.tool()
@handle_sb_errors
def enter_mfa_code(selector: str, totp_key: str) -> str:
    """Generate a current TOTP code and type it into a field."""
    _get_sb().enter_mfa_code(selector, totp_key)
    return f"Entered MFA code into {selector}"


# ---------------------------------------------------------------------------
# Output & files
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def save_screenshot(
    name: str = "screenshot.png", folder: str | None = None
) -> str:
    """Save a screenshot of the current page."""
    _get_sb().save_screenshot(name, folder=folder)
    return f"Screenshot saved as {name}"


@mcp.tool()
@handle_sb_errors
def save_page_source(
    name: str = "page_source.html", folder: str | None = None
) -> str:
    """Save the current page's HTML source to a file."""
    _get_sb().save_page_source(name, folder=folder)
    return f"Page source saved as {name}"


@mcp.tool()
@handle_sb_errors
def print_to_pdf(name: str = "page.pdf", folder: str | None = None) -> str:
    """Print the current page to a PDF file."""
    _get_sb().print_to_pdf(name, folder=folder)
    return f"Page saved as PDF: {name}"


@mcp.tool()
@handle_sb_errors
def download_file(file_url: str, destination_folder: str | None = None) -> str:
    """Download a file from a URL to a local folder."""
    _get_sb().download_file(file_url, destination_folder=destination_folder)
    return f"Downloaded {file_url}"


@mcp.tool()
@handle_sb_errors
def evaluate(expression: str) -> Any:
    """Evaluate a JavaScript expression in the page context and return the
    result."""
    return _get_sb().evaluate(expression)


@mcp.tool()
@handle_sb_errors
def execute_script(script: str) -> Any:
    """Execute JavaScript in the page context and return the result.
    This method can run any arbitrary JavaScript on any site,
    so take any necessary precautions to prevent AI harnesses
    from running scripts that you don't want them to run."""
    return _get_sb().execute_script(script)


@mcp.tool()
@handle_sb_errors
def highlight(selector: str, loops: int = 4) -> str:
    """Briefly highlight an element with a colored animation — useful for
    narrating actions on a visible/headed browser."""
    _get_sb().highlight(selector, loops=loops)
    return f"Highlighted {selector}"


@mcp.tool()
@handle_sb_errors
def flash(selector: str, duration: float = 1) -> str:
    """Flash an element to draw attention to it."""
    _get_sb().flash(selector, duration=duration)
    return f"Flashed {selector}"


@mcp.tool()
@handle_sb_errors
def sleep(seconds: float) -> str:
    """Pause execution for a number of seconds."""
    _get_sb().sleep(seconds)
    return f"Slept {seconds}s"


def _cleanup_browser():
    global _sb_context, _sb
    if _sb_context is not None:
        try:
            _sb_context.__exit__(None, None, None)
        except Exception:
            pass
    _sb_context = None
    _sb = None


def main():
    atexit.register(_cleanup_browser)
    print(f'Running the "{mcp.name}" server...', file=sys.stderr)
    try:
        mcp.run(transport="stdio")
    except (KeyboardInterrupt, SystemExit):
        print(f'\nThe "{mcp.name}" server was stopped.', file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
