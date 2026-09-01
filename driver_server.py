#!/usr/bin/env python3
"""
SeleniumBase MCP Server
========================
Exposes SeleniumBase browser automation as tools callable by any MCP client
(Claude Desktop, Claude Code, etc.) over stdio.

Model: One persistent browser session per server process.
Call start_browser once; drive it with the other tools; then close_browser.
"""
from __future__ import annotations
import atexit
import sys
from functools import wraps
from typing import Any, Literal
from mcp.server import MCPServer
from seleniumbase import Driver

mcp = MCPServer("seleniumbase-driver")

_driver: Driver | None = None


def _get_driver() -> Driver:
    if _driver is None:
        raise RuntimeError("No browser session. Call start_browser first.")
    return _driver


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
    """Start a new browser session. Must be called before any other tool.
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
        uc: Undetected-chromedriver mode, useful for sites with bot detection.
            (The `uc` option is for Chrome/Chromium, only!)
        incognito: Launch Chrome/Chromium in incognito mode.
        guest: Launch Chrome/Chromium in guest mode.
            (Do not combine this with incognito=True.)
        ad_block: Enable SeleniumBase's basic ad-blocking functionality.
        proxy: Optional proxy server. Examples include
            "SERVER:PORT" or "USER:PASS@SERVER:PORT".
    """
    global _driver
    if _driver is not None:
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

    try:
        _driver = Driver(
            browser=browser,
            headless=headless,
            use_chromium=use_chromium,
            uc=uc,
            incognito=incognito,
            guest_mode=guest_mode,
            ad_block=ad_block,
            proxy=proxy,
        )
        return (
            f"Started Driver() session with browser={browser}, "
            f"headless={headless}, uc={uc}."
        )
    except Exception as e:
        if _driver is not None:
            try:
                _driver.quit()
            except Exception:
                pass
            _driver = None

        return (
            f"Error starting browser: "
            f"{e.__class__.__name__} - {str(e).strip()}"
        )


@mcp.tool()
@handle_sb_errors
def close_browser() -> str:
    """Close the browser and end the session."""
    global _driver
    if _driver is None:
        return "No browser session was running."
    _driver.quit()
    _driver = None
    return "Browser closed."


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
    _get_driver().open(url)
    return f"Navigated to {url}"


@mcp.tool()
@handle_sb_errors
def go_back() -> str:
    """Go back one page in browser history.
    Same as clicking the Back button in the web browser."""
    _get_driver().go_back()
    return "Navigated back."


@mcp.tool()
@handle_sb_errors
def go_forward() -> str:
    """Go forward one page in browser history.
    Same as clicking the Forward button in the web browser."""
    _get_driver().go_forward()
    return "Navigated forward."


@mcp.tool()
@handle_sb_errors
def refresh_page() -> str:
    """Refresh the current page.
    Same as clicking the Reload button in the web browser."""
    _get_driver().refresh_page()
    return "Page refreshed."


@mcp.tool()
@handle_sb_errors
def get_current_url() -> str:
    """Get the URL of the current page."""
    return _get_driver().get_current_url()


@mcp.tool()
@handle_sb_errors
def get_title() -> str:
    """Get the title of the current page."""
    return _get_driver().get_title()


# ---------------------------------------------------------------------------
# Reading page content
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def get_page_source() -> str:
    """Get the full HTML source of the current page."""
    return _get_driver().get_page_source()


@mcp.tool()
@handle_sb_errors
def get_text(selector: str) -> str:
    """Get the visible text of an element matched by a CSS selector.
    Raises an exception if the element isn't found within the default timeout.
    """
    return _get_driver().get_text(selector)


@mcp.tool()
@handle_sb_errors
def find_elements_count(selector: str) -> int:
    """Count how many elements on the page match a CSS selector."""
    return len(_get_driver().find_elements(selector))


@mcp.tool()
@handle_sb_errors
def is_element_visible(selector: str) -> bool:
    """Check whether an element matched by a CSS selector is visible."""
    return _get_driver().is_element_visible(selector)


# ---------------------------------------------------------------------------
# Interacting with elements
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def click(selector: str, timeout: int | float | None = 7) -> str:
    """Click an element matched by the given selector.
    Raises an exception if the element isn't found within the timeout."""
    d = _get_driver()
    d.click(selector, timeout=timeout)
    return f"Clicked {selector}"


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
    Args:
        selector: The selector for the field.
        text: The text to type.
        clear_first: Clear the field's existing contents before typing.
        timeout: The maximum time to wait for an element in seconds."""
    d = _get_driver()
    if clear_first:
        d.type(selector, text, timeout=timeout)
    else:
        d.add_text(selector, text, timeout=timeout)
    return f"Typed into {selector}"


@mcp.tool()
@handle_sb_errors
def select_option_by_text(dropdown_selector: str, option: str) -> str:
    """Select a <select> dropdown option by its visible text.
    Raises an exception if the element or option aren't found
      within the default timeout, which is 7 seconds."""
    _get_driver().select_option_by_text(dropdown_selector, option)
    return f"Selected text '{option}' in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def select_option_by_value(dropdown_selector: str, option: str) -> str:
    """Select a <select> dropdown option by its value attribute.
    Raises an exception if the element or option aren't found
      within the default timeout, which is 7 seconds."""
    _get_driver().select_option_by_value(dropdown_selector, option)
    return f"Selected value '{option}' in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def select_option_by_index(dropdown_selector: str, option: str) -> str:
    """Select a <select> dropdown option by its 0-based index.
    Raises an exception if the element or option aren't found
      within the default timeout, which is 7 seconds."""
    _get_driver().select_option_by_index(dropdown_selector, option)
    return f"Selected index '{option}' in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def wait_for_element(selector: str, timeout: int | float | None = 10) -> str:
    """Wait until an element matched by a CSS selector appears.
    Raises an exception if the element isn't found within the given timeout."""
    _get_driver().wait_for_element(selector, timeout=timeout)
    return f"Element {selector} appeared."


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def switch_to_frame(selector: str) -> str:
    """Switch driver focus into an iframe matched by a CSS selector."""
    _get_driver().switch_to_frame(selector)
    return f"Switched into frame {selector}"


@mcp.tool()
@handle_sb_errors
def switch_to_default_content() -> str:
    """Switch driver focus back out to the main page (out of any iframe)."""
    _get_driver().switch_to_default_content()
    return "Switched back to main page."


# ---------------------------------------------------------------------------
# Assertions / verification
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def assert_text(text: str, selector: str | None = None) -> str:
    """Assert that text is present on the page, or within a specific element.
    Raises an error (returned as a tool error to the client) if not found."""
    d = _get_driver()
    if selector:
        d.assert_text(text, selector)
    else:
        d.assert_text(text)
    return f"Confirmed '{text}' is present."


# ---------------------------------------------------------------------------
# UC Mode / CDP Mode stealth helpers (require start_browser(uc=True))
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def activate_cdp_mode(url: str | None = None) -> str:
    """Switch the current browser session into CDP Mode, which adds stealth
    capabilities and additional methods that use the Chrome DevTools Protocol.
    You can optionally specify a URL to navigate to. Requires uc=True."""
    _get_driver().activate_cdp_mode(url)
    return f"CDP Mode activated (url={url!r})"


@mcp.tool()
@handle_sb_errors
def solve_captcha() -> str:
    """Attempt to solve a captcha (e.g. Cloudflare Turnstile) on the page."""
    _get_driver().solve_captcha()
    return "Attempted captcha solve."


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def screenshot(filename: str = "screenshot.png") -> str:
    """Take a screenshot of the current page and save it to disk."""
    _get_driver().save_screenshot(filename)
    return f"Screenshot saved to {filename}"


@mcp.tool()
@handle_sb_errors
def execute_script(script: str) -> Any:
    """Execute JavaScript in the page context and return the result.
    This method can run any arbitrary JavaScript on any site,
    so take any necessary precautions to prevent AI harnesses
    from running scripts that you don't want them to run."""
    return _get_driver().execute_script(script)


def _cleanup_browser():
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


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
