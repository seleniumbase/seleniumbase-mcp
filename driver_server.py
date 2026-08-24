#!/usr/bin/env python3
"""
SeleniumBase MCP Server
========================
Exposes SeleniumBase browser automation as tools callable by any MCP client
(Claude Desktop, Claude Code, etc.) over stdio.

Model: one persistent browser session per server process. Call start_browser
once, drive it with the other tools, then close_browser when done.
"""
from __future__ import annotations
import atexit
import sys
from mcp.server import MCPServer
from seleniumbase import Driver

mcp = MCPServer("seleniumbase-driver")

_driver: Driver | None = None


def _get_driver() -> Driver:
    if _driver is None:
        raise RuntimeError("No browser session. Call start_browser first.")
    return _driver


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

@mcp.tool()
def start_browser(
    browser: str = "chrome",
    headless: bool = False,
    uc: bool = True,
    incognito: bool = False,
    guest_mode: bool = False,
    proxy: str | None = None,
    ad_block: bool = False,
) -> str:
    """Start a new browser session. Must be called before any other tool.

    Args:
        headless: Run without a visible window. Set False if you need to
            watch the browser or if a site blocks headless clients.
        browser: "chrome", "edge", or "firefox".
        uc: Undetected-chromedriver mode, useful for sites with bot detection.
        incognito: Launch in a private/incognito window.
    """
    global _driver
    if _driver is not None:
        return (
            "A browser session is already running. Call close_browser first."
        )
    _driver = Driver(
        browser=browser,
        headless=headless,
        uc=uc,
        incognito=incognito,
        guest_mode=guest_mode,
        proxy=proxy,
        ad_block=ad_block,
    )
    return (
        f"Started Driver() session with browser={browser}, "
        f"headless={headless}, uc={uc}."
    )


@mcp.tool()
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
def navigate(url: str) -> str:
    """Navigate to a URL."""
    _get_driver().open(url)
    return f"Navigated to {url}"


@mcp.tool()
def go_back() -> str:
    """Go back one page in browser history."""
    _get_driver().go_back()
    return "Navigated back."


@mcp.tool()
def go_forward() -> str:
    """Go forward one page in browser history."""
    _get_driver().go_forward()
    return "Navigated forward."


@mcp.tool()
def refresh_page() -> str:
    """Refresh the current page."""
    _get_driver().refresh_page()
    return "Page refreshed."


@mcp.tool()
def get_current_url() -> str:
    """Get the URL of the current page."""
    return _get_driver().get_current_url()


@mcp.tool()
def get_title() -> str:
    """Get the title of the current page."""
    return _get_driver().get_title()


# ---------------------------------------------------------------------------
# Reading page content
# ---------------------------------------------------------------------------

@mcp.tool()
def get_page_source() -> str:
    """Get the full HTML source of the current page."""
    return _get_driver().get_page_source()


@mcp.tool()
def get_text(selector: str) -> str:
    """Get the visible text of an element matched by a CSS selector."""
    return _get_driver().get_text(selector)


@mcp.tool()
def find_elements_count(selector: str) -> int:
    """Count how many elements on the page match a CSS selector."""
    return len(_get_driver().find_elements(selector))


@mcp.tool()
def is_element_visible(selector: str) -> bool:
    """Check whether an element matched by a CSS selector is visible."""
    return _get_driver().is_element_visible(selector)


# ---------------------------------------------------------------------------
# Interacting with elements
# ---------------------------------------------------------------------------

@mcp.tool()
def click(selector: str, by: str = "css") -> str:
    """Click an element.

    Args:
        selector: CSS selector or XPath string identifying the element.
        by: "css" or "xpath".
    """
    d = _get_driver()
    d.click(f"xpath={selector}" if by == "xpath" else selector)
    return f"Clicked {selector}"


@mcp.tool()
def type_text(selector: str, text: str, clear_first: bool = True) -> str:
    """Type text into an input field.

    Args:
        selector: CSS selector for the field.
        text: Text to type.
        clear_first: Clear the field's existing contents before typing.
    """
    d = _get_driver()
    if clear_first:
        d.type(selector, text)
    else:
        d.add_text(selector, text)
    return f"Typed into {selector}"


@mcp.tool()
def select_option(selector: str, option_text: str) -> str:
    """Select a dropdown (<select>) option by its visible text."""
    _get_driver().select_option_by_text(selector, option_text)
    return f"Selected '{option_text}' in {selector}"


@mcp.tool()
def wait_for_element(selector: str, timeout: int = 10) -> str:
    """Wait until an element matched by a CSS selector appears."""
    _get_driver().wait_for_element(selector, timeout=timeout)
    return f"Element {selector} appeared."


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

@mcp.tool()
def switch_to_frame(selector: str) -> str:
    """Switch driver focus into an iframe matched by a CSS selector."""
    _get_driver().switch_to_frame(selector)
    return f"Switched into frame {selector}"


@mcp.tool()
def switch_to_default_content() -> str:
    """Switch driver focus back out to the main page (out of any iframe)."""
    _get_driver().switch_to_default_content()
    return "Switched back to main page."


# ---------------------------------------------------------------------------
# Assertions / verification
# ---------------------------------------------------------------------------

@mcp.tool()
def assert_text(text: str, selector: str | None = None) -> str:
    """Assert that text is present on the page, or within a specific element.

    Raises an error (returned as a tool error to the client) if not found.
    """
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
def activate_cdp_mode(url: str | None = None) -> str:
    """Switch the current session into Pure CDP Mode, optionally navigating
    to a URL. Once active, CDP-only capabilities (e.g. more thorough
    stealth) apply to subsequent actions. Requires uc=True."""
    _get_driver().activate_cdp_mode(url)
    return f"CDP Mode activated (url={url!r})"


@mcp.tool()
def solve_captcha() -> str:
    """Attempt to solve a captcha (e.g. Cloudflare Turnstile) on the page."""
    _get_driver().solve_captcha()
    return "Attempted captcha solve."


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

@mcp.tool()
def screenshot(filename: str = "screenshot.png") -> str:
    """Take a screenshot of the current page and save it to disk."""
    _get_driver().save_screenshot(filename)
    return f"Screenshot saved to {filename}"


@mcp.tool()
def execute_script(script: str):
    """Execute JavaScript in the page context and return the result."""
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
