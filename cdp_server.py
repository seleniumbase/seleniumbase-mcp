#!/usr/bin/env python3
"""
SeleniumBase Pure CDP Mode MCP Server
======================================
Exposes SeleniumBase's Pure CDP Mode (sync API, `seleniumbase.sb_cdp.Chrome`)
as MCP tools. Pure CDP Mode drives the web browser entirely over the Chrome
DevTools Protocol (no WebDriver at all), and can avoid automation signals
that are generally associated with WebDriver-based browser automation tools.
Pure CDP Mode also includes CAPTCHA-solving support for detecting & clicking
CAPTCHA checkboxes via CDP functions.

Reference:
github.com/seleniumbase/SeleniumBase/blob/master/help_docs/cdp_mode_methods.md

Model: One persistent `sb_cdp.Chrome` session per server process.
Call start_browser once; drive it with the other tools; then close_browser.

Selectors:
- CSS selectors are preferred. (All tools that take selectors support CSS.)
- XPath support is tool-dependent: XPath is accepted in several (but not all)
  cases. Some methods utilize the Chrome DevTools protocol, where XPath might
  not be accepted unless SeleniumBase is able to convert those XPath selectors
  into valid CSS selectors first (which SeleniumBase tries to do as needed).
- SeleniumBase includes a visible text selector, e.g. `a:contains("Sign in")`.
  This selector is accepted by multiple individual tools, but not all of them.
- Tool-specific documentation takes precedence when selector behavior differs.

Design notes:
Related SeleniumBase capabilities are consolidated into parameterized tools
using action, mode, state, or check parameters.
This keeps the toolset compact and predictable while giving an MCP client
access to the underlying browser-automation capabilities without
having to choose between multiple near-identical tools.

Tool-selection philosophy:
- Use 'start_browser'/'close_browser' for opening/quitting the web browser.
- Use 'navigate'/'manage_history' for browser navigation & history inspection.
- Use 'get_page_info' for reading browser/page metadata such as URL/title.
- Use 'get_content'/'get_attributes' for reading text, HTML, or attributes.
- Use 'find_elements' for discovering and inspecting multiple matching
  elements as structured data.
- Use 'check_condition' for an immediate, non-waiting state check.
- Use 'wait_for' when the agent needs to wait for a condition to become true.
- Use 'assert_condition' when the agent needs to verify an expected condition
  and treat failure as an assertion error.
- Use 'click'/'type_text'/'select_option' for standard page interactions.
- Use 'hover_action' for just a hover, with a click, or with a drag/drop.
- Use 'focus' for element positioning and visual focus.
- Use 'solve_captcha' for clicking the checkbox of a CAPTCHA on the page.
- Use 'save_output' for saving page output as a PNG, a PDF, or an HTML file.
"""
from __future__ import annotations
import atexit
import sys
from functools import wraps
from typing import Any, Literal
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from seleniumbase import sb_cdp

mcp = MCPServer("seleniumbase-cdp")

_sb: sb_cdp.CDPMethods | None = None


def _get_sb() -> sb_cdp.CDPMethods:
    """Return the active browser session or raise a useful lifecycle error."""
    if _sb is None:
        raise ToolError("No browser session. Call start_browser first.")
    return _sb


def handle_sb_errors(func):
    """Convert SeleniumBase/runtime exceptions into descriptive MCP results.

    Browser automation failures are returned as readable error strings so
    an MCP client/LLM can inspect the error and decide whether to retry,
    change a selector, wait for a condition, navigate elsewhere, or take
    another corrective action.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ToolError:
            raise
        except Exception as e:
            error_type = e.__class__.__name__
            error_msg = str(e).strip()
            return f"Error in {func.__name__}: {error_type} - {error_msg}"

    return wrapper


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

@mcp.tool()
def start_browser(
    url: str | None = None,
    headless: bool | None = None,
    use_chromium: bool = False,
    browser_executable_path: str | None = None,
    incognito: bool = False,
    guest: bool = False,
    ad_block: bool = False,
    proxy: str | None = None,
) -> str:
    """Launch a persistent SeleniumBase Pure CDP Mode browser session.

    This must be called before browser interaction tools such as navigate,
    get_content, click, type_text, or find_elements. The same browser
    session remains active across subsequent MCP tool calls until
    close_browser is called or the server process exits.

    Pure CDP Mode communicates directly with the browser through the Chrome
    DevTools Protocol rather than WebDriver. This provides SeleniumBase's
    CDP-based browser automation capabilities without using WebDriver as the
    browser-control layer.

    Args:
        url: Optional URL to open immediately after the browser launches.
            If omitted, the browser starts without navigating to a requested
            page.

        headless: Controls whether the browser runs without a visible window.
            If True, always run headless. If False, always run headed.
            If omitted (None), the default depends on the operating system:
            Linux defaults to headless because MCP/server environments
            commonly do not have a graphical desktop, while Windows and macOS
            default to headed so that a visible browser window is available.
            Use True or False to explicitly override the OS-specific default
            on any operating system.

        use_chromium: Use Chromium instead of Google Chrome. This is useful
            when Google Chrome is not installed. SeleniumBase can manage the
            Chromium browser when this option is enabled.

        browser_executable_path: Explicit filesystem path to the browser
            executable when it is not installed in a standard location.
            Do not combine this with use_chromium=True.

        incognito: Launch Chrome/Chromium in incognito mode.

        guest: Launch Chrome/Chromium in guest mode. Do not combine this with
            incognito=True.

        ad_block: Enable SeleniumBase's basic ad-blocking functionality.

        proxy: Optional proxy server. Examples include
            "SERVER:PORT" or "USER:PASS@SERVER:PORT".

    Returns:
        A confirmation message when the browser starts successfully, including
        the effective headless setting, or a descriptive error when browser
        startup fails.

    Lifecycle:
        Call start_browser once at the beginning of a browser automation
        workflow. Reusing the existing session preserves cookies, tabs,
        navigation history, localStorage/sessionStorage, and other browser
        state between tool calls. Call close_browser when finished.

    Environment requirements:
        The MCP runtime must have a compatible Chrome or Chromium browser
        available. If the browser executable cannot be discovered, use
        use_chromium=True or provide browser_executable_path explicitly.

        On Linux, the default is headless=True so the browser can run in
        typical server/container environments without a graphical desktop.
        Set headless=False when a graphical display is available and a visible
        browser is desired. On Windows and macOS, the default is
        headless=False. Set headless=True when running without a desktop or
        when a visible browser window is not desired.
    """
    global _sb

    if _sb is not None:
        return ("A browser session is already running.")

    if incognito and guest:
        return "Error: incognito and guest cannot both be enabled."

    if use_chromium and browser_executable_path:
        return (
            "Error: use_chromium and browser_executable_path "
            "cannot both be used at the same time."
        )

    # OS-specific default:
    # - Linux: headless by default for server/container compatibility.
    # - Windows/macOS: headed by default for interactive desktop use.
    # - Explicit True/False always overrides the OS default.
    if headless is None:
        effective_headless = sys.platform.startswith("linux")
    else:
        effective_headless = headless

    kwargs: dict[str, Any] = {"headless": effective_headless}

    if use_chromium:
        kwargs["use_chromium"] = True
    if browser_executable_path:
        kwargs["browser_executable_path"] = browser_executable_path
    if incognito:
        kwargs["incognito"] = True
    if guest:
        kwargs["guest"] = True
    if ad_block:
        kwargs["ad_block"] = True
    if proxy:
        kwargs["proxy"] = proxy

    try:
        _sb = sb_cdp.Chrome(url, **kwargs)
        return (
            f"Started Pure CDP Mode browser "
            f"(url={url!r}, headless={effective_headless}, "
            f"use_chromium={use_chromium})"
        )
    except Exception:
        # Retry once if the first launch attempt fails.
        # (A retry helped when testing on Glama's MCP Inspector.)
        # If it fails again, then we'll return the error from
        # the 2nd attempt. (The first error doesn't matter here.)
        try:
            if _sb is not None:
                try:
                    _sb.quit()
                except Exception:
                    pass
                _sb = None
            _sb = sb_cdp.Chrome(url, **kwargs)
            return (
                f"Started Pure CDP Mode browser "
                f"(url={url!r}, headless={effective_headless}, "
                f"use_chromium={use_chromium})"
            )
        except Exception as e:
            if _sb is not None:
                try:
                    _sb.quit()
                except Exception:
                    pass
                _sb = None
            return (
                f"Error starting browser: "
                f"{e.__class__.__name__} - {str(e).strip()}"
            )


@mcp.tool()
def close_browser() -> str:
    """Close the active browser session and release browser resources.

    Call this when the browser automation workflow is finished. Closing the
    session ends the persistent browser state, including its open tabs,
    cookies, navigation history, and page state. If browser automation is
    needed afterward, start a new session with start_browser.

    This operation is safe to call when no browser session is active.
    """
    global _sb

    if _sb is None:
        return "No browser session is currently running."

    try:
        _sb.quit()
    except Exception as e:
        return (
            "Error calling `quit()` on the browser session: "
            f"{e.__class__.__name__} - {str(e).strip()}"
        )
    finally:
        _sb = None

    return "The browser session was closed."


# ---------------------------------------------------------------------------
# Page information
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def get_page_info() -> dict[str, Any]:
    """Get current browser session and page metadata.

    Use this as the primary tool for determining where the browser currently
    is after navigation, clicks, form submissions, redirects, reloads, or
    tab switches.

    This is a READ-ONLY metadata operation. It does not inspect arbitrary
    page content, find elements, check visibility, wait for conditions, or
    assert expected values.

    Returns:
        A dictionary containing:
        - running: True when browser metadata was successfully retrieved.
          False when no session is available or metadata retrieval failed.
        - url: The complete current page URL, including path and query string.
        - title: The current document title.
        - origin: The current page origin (scheme, host, and port).
        - user_agent: The browser's current User-Agent string.

    Tool selection:
        - Need URL, title, origin, or User-Agent -> use get_page_info.
        - Need visible page text or HTML -> use get_content.
        - Need information about matching elements -> use find_elements.
        - Need an immediate state check -> use check_condition.
        - Need to wait for a condition -> use wait_for.
        - Need to verify an expected condition -> use assert_condition.

    Unlike a dedicated browser-status tool, get_page_info is the single
    source of browser/page metadata. If no browser session is active, it
    returns {"running": False} instead of attempting to access a page.

    This operation does not navigate, reload, click, type, or otherwise
    modify the current page.
    """
    if _sb is None:
        return {"running": False}

    try:
        return {
            "running": True,
            "url": _sb.get_current_url(),
            "title": _sb.get_title(),
            "origin": _sb.get_origin(),
            "user_agent": _sb.get_user_agent(),
        }
    except Exception as e:
        return {
            "running": False,
            "error": f"{e.__class__.__name__}: {str(e).strip()}",
        }


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def navigate(url: str) -> str:
    """Navigate the current browser tab to a URL.

    Use this when the browser needs to visit a new URL rather than move
    through its existing back/forward history.

    If the URL does not include a protocol such as "https://", SeleniumBase
    automatically prefixes "https://" before navigation. For example,
    "seleniumbase.io" becomes "https://seleniumbase.io".

    Navigation waits for the browser's navigation operation to complete
    before returning. Dynamic content may still be loading;
    use wait_for when synchronization is required.

    Args:
        url: Destination URL. May be a complete URL such as
            "https://example.com" or a hostname such as "example.com".

    Returns:
        A confirmation message containing the requested URL.

    Tool selection:
        - Go to a new URL -> use navigate.
        - Return to the previous page -> use manage_history(action="back").
        - Go forward in history -> use manage_history(action="forward").
        - Refresh the current page -> use manage_history(action="reload").
    """
    sb = _get_sb()
    sb.get(url)
    return f"Navigated to {url}"


@mcp.tool()
@handle_sb_errors
def manage_history(
    action: Literal["back", "forward", "reload", "list"] = "list",
) -> str | dict[str, Any]:
    """Manage or inspect the current browser tab's navigation history.

    Use 'back' or 'forward' for history navigation, 'reload' to refresh
    while bypassing the cache, or 'list' to inspect history.
    Use 'navigate' for an arbitrary URL.

    Args:
        action:
            - "back": Go to the previous history entry, if available.
            - "forward": Go to the next history entry, if available.
            - "reload": Reload the current page while ignoring the cache.
            - "list": Return the current history position and entries.

    Navigation actions can trigger page loads or redirects.
    Use get_page_info afterward to verify the resulting URL or title.
    """
    sb = _get_sb()

    if action == "back":
        sb.go_back()
        return "Navigated back."

    if action == "forward":
        sb.go_forward()
        return "Navigated forward."

    if action == "reload":
        sb.reload(ignore_cache=True)
        return "Page reloaded."

    if action == "list":
        position, entries = sb.get_navigation_history()
        return {
            "position": position,
            "entries": [
                {
                    "id": entry.id_,
                    "url": entry.url,
                    "user_typed_url": entry.user_typed_url,
                    "title": entry.title,
                    "transition_type": entry.transition_type.value,
                }
                for entry in entries
            ],
        }

    return (
        f"Error: unknown action '{action}'. "
        "Use 'back', 'forward', 'reload', or 'list'."
    )


# ---------------------------------------------------------------------------
# Finding & reading
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def find_elements(
    selector: str,
    timeout: float = 0.5,
    include_html: bool = False,
) -> dict | str:
    """Find matching elements and return structured element information.

    Use this tool when you need to discover how many elements match a
    selector, inspect their text/tag names, or inspect the HTML of multiple
    matches.

    This tool converts matching elements into ordinary serializable
    dictionaries. It does not return live SeleniumBase element objects.

    Args:
        selector: A SeleniumBase-supported selector, typically CSS or XPath.

        timeout: Maximum number of seconds to wait for at least one matching
            element to appear.

        include_html: If True, include each matching element's outer HTML.
            If False, return only tag name and text.

    Returns:
        A dictionary containing:
        - count: Number of matching elements found.
        - matches: A list of element dictionaries containing tag_name and
          text, plus html when include_html=True.
        If there's an error, returns a string with error details.

    Tool selection:
        - Need structured information about matching elements ->
          use find_elements.
        - Need the visible text/HTML of a page or a single element ->
          use get_content.
        - Need to click one of several matches -> use click with nth.
        - Need to know whether an element is present/visible ->
          use check_condition.

    Note:
        Element handles cannot be persisted across MCP calls. If you find
        elements and then need to act on one, resolve it again with the
        appropriate interaction tool.
    """
    sb = _get_sb()
    elements = sb.find_elements(selector, timeout=timeout)

    if include_html:
        return {
            "count": len(elements),
            "matches": [
                {
                    "tag_name": element.tag_name,
                    "text": element.text,
                    "html": element.get_html(),
                }
                for element in elements
            ],
        }

    return {
        "count": len(elements),
        "matches": [
            {
                "tag_name": element.tag_name,
                "text": element.text,
            }
            for element in elements
        ],
    }


@mcp.tool()
@handle_sb_errors
def get_content(
    selector: str | None = None,
    output_format: Literal["text", "html", "urls"] = "text",
    include_shadow_dom: bool = True,
) -> str | list[str]:
    """Read visible text, HTML, or discovered URLs from the current page.

    Use this tool when you need actual page content or URL information rather
    than page metadata.

    Args:
        selector: Optional CSS selector or SeleniumBase text-matching selector
            identifying the element whose content should be read. For
            output_format="text" or "html", the selector scopes the returned
            content to that element. For output_format="urls", the selector
            scopes URL discovery to URLs within that element. When omitted,
            the operation applies to the whole page.

        output_format:
            - "text": Return visible text from the page or selected element.
            - "html": Return HTML from the page or selected element.
            - "urls": Return URLs discovered by SeleniumBase from the page
              or selected element. URLs associated with elements such as
              anchors, links, images, scripts, and metadata may be included.
              SeleniumBase returns full URLs with their URL protocol prefixes.

        include_shadow_dom: When output_format="html" and selector is omitted,
            include any shadow-root HTML present in the page. This option has
            no effect for "text" or "urls", or when a selector is specified.

    Returns:
        For output_format="text", a string containing visible text.
        For output_format="html", a string containing HTML.
        For output_format="urls", a list of URL strings. This is useful for
        crawling, link discovery, resource inspection, and finding candidate
        URLs before navigating to them.

    Tool selection:
        - Need URL, title, origin, or User-Agent -> use get_page_info.
        - Need visible text -> use output_format="text".
        - Need page or element HTML -> use output_format="html".
        - Need URLs from the page or an element -> use output_format="urls".
        - Need structured information about matching elements ->
          use find_elements.
        - Need to check element presence/visibility -> use check_condition.
        - Need to wait for content to appear -> use wait_for.
    """
    sb = _get_sb()

    if output_format == "urls":
        return sb.get_all_urls(selector=selector)

    if selector is None:
        if output_format == "html":
            return sb.get_page_source(
                include_shadow_dom=include_shadow_dom
            )
        return sb.get_text("body")

    if output_format == "html":
        return sb.get_element_html(selector)

    return sb.get_text(selector)


@mcp.tool()
@handle_sb_errors
def get_attributes(
    selector: str,
    attribute: str | None = None,
) -> Any:
    """Read HTML attributes from a matching element.

    Use this tool when you need the value of one or more HTML attributes
    such as href, src, value, class, id, name, type, aria-label, or data-*.

    Args:
        selector: CSS selector or SeleniumBase text-matching selector for
            the target element.

        attribute: Specific HTML attribute to retrieve. When omitted, return
            all HTML attributes of the element as a dictionary.

    Returns:
        The requested attribute value, or a dictionary containing all
        HTML attributes of the element when attribute is omitted.

    Tool selection:
        - Need one or more HTML attribute values from a specific element ->
          use this tool.
        - Need to discover multiple matching elements or inspect their text ->
          use 'find_elements'.
        - Need visible text or HTML content -> use 'get_content'.
        - Need to check element presence/visibility -> use 'check_condition'.

    This is a read-only operation.
    """
    sb = _get_sb()

    if attribute:
        return sb.get_attribute(selector, attribute)

    return sb.get_element_attributes(selector)


@mcp.tool()
@handle_sb_errors
def check_condition(
    check: Literal["present", "visible"] = "visible",
    selector: str = "body",
    text: str | None = None,
) -> bool | str:
    """Check the current state of an element or text without waiting
    for the condition to become true.

    Use this tool when you need an immediate boolean observation of the current
    page state. Use wait_for when the condition may become true later and the
    workflow should wait for it. Use assert_condition when the condition is an
    expected requirement and failure should be treated as an assertion error.

    Args:
        check:
            The element state to inspect when text is not provided:
            - "present": Return True when at least one matching element exists.
            - "visible": Return True when the matching element is visible.
            `check` is ignored when `text` is provided.

        selector:
            CSS selector or SeleniumBase selector identifying the element.

        text:
            Optional text to check for visibility within `selector`. When
            provided, this takes precedence over `check`; the tool checks text
            visibility instead of element presence or visibility. Use this when
            the question is "Is this text currently visible?" rather than
            whether the element itself is present or visible.

    Returns:
        True or False indicating whether the requested condition is currently
        satisfied. Missing elements return False rather than raising an
        exception. If there's an error, returns a string with error details.

    Tool selection:
        - Immediate boolean observation -> use check_condition.
        - Wait for a state/content transition -> use wait_for.
        - Verify an expected condition -> use assert_condition.
        - Need element details of matching elements -> use find_elements.
        - Need to read page or element content -> use get_content.

    Notes:
        This tool does not intentionally wait for elements or text to appear.
        It is intended for checking the current state only. If page timing or
        asynchronous loading matters, use wait_for instead.

        When `text` is provided, `check` is ignored.
    """
    sb = _get_sb()

    if text:
        return sb.is_text_visible(text, selector)

    if check == "present":
        return sb.is_element_present(selector)

    if check == "visible":
        return sb.is_element_visible(selector)

    return (
        f"Error: Unknown check {check!r}. Use 'present' or 'visible'."
    )


# ---------------------------------------------------------------------------
# Interacting with elements
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def click(
    selector: str,
    nth: int | None = None,
    all_matches: bool = False,
    only_if_visible: bool = False,
    parent_selector: str | None = None,
    timeout: float = 5,
    scroll: bool = True,
) -> str:
    """Click element(s) matching a CSS, XPath, or supported text selector.

    Use this tool for normal clicks, clicking a specific matching occurrence,
    clicking all visible matches, conditional clicks, or clicks scoped to a
    parent element.

    Selection behavior:
    - `nth` is 1-based and takes precedence over every other click mode.
    - Otherwise, `all_matches=True` clicks every currently visible match.
    - Otherwise, `only_if_visible=True` clicks only if a match is visible.
    - Otherwise, `parent_selector` scopes the click to a nested element.
    - With none of the above, performs a normal SeleniumBase click.

    Args:
        selector: CSS selector, XPath selector, or supported SeleniumBase
            text-matching selector. Text-matching selectors such as
            `a:contains("Sign in")` are supported only for single-element
            clicks; do not use them with `all_matches=True`.

        nth: 1-based occurrence to click when multiple elements match.
            Must be >= 1. Takes precedence over `all_matches`,
            `only_if_visible`, and `parent_selector`.

        all_matches: If True, click every currently visible matching element
            in order of appearance. Ignored when `nth` is provided. Use only
            when multiple clicks are intentionally desired, such as for
            clicking all the checkboxes in a section of a webpage.
            If a click induces page navigation, then subsequent clicks are
            cancelled.

        only_if_visible: If True, click only when the target is already
            visible; do not wait for it to become visible.

        parent_selector: CSS/XPath selector for the parent/container in which
            to find `selector`. Used only for the nested-click mode.
            Can be used to click an element inside a parent iframe.

        timeout: Maximum seconds to wait for a normal click operation.
            Default: 5. Not used by conditional or bulk click modes.

        scroll: If True, scroll the target into view before a normal or
            indexed click. Default: True.

    Examples:
        - Click one element: `click("button.submit")`
        - Click the 2nd matching element: `click("button", nth=2)`
        - Click all visible matches: `click(".dismiss", all_matches=True)`
        - Click only if already visible: `click("#menu", only_if_visible=True)`
        - Click inside a container: `click(".item", parent_selector="#result")`
    """
    sb = _get_sb()

    if nth is not None:
        if nth < 1:
            return "Error: nth must be >= 1."
        sb.click_nth_element(selector, nth, scroll=scroll)
        return f"Clicked match #{nth} of {selector}"

    if all_matches:
        sb.click_visible_elements(selector)
        return f"Clicked all visible matches of {selector}"

    if only_if_visible:
        sb.click_if_visible(selector)
        return f"click (only_if_visible) ran for {selector}"

    if parent_selector:
        sb.nested_click(parent_selector, selector)
        return f"Clicked {selector} inside {parent_selector}"

    sb.click(selector, timeout=timeout, scroll=scroll)
    return f"Clicked {selector}"


@mcp.tool()
@handle_sb_errors
def hover_action(
    selector1: str,
    selector2: str | None = None,
    action: Literal[
        "none",
        "click",
        "drag_and_drop",
    ] = "none",
) -> str:
    """Hover over an element, optionally click another, or drag-and-drop.

    Use this tool for hover interactions, hover-triggered menus, and
    drag-and-drop operations.

    Args:
        selector1:
            The primary element selector.
            For action="none", this is the element to hover over.
            For action="click", this is the element to hover over before
            clicking selector2.
            For action="drag_and_drop", this is the draggable source element.

        selector2:
            The secondary element selector.
            Required for action="click", where it identifies the element
            revealed or targeted after hovering selector1.
            Required for action="drag_and_drop", where it identifies the
            destination/drop target.
            Not used for action="none".

        action:
            - "none": Hover over selector1 only.
            - "click": Hover over selector1, then click selector2.
            - "drag_and_drop": Drag selector1 and drop it onto selector2.

    Returns:
        A confirmation message describing the performed operation.

    Tool selection:
        - Simple hover -> action="none".
        - Hover over one element and then click another -> action="click".
        - Drag one element onto another -> action="drag_and_drop".

    Notes:
        For action="click", selector1 is the hover target and selector2 is
        the click target.

        For action="drag_and_drop", selector1 is the source and selector2
        is the destination.
    """
    sb = _get_sb()

    if action == "none":
        sb.hover_element(selector1)
        return f"Hovered {selector1}"

    if action == "click":
        if selector2 is None:
            return "Error: action='click' requires selector2."
        sb.hover_and_click(selector1, selector2)
        return f"Hovered {selector1} and clicked {selector2}"

    if action == "drag_and_drop":
        if selector2 is None:
            return "Error: action='drag_and_drop' requires selector2."
        sb.drag_and_drop(selector1, selector2)
        return f"Dragged {selector1} onto {selector2}"

    return (
        f"Error: unknown action '{action}'. "
        "Use 'none', 'click', or 'drag_and_drop'."
    )


@mcp.tool()
@handle_sb_errors
def type_text(
    selector: str,
    text: str = "",
    mode: Literal[
        "fill_input",
        "append",
        "fast_type",
        "set_value",
        "clear_only",
    ] = "fill_input",
    timeout: float = 5,
) -> str:
    """Enter, append, directly set, or clear text or values on page elements.

    Use this for text entry and direct value changes on supported page
    elements, including inputs, textareas, contenteditable elements,
    and input sliders.

    Args:
        selector: CSS selector or SeleniumBase selector identifying the target.

        text: Text to enter or set. Ignored when mode="clear_only".

        mode:
            - "fill_input": Clear the field and type text normally.
            - "append": Keep the existing value and add text as keystrokes.
            - "fast_type": Clear the field and type text without pauses.
            - "set_value": Set the value directly without simulating
              key events. Useful for fast form filling and input sliders.
            - "clear_only": Empty the field; `text` is ignored.

        timeout: Maximum seconds to wait for the target element.
    """
    sb = _get_sb()

    if mode == "fill_input":
        sb.type(selector, text, timeout=timeout)
    elif mode == "append":
        sb.send_keys(selector, text, timeout=timeout)
    elif mode == "fast_type":
        sb.fast_type(selector, text, timeout=timeout)
    elif mode == "set_value":
        sb.set_value(selector, text, timeout=timeout)
    elif mode == "clear_only":
        sb.clear_input(selector, timeout=timeout)
    else:
        return (
            f"Error: unknown mode '{mode}'. "
            "Use 'fill_input', 'append', 'fast_type', "
            "'set_value', or 'clear_only'."
        )

    return f"type_text(mode={mode!r}) done for {selector}"


@mcp.tool()
@handle_sb_errors
def select_option(
    dropdown_selector: str,
    value: str | int,
    by: Literal["text", "value", "index"] = "text",
) -> str:
    """Select an option from an HTML <select> dropdown.

    Args:
        dropdown_selector: CSS selector identifying the <select> element.

        value: The option's visible text, its HTML value attribute, or its
            0-based index, depending on by.

        by:
            - "text": Match the option's visible text.
            - "value": Match the option's HTML value attribute.
            - "index": Match the option's 0-based position. Both integer and
              numeric-string values are accepted.

    Raises:
        An error when the dropdown or requested option cannot be found.

    This tool is for native <select> elements. For custom JavaScript
    dropdowns made from div/button/list elements, use click or other
    element-interaction tools instead.
    """
    sb = _get_sb()

    if by == "text":
        sb.select_option_by_text(dropdown_selector, str(value))
    elif by == "value":
        sb.select_option_by_value(dropdown_selector, str(value))
    elif by == "index":
        sb.select_option_by_index(dropdown_selector, int(value))
    else:
        return f"Error: unknown by='{by}'. Use 'text', 'value', or 'index'."

    return f"Selected ({by}={value!r}) in {dropdown_selector}"


@mcp.tool()
@handle_sb_errors
def focus(
    selector: str,
    action: Literal[
        "scroll_to_element",
        "focus",
        "highlight",
    ] = "scroll_to_element",
) -> str:
    """Scroll to, focus, or highlight an element.

    This tool does not click, type, select, hover, or otherwise activate the
    element. Use `click`, `type_text`, or `hover_action` for those operations.

    Args:
        selector: CSS selector or SeleniumBase selector identifying the target.

        action:
            - "scroll_to_element": Scroll the element into the viewport.
            - "focus": Move keyboard focus to the element.
            - "highlight": Temporarily highlight the element for debugging or
              demonstration. May affect timing and reduce stealth.
    """
    sb = _get_sb()

    if action == "scroll_to_element":
        sb.scroll_into_view(selector)
    elif action == "focus":
        sb.find_element(selector).focus()
    elif action == "highlight":
        sb.highlight(selector)
    else:
        return (
            f"Error: unknown action '{action}'. "
            "Use 'scroll_to_element', 'focus', or 'highlight'."
        )

    return f"{action} done for {selector}"


# ---------------------------------------------------------------------------
# Waiting & assertions
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def wait_for(
    state: Literal[
        "present",
        "visible",
        "not_visible",
        "absent",
        "seconds_passed",
    ] = "visible",
    selector: str | None = None,
    text: str | None = None,
    timeout: float = 5,
) -> str:
    """Wait until an element or text reaches a requested state, or wait for
    a specific amount of time to pass.

    If 'seconds_passed' is selected for `state`, then this tool ignores any
    values set for 'selector' and 'text', and then waits for full `timeout`
    seconds (blocking behavior).

    When `text` is provided, `present` is treated the same as `visible`
    (the tool waits until the text is visible), and `absent` is treated the
    same as `not_visible` (the tool waits until the text is no longer visible).

    Use this tool when the page is dynamic and an automation step must wait
    for a condition before continuing.

    Unlike check_condition, this tool intentionally waits.
    Unlike assert_condition, its purpose is synchronization
    rather than validating a test expectation.

    Args:
        state:
            - "present": Wait until the matching element exists.
            - "visible": Wait until the matching element is visible.
            - "not_visible": Wait until the matching element is not visible.
            - "absent": Wait until the matching element no longer exists.
            - "seconds_passed": Wait until the `timeout` seconds have passed.

        selector: CSS selector or SeleniumBase selector for the element.
            Required unless `text` is supplied or `seconds_passed` is set.

        text: If supplied and is non-empty, a `state` of 'present' or 'visible'
            both wait for the text to appear within the selector, and a `state`
            of 'not_visible' or 'absent' both wait for the text to be absent
            from the selector (or within "body" when selector is omitted).

        timeout: Maximum seconds to wait for the requested state to be true.

    Returns:
        A confirmation message when the requested condition is reached.

    Tool selection:
        - Check current state immediately -> use check_condition.
        - Wait for a condition to become true -> use wait_for.
        - Verify an expected value/condition -> use assert_condition.
    """
    sb = _get_sb()

    if state != "seconds_passed" and not selector and not text:
        return (
            "Error: `selector` and `text` cannot both be empty "
            "unless 'state' is set to 'seconds_passed'."
        )

    if timeout < 0:
        return "Error: timeout must be >= 0."

    if state == "seconds_passed":
        # This ignores any values that are set for 'selector' or 'text'.
        sb.sleep(timeout)
        return f"Waited for {timeout}s"

    if text:
        if state in ("present", "visible"):
            sb.wait_for_text(text, selector or "body", timeout=timeout)
            return f"Text '{text}' found in {selector or 'the page'}."
        if state in ("absent", "not_visible"):
            sb.wait_for_text_not_visible(
                text, selector or "body", timeout=timeout
            )
            return f"Text '{text}' not found in {selector or 'the page'}."

    if state == "present":
        sb.wait_for_element_present(selector, timeout=timeout)
    elif state == "visible":
        sb.wait_for_element_visible(selector, timeout=timeout)
    elif state == "not_visible":
        sb.wait_for_element_not_visible(selector, timeout=timeout)
    elif state == "absent":
        sb.wait_for_element_absent(selector, timeout=timeout)
    else:
        return (
            f"Error: unknown state '{state}'. "
            "Use 'present', 'visible', 'not_visible', 'absent' "
            "or 'seconds_passed'."
        )

    return f"Element {selector} reached state '{state}'."


@mcp.tool()
@handle_sb_errors
def assert_condition(
    check: Literal[
        "element_present",
        "element_visible",
        "text_visible",
        "title",
        "url",
        "url_contains",
    ] = "element_visible",
    selector: str | None = None,
    expected: str | None = None,
    exact: bool = False,
    timeout: float = 5,
) -> str:
    """Verify an expected browser condition and fail when it is not met.

    Use this tool for explicit verification. Unlike check_condition,
    which simply reports True or False on the current state,
    assert_condition treats a failed expectation as an error.
    The timeout applies only to element and text checks.
    The title and URL checks are immediate.

    Args:
        check:
            - "element_present": Verify selector identifies a present element.
            - "element_visible": Verify selector identifies a visible element.
            - "text_visible": Verify expected text is visible within selector,
              or within the whole HTML document when selector is omitted.
            - "title": Verify the exact page title.
            - "url": Verify the exact current URL.
            - "url_contains": Verify that the current URL contains expected.

        selector: Element selector for element_present, element_visible, and
            text_visible checks.

        expected: Expected text/title/URL value for text_visible, title, url,
            and url_contains.

        exact: For check="text_visible", require exact text
            rather than a substring.

        timeout: Maximum seconds to wait for element/text checks.
            (Ignored for title and URL checks.)

    Returns:
        A confirmation message when the expectation passes.

    Raises:
        An assertion-related SeleniumBase exception when the expectation
        fails; the MCP error wrapper converts it to a descriptive result.

    Tool selection:
        - Just inspect current state -> use check_condition.
        - Wait for a condition to become true -> use wait_for.
        - Verify that an expected condition is true -> use assert_condition.
    """
    sb = _get_sb()

    if check in ("element_present", "element_visible") and selector is None:
        return f"Error: check='{check}' requires value for `selector`."

    if check in (
        "text_visible", "title", "url", "url_contains"
    ) and expected is None:
        return f"Error: check='{check}' requires value for `expected`."

    if check == "element_present":
        sb.assert_element(selector, timeout=timeout)
        return f"Confirmed {selector} is present."

    if check == "element_visible":
        sb.assert_element_visible(selector, timeout=timeout)
        return f"Confirmed {selector} is visible."

    if check == "text_visible":
        target = selector or "html"
        if exact:
            sb.assert_exact_text(expected, target, timeout=timeout)
        else:
            sb.assert_text(expected, target, timeout=timeout)
        return f"Confirmed visible text {expected} in {target}."

    if check == "title":
        sb.assert_title(expected)
        return f"Confirmed title is '{expected}'."

    if check == "url":
        sb.assert_url(expected)
        return f"Confirmed URL is '{expected}'."

    if check == "url_contains":
        sb.assert_url_contains(expected)
        return f"Confirmed URL contains '{expected}'."

    return (
        f"Error: unknown check '{check}'. Use 'element_present', "
        "'element_visible', 'text_visible', 'title', 'url', "
        "or 'url_contains'."
    )


# ---------------------------------------------------------------------------
# Cookies & storage
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def manage_cookies(
    action: Literal["get_all", "clear", "save", "load"] = "get_all",
    filename: str = "cookies.txt",
) -> Any:
    """Manage cookies for the current browser session.

    Use this tool to inspect, clear, save, or restore browser cookies. Cookie
    management is useful for inspecting session state, preserving login
    sessions between browser runs, restoring previously saved sessions, or
    resetting website state during testing.

    Args:
        action:
            - "get_all": Return all cookies currently available to the browser,
              including attributes such as name, value, domain, path, expiry,
              and security flags.
            - "clear": Delete all cookies from the current browser session.
            - "save": Save current cookies to filename. The file may be
              created or overwritten.
            - "load": Load cookies from filename into the current browser
              session.

        filename: Filesystem path used by save/load.
            Ignored for get_all and clear.

    Returns:
        "get_all": Current browser cookies.
        "clear": Confirmation that cookies were cleared.
        "save": Confirmation containing the destination filename.
        "load": Confirmation containing the source filename.

    Security:
        Cookie data can contain authentication credentials, session
        identifiers, and other private information. Only inspect, save,
        load, or share cookies when explicitly authorized.

        `filename` is passed to SeleniumBase's cookie persistence methods and
        can access the filesystem available to the MCP server. Use only
        trusted, authorized paths. The save action may overwrite an existing
        file.

    Notes:
        Loading saved cookies does not guarantee restoration of a login.
        Cookies may be expired, invalidated, domain/path restricted, or
        dependent on other browser state. Navigate to the relevant site when
        necessary so the browser has the appropriate origin for the cookies.
    """
    sb = _get_sb()

    if action == "get_all":
        return sb.get_all_cookies()

    if action == "clear":
        sb.clear_cookies()
        return "Cookies cleared."

    if action == "save":
        sb.save_cookies(name=filename)
        return f"Cookies saved to {filename}"

    if action == "load":
        sb.load_cookies(name=filename)
        return f"Cookies loaded from {filename}"

    return (
        f"Error: unknown action '{action}'. "
        "Use 'get_all', 'clear', 'save', or 'load'."
    )


@mcp.tool()
@handle_sb_errors
def manage_storage(
    key: str,
    value: str | None = None,
    storage: Literal["local", "session"] = "local",
    action: Literal["get", "set"] = "get",
) -> Any:
    """Get or set a key in localStorage or sessionStorage.

    Use this tool when the browser workflow needs to inspect or modify
    JavaScript Web Storage belonging to the current page origin.

    Tool selection:
        - Need localStorage/sessionStorage -> use this tool.
        - Need cookies or authentication cookies -> use manage_cookies.
        - Need arbitrary JavaScript or storage operations not covered here ->
          use run_javascript.
        - Need visible page content or HTML -> use get_content.
        - Need an element's HTML attributes -> use get_attributes.

    When not to use:
        - Do not use this tool for HTTP cookies; use manage_cookies instead.
        - Do not use this tool for arbitrary page JavaScript;
          use run_javascript when a higher-level tool is insufficient.
        - Do not use this tool to inspect values from another origin;
          storage is scoped to the current page origin.

    Args:
        key: Storage key to read or modify.

        value: Value to store when action="set". Required for set.

        storage: "local" for localStorage or "session" for sessionStorage.

        action: "get" to read the key or "set" to write the key.

    Returns:
        The stored value for get, or a confirmation message for set.

    Security:
        Web storage can contain authentication tokens, session identifiers,
        and other sensitive application state. Only use this tool with trusted
        sites and authorized MCP clients.

    Notes:
        Storage belongs to the current page origin. Values from one website
        are not generally available to another origin.
    """
    sb = _get_sb()

    if action not in ("get", "set"):
        return "Error: action must be 'get' or 'set'."

    if action == "set" and value is None:
        return "Error: value is required when action='set'."

    if storage == "local":
        if action == "get":
            return sb.get_local_storage_item(key)
        sb.set_local_storage_item(key, value)
        return f"Set localStorage[{key!r}]"

    if storage == "session":
        if action == "get":
            return sb.get_session_storage_item(key)
        sb.set_session_storage_item(key, value)
        return f"Set sessionStorage[{key!r}]"

    return f"Error: unknown storage '{storage}'. Use 'local' or 'session'."


# ---------------------------------------------------------------------------
# Scrolling
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def scroll(
    direction: Literal["up", "down", "top", "bottom"] = "down",
    amount: int = 25,
) -> str:
    """Scroll the current page vertically.

    Args:
        direction:
            - "up": Scroll upward by amount percent of the window height.
            - "down": Scroll downward by amount percent of the window height.
            - "top": Scroll directly to the top; amount is ignored.
            - "bottom": Scroll directly to the bottom; amount is ignored.

        amount: Percentage of the current viewport height used for relative
            up/down scrolling. For example, amount=25 scrolls approximately
            one quarter of the viewport height.

    Values greater than 100 for `amount` are allowed.
    For example, 200 means approximately two viewport heights.

    Use focus(action="scroll_to_element") when the goal is to reveal a
    specific element rather than scroll the page by a relative amount.
    """
    sb = _get_sb()

    if direction in ("up", "down") and amount < 0:
        return "Error: `amount` cannot be negative for 'up' or 'down'."

    if direction == "up":
        sb.scroll_up(amount=amount)
        return f"Scrolled up by {amount}%."
    elif direction == "down":
        sb.scroll_down(amount=amount)
        return f"Scrolled down by {amount}%."
    elif direction == "top":
        sb.scroll_to_top()
        return "Scrolled to the top."
    elif direction == "bottom":
        sb.scroll_to_bottom()
        return "Scrolled to the bottom."
    else:
        return (
            f"Error: unknown direction '{direction}'. "
            "Use 'up', 'down', 'top', or 'bottom'."
        )


# ---------------------------------------------------------------------------
# Windows & tabs
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def manage_window(
    action: Literal[
        "get_rect",
        "set_rect",
        "maximize",
        "minimize",
    ] = "get_rect",
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str | dict[str, Any]:
    """Get or change browser window geometry or state.

    Args:
        action:
            - "get_rect": Return the current window position and size.
            - "set_rect": Set x, y, width, and height. All four are required.
            - "maximize": Maximize the browser window.
            - "minimize": Minimize the browser window.

        x: Horizontal screen position for "set_rect".

        y: Vertical screen position for "set_rect".

        width: Window width for "set_rect".

        height: Window height for "set_rect".

    Use this tool for browser-window geometry and state.
    Use `manage_tabs` for switching between browser tabs.
    """
    sb = _get_sb()

    if action == "get_rect":
        return sb.get_window_rect()

    if action == "set_rect":
        if None in (x, y, width, height):
            return "Error: set_rect requires x, y, width, and height."
        sb.set_window_rect(x, y, width, height)
        return f"Window set to ({x}, {y}, {width}x{height})"

    if action == "maximize":
        sb.maximize()
        return "Window maximized."

    if action == "minimize":
        sb.minimize()
        return "Window minimized."

    return (
        f"Error: unknown action '{action}'. "
        "Use 'get_rect', 'set_rect', 'maximize', or 'minimize'."
    )


@mcp.tool()
@handle_sb_errors
def manage_tabs(
    action: Literal[
        "list",
        "open",
        "switch",
        "switch_newest",
        "close_active",
    ] = "list",
    url: str | None = None,
    tab_index: int | None = None,
    switch_to: bool = True,
) -> str | list[dict[str, Any]]:
    """Manage browser tabs, including opening new ones.

    Use this for listing, opening, switching, or closing tabs.
    Use `navigate` and `manage_history` for navigation within the active tab.

    Args:
        action:
            - "list": Return each tab's index, URL, and title.
              Use this to find the tab_index for "switch".
            - "open": Open a new tab, optionally navigating it to `url`.
            - "switch": Switch to the tab at tab_index from "list".
            - "switch_newest": Switch to the newest tab.
            - "close_active": Close the active tab.

        url: URL for "open".

        tab_index: Tab index from "list" for "switch".

        switch_to: For "open", switch to the new tab when True.

    Tab indexes are session-relative and may change after tabs are opened or
    closed. Use "list" to get current indexes before switching by index.
    """
    sb = _get_sb()

    if action == "list":
        tabs = sb.get_tabs()
        return [
            {
                "index": i,
                "url": getattr(t, "url", None),
                "title": getattr(t, "title", None),
            }
            for i, t in enumerate(tabs)
        ]

    if action == "open":
        sb.open_new_tab(url=url, switch_to=switch_to)
        return f"Opened new tab (url={url!r}, switch_to={switch_to})"

    if action == "switch":
        if tab_index is None:
            return (
                "Error: action='switch' requires tab_index "
                "(see action='list')."
            )

        tabs = sb.get_tabs()

        if tab_index < 0 or tab_index >= len(tabs):
            return (
                f"Error: tab_index={tab_index} out of range. "
                f"Available indexes: 0-{len(tabs) - 1}."
            )

        sb.switch_to_tab(tabs[tab_index])
        return f"Switched to tab {tab_index}"

    if action == "switch_newest":
        sb.switch_to_newest_tab()
        return "Switched to newest tab."

    if action == "close_active":
        sb.close_active_tab()
        return "Closed active tab."

    return (
        f"Error: unknown action '{action}'. Use 'list', 'open', 'switch', "
        f"'switch_newest', or 'close_active'."
    )


# ---------------------------------------------------------------------------
# Captcha solving
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def solve_captcha() -> str:
    """Attempt a SeleniumBase CDP-based CAPTCHA interaction, such as clicking
    a CAPTCHA checkbox, or performing a drag/drop action on a slider CAPTCHA.

    This tool attempts to interact with CAPTCHA controls such as Cloudflare
    Turnstile, reCAPTCHA, hCaptcha, DataDome Slider, or FriendlyCaptcha via
    the Chrome DevTools Protocol (CDP), which is stealthier than JavaScript
    actions because CDP actions can avoid triggering `isTrusted: false`.

    This tool automatically detects the coordinates of CAPTCHA checkboxes
    for determining the correct location to perform the click. If no CAPTCHA
    is detected on the current page, then no click action is performed.

    The tool does not guarantee that the CAPTCHA was solved. Some CAPTCHA
    controls are embedded inside shadow DOM or otherwise do not expose an
    easy success signal. A successful attempt may result in changes to page
    state or browser cookies.

    Tool workflow:
        1. Inspect the webpage with get_content when you need to
           determine whether CAPTCHA-related controls are present.
        2. Call solve_captcha to attempt the CAPTCHA interaction.
        3. Use get_page_info, get_content, check_condition,
           or manage_cookies to inspect resulting page/session state.

    Returns:
        A message confirming that the CAPTCHA interaction was attempted.
        (There's no guarantee that the CAPTCHA challenge was solved.)
    """
    sb = _get_sb()
    sb.solve_captcha()
    return "Attempted CAPTCHA solve."


# ---------------------------------------------------------------------------
# Output & misc
# ---------------------------------------------------------------------------

@mcp.tool()
@handle_sb_errors
def save_output(
    format: Literal["screenshot", "html", "pdf"] = "screenshot",
    filename: str | None = None,
    folder: str | None = None,
) -> str:
    """Save the current browser page as a screenshot, HTML file, or PDF.

    Args:
        format:
            - "screenshot": Save a PNG screenshot.
            - "html": Save the current page source as HTML.
            - "pdf": Save the current page as a PDF.

        filename: Output filename. Defaults to screenshot.png,
            page_source.html, or page.pdf based on `format`.

        folder: Optional destination folder.

    Existing files may be overwritten.
    Use trusted, authorized paths for `filename` and `folder`.
    """
    sb = _get_sb()

    if format == "screenshot":
        name = filename or "screenshot.png"
        sb.save_screenshot(name, folder=folder)
    elif format == "html":
        name = filename or "page_source.html"
        sb.save_page_source(name, folder=folder)
    elif format == "pdf":
        name = filename or "page.pdf"
        sb.save_as_pdf(name, folder=folder)
    else:
        return (
            f"Error: unknown format '{format}'. "
            "Use 'screenshot', 'html', or 'pdf'."
        )

    return f"Saved {format} as {name}"


@mcp.tool()
@handle_sb_errors
def run_javascript(expression: str) -> Any:
    """Evaluate a JavaScript expression in the current page context.

    Use this only when the required browser operation cannot be accomplished
    through the higher-level SeleniumBase tools.

    The expression is evaluated through Chrome DevTools Protocol
    Runtime.evaluate in the currently active page. It executes with access
    to the page's JavaScript context, including DOM APIs, browser storage,
    and other same-origin page resources available to JavaScript.

    Tool selection:
        - Prefer click, type_text, select_option, hover_action,
          focus, scroll, and other higher-level tools for normal browser
          interactions.
        - Prefer get_content, get_attributes, and find_elements for reading
          page content or element information.
        - Prefer manage_storage for ordinary localStorage/sessionStorage
          reads and writes.
        - Prefer manage_cookies for browser cookie operations.
        - Use this tool when a required operation needs arbitrary JavaScript
          that the higher-level tools do not expose.

    Args:
        expression: A JavaScript expression or executable JavaScript code
            evaluated in the current page. It may reference standard browser
            globals such as document and window and may use DOM APIs.

            Examples:
                - "document.title"
                - "document.querySelector('button')?.textContent"
                - "localStorage.getItem('theme')"
                - "document.body.classList.contains('dark')"
                - "document.querySelector('#slider').value = '50'"

            The expression should produce a value when a result is needed.
            JavaScript that returns a Promise is supported and its resolved
            value is returned.

    Returns:
        The JavaScript evaluation result when it can be serialized and
        returned across the MCP boundary. Primitive values, arrays, plain
        objects, and null are generally suitable return values. DOM objects,
        functions, symbols, and other non-serializable JavaScript values may
        not be returned directly; extract the needed property or convert the
        value to a serializable form first.

    Security:
        This provides unrestricted JavaScript execution in the current browser
        page. It can read or modify page data and interact with the page in
        ways that bypass the higher-level tool abstractions. Only expose this
        MCP server to trusted clients.
    """
    sb = _get_sb()
    return sb.evaluate(expression)


def _cleanup_browser():
    global _sb

    if _sb is not None:
        try:
            _sb.quit()
        except Exception:
            pass
        _sb = None


def main():
    atexit.register(_cleanup_browser)
    print(f'Running the "{mcp.name}" server...', file=sys.stderr)

    try:
        mcp.run(transport="stdio")
    except (KeyboardInterrupt, SystemExit):
        print(
            f'\nThe "{mcp.name}" server was stopped.',
            file=sys.stderr,
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
