# SeleniumBase MCP Servers

Exposes [SeleniumBase](https://github.com/seleniumbase/SeleniumBase)
browser automation as tools over the [Model Context Protocol](https://modelcontextprotocol.io), so any
MCP client (Claude Desktop, Claude Code, etc.) can drive a real browser.

There are **three server variants** in this folder:

| File | Backs onto | Best for |
|---|---|---|
| `cdp_server.py` | `seleniumbase.sb_cdp.Chrome()` (Pure CDP Mode, sync) | Scraping/automation against bot-detection (Cloudflare, etc.) No WebDriver at all. Includes CAPTCHA-solving. |
| `driver_server.py` | `seleniumbase.Driver()` (WebDriver) | General automation with Selenium ecosystem support. |
| `sb_server.py` | `seleniumbase.SB()` (used without `with`, via manual `__enter__`/`__exit__`) | The broadest API surface: Everything `Driver` offers, plus drag-and-drop, MFA-handling, file downloads, etc. Can switch to CDP Mode mid-flow via `activate_cdp_mode` |

All three default `headless=False` — the browser window is visible unless
you pass `headless=True` when starting a session.

Point your MCP client config at whichever `*_server.py` fits the task (see
step 3 below) — or register all three under different names.

## 1. Install

(Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/getting-started/installation/))

```bash
git clone https://github.com/seleniumbase/seleniumbase-mcp.git
cd seleniumbase-mcp
uv sync
```

`uv sync` reads `pyproject.toml`, creates a `.venv/` in this folder, and
installs the two dependencies (`mcp[cli]`, `seleniumbase`) along with this
project itself — which registers three console-script commands via
`[project.scripts]`:

- `seleniumbase-driver`
- `seleniumbase-cdp`
- `seleniumbase-sb`

Each just calls that server file's `main()` function
(`mcp.run(transport="stdio")`). This is what lets `uv run <name>` — no
python path, no venv path, no script path — work as the MCP client command
in steps 3 and 4 below.

```bash
# SeleniumBase's Driver() and SB() formats need a browser driver downloaded:
uv run seleniumbase get chromedriver
# (Not needed for the "seleniumbase-cdp" Pure CDP Mode MCP Server,
#  which doesn't use WebDriver at all.)
```

(No `uv`? A regular `python3 -m venv venv && pip install -e .` works too —
just substitute `python <script>.py` for `uv run <name>` everywhere below,
and use absolute `venv/bin/python` + script paths in your MCP client config
instead of the path-free options.)

## 2. Try it standalone (optional sanity check)

```bash
uv run mcp dev cdp_server.py
```
That opens the MCP Inspector for SeleniumBase's "Pure CDP Mode" MCP Server, where you can test commands ("Tools"). Ctrl+C to exit. The real test is wiring it into a client (next step).

## 3. Connect it to Claude Desktop

Claude Desktop doesn't run from a "project" directory the way Claude Code
does, so a bare `uv run <name>` isn't guaranteed to find this repo. Two
ways to get a stable config:

**Option A — global install (recommended, zero paths anywhere):**

```bash
uv tool install .          # from inside the repo, installs the 3 commands globally
```
This puts `seleniumbase-driver`/`seleniumbase-cdp`/`seleniumbase-sb` on
your `PATH` permanently (run `uv tool ensurepath` once if it warns that its
bin directory isn't on `PATH` yet). Then `claude_desktop_config.json` can
be just:

```json
{
  "mcpServers": {
    "seleniumbase-cdp": { "command": "seleniumbase-cdp" },
    "seleniumbase-driver": { "command": "seleniumbase-driver" },
    "seleniumbase-sb": { "command": "seleniumbase-sb" }
  }
}
```

**Option B — point `uv` at the repo directly (one absolute path, but no
venv/interpreter path to track down, and no separate install step):**

```json
{
  "mcpServers": {
    "seleniumbase-cdp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/seleniumbase-mcp", "run", "seleniumbase-cdp"]
    },
    "seleniumbase-driver": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/seleniumbase-mcp", "run", "seleniumbase-driver"]
    },
    "seleniumbase-sb": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/seleniumbase-mcp", "run", "seleniumbase-sb"]
    }
  }
}
```

The location of `claude_desktop_config.json` depends on your system:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop. You should see a 🔨 tools icon indicating the
server(s) connected, with tools like `start_browser`, `navigate`, `click`,
etc. available. Only keep the entries you actually want — three separate
browser-automation servers is a lot if you only need one.

## 4. Connect it to Claude Code

This repo's `.mcp.json` is checked in and ready to use as-is — no path
editing required, because `uv run <name>` resolves this project from
`pyproject.toml` in the current directory:

```json
{
  "mcpServers": {
    "seleniumbase-cdp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "seleniumbase-cdp"]
    },
    "seleniumbase-driver": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "seleniumbase-driver"]
    },
    "seleniumbase-sb": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "seleniumbase-sb"]
    }
  }
}
```

Claude Code auto-loads `.mcp.json` from the directory you launch `claude`
in, so as long as you run `claude` from inside this repo (or a clone of
it), it just works — identically for every teammate who clones the repo,
with zero machine-specific editing.

If you'd rather register the servers manually instead of relying on
`.mcp.json`:

```bash
claude mcp add seleniumbase-cdp -- uv run seleniumbase-cdp
claude mcp add seleniumbase-driver -- uv run seleniumbase-driver
claude mcp add seleniumbase-sb -- uv run seleniumbase-sb
```
(run from inside the repo directory, for the same reason as above.)

## Tools exposed (driver_server.py)

| Tool | Purpose |
|---|---|
| `start_browser(browser, headless, uc, incognito)` | Launch a browser session (headless defaults to `False`) |
| `close_browser()` | End the session |
| `navigate(url)` | Go to a URL |
| `go_back()` / `go_forward()` / `refresh_page()` | History navigation |
| `get_current_url()` / `get_title()` | Page metadata |
| `get_page_source()` | Full HTML |
| `get_text(selector)` | Visible text of an element |
| `find_elements_count(selector)` | Count matches |
| `is_element_visible(selector)` | Visibility check |
| `click(selector, by)` | Click (CSS or XPath) |
| `type_text(selector, text, clear_first)` | Fill a field |
| `select_option(selector, option_text)` | Choose a dropdown option |
| `wait_for_element(selector, timeout)` | Explicit wait |
| `switch_to_frame(selector)` / `switch_to_default_content()` | iframe handling |
| `assert_text(text, selector)` | Verify text is present |
| `screenshot(filename)` | Save a screenshot |
| `execute_script(script)` | Run a JS script |

## Design notes / things to adapt for your use case

- **Single global session.** Each server holds one browser session at a
  time. This matches how MCP servers are typically launched (one process
  per client connection) and keeps the tool surface simple. If you need
  multiple concurrent browser tabs/sessions, you'd extend this to a
  dict of named sessions and add a `session_id` parameter to each tool.
- **Blocking calls.** SeleniumBase's calls are synchronous and will block
  the server while a page loads or an element is waited on. For a
  single-user local tool this is fine; for a multi-client server you'd
  want to run them in a thread pool via `asyncio.to_thread`.
- **Headless vs Headed.** Default is headed (`headless=False`) so you can
  watch the browser work and so sites that block headless Chrome still
  function. Pass `headless=True` for background/server use once you've
  confirmed a flow works. `sb_server.py`'s `uc=True` (undetected-
  chromedriver) also helps against bot-detection walls.

## Extending

Adding a tool is just adding a `@mcp.tool()`-decorated function that calls
the matching SeleniumBase method — SeleniumBase has methods for file
uploads, hovering, alerts, network conditions, and more that aren't wrapped
above yet.

---

## cdp_server.py — Pure CDP Mode

Wraps `seleniumbase.sb_cdp.Chrome`, SeleniumBase's stealthiest mode: the
browser is driven entirely over the Chrome DevTools Protocol, no WebDriver
in the loop at all. Reference:
[cdp_mode_methods.md](https://github.com/seleniumbase/SeleniumBase/blob/master/help_docs/cdp_mode_methods.md).

### Tool groups

| Group | Examples |
|---|---|
| Session | `start_browser(url, headless, incognito, guest, proxy, ad_block)`, `close_browser` |
| Navigation | `navigate`, `reload_page`, `go_back`/`go_forward`, `get_current_url`, `get_title` |
| Finding & reading | `find_element_info`, `find_all_info`, `get_text`, `get_html_source`, `get_element_attribute(s)`, `is_element_present/visible` |
| Interacting | `click`, `click_if_visible`, `click_visible_elements`, `type_text`, `send_keys`, `set_value`, `select_option_by_text/value/index`, `nested_click` |
| Waiting | `wait_for_element`, `wait_for_element_visible/not_visible/absent`, `wait_for_text` |
| Assertions | `assert_element`, `assert_text`, `assert_exact_text`, `assert_title`, `assert_url(_contains)` |
| Cookies & storage | `get_all_cookies`, `save_cookies`/`load_cookies`, `get/set_local_storage_item`, `get/set_session_storage_item` |
| Scrolling | `scroll_into_view`, `scroll_to_top/bottom`, `scroll_up/down` |
| Tabs & windows | `open_new_tab`, `switch_to_tab`/`switch_to_newest_tab`, `close_active_tab`, `maximize`/`minimize`, `get/set_window_rect` |
| Captcha | `solve_captcha` |
| Output | `save_screenshot`, `save_page_source`, `save_as_pdf`, `evaluate` |

### CDP-specific design notes

- **Elements don't cross the wire as handles.** In native CDP Mode,
  `find_element()` returns a live object with its own methods
  (`el.click()`, `el.get_html()`, ...). MCP tools can only return
  JSON-serializable data, so `find_element_info`/`find_all_info` resolve
  the element immediately to a plain dict (`tag_name`, `text`, `html`)
  instead of returning a handle you could call further methods on. If you
  need to act on one of several matches, use `click_nth_element` (acts by
  position) rather than "find, then click" as two separate steps.
- **Captcha solving isn't universal.** `solve_captcha` handles supported
  challenge types (e.g. Cloudflare Turnstile in the SeleniumBase demo
  app); it isn't a guaranteed bypass for arbitrary CAPTCHAs.
- **Session teardown.** `sb.quit()` (used by `close_browser`) is the
  documented way to end a session; the browser also auto-closes if the
  process exits without it.
- **Not wrapped:** PyAutoGUI-based `gui_*` methods (excluded by design —
  see the top-level design notes), low-level plumbing
  (`get_websocket_url`, `add_handler`, permission grants, raw
  `get_document`/`get_flattened_document`), and exact method aliases
  (`open`/`goto` vs `get`) were left out to keep the tool list focused —
  add them the same way as any other tool if you need them.

---

## sb_server.py — SB() without the `with` statement

Wraps `seleniumbase.SB()`, normally used as a context manager:

```python
with SB(uc=True) as sb:
    sb.goto(...)
```

An MCP server's tool calls happen one at a time across separate function
invocations — there's no single indented block to put `with` around — so
this server calls the context manager protocol manually instead:

```python
sb_context = SB(**kwargs)
sb = sb_context.__enter__()   # in start_browser
...
sb_context.__exit__(None, None, None)   # in close_browser
```

`sb` is a `BaseCase` instance, SeleniumBase's broadest API — a superset of
what `Driver` (in `driver_server.py`) exposes, plus UC Mode stealth helpers
and a few extras `driver_server.py`/`cdp_server.py` don't have. This server
focuses on those extras rather than re-wrapping everything already covered:

| Group | Tools |
|---|---|
| UC/CDP stealth | `activate_cdp_mode` (flips the *same* session into Pure CDP Mode mid-flow) |
| Extra interactions | `hover_and_click`, `drag_and_drop`, `double_click`, `context_click`, `choose_file` (upload) |
| MFA | `get_mfa_code`, `enter_mfa_code` (TOTP/Google-Authenticator-style codes from a secret key) |
| Files | `download_file` |
| Site health | `assert_no_404_errors`, `assert_no_js_errors` |
| Visual feedback | `highlight`, `flash` |

Plus the same core navigation/interaction/waiting/assertions/cookies/
scrolling/tabs/output tools as the other two servers, called through the
`BaseCase` method names (e.g. `sb.goto`, `sb.click`, `sb.assert_element`)
rather than `Driver`'s or CDP's.

### SB()-specific design notes

- **UC Mode (stealth mode) requires `uc=True` at startup.**
  Pass it in `start_browser` up front if you'll need them.
- **`activate_cdp_mode` doesn't start a new session.** It switches the
  *existing* `sb` session's underlying mode to Pure CDP for subsequent
  actions — it's a mid-flow escalation, not a fresh browser.
