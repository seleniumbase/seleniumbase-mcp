import asyncio
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVERS = [
    ("seleniumbase-cdp", "seleniumbase-cdp"),
    ("seleniumbase-driver", "seleniumbase-driver"),
    ("seleniumbase-sb", "seleniumbase-sb"),
]


async def test_server(name: str, command: str) -> None:
    params = StdioServerParameters(
        command="uv",
        args=["run", command],
    )

    print(f'Starting test for the "{name}" server...')

    async with Client(stdio_client(params)) as client:
        result = await client.list_tools()
        tools = {tool.name for tool in result.tools}

        assert "start_browser" in tools
        assert "close_browser" in tools
        assert "navigate" in tools
        assert "get_title" in tools

        result = await client.call_tool(
            "start_browser",
            {"headless": True},
        )
        assert not result.is_error

        result = await client.call_tool(
            "navigate",
            {
                "url": (
                    "data:text/html,"
                    "<html><head><title>MCP Test</title></head>"
                    "<body><h1>Hello MCP</h1></body></html>"
                )
            },
        )
        assert not result.is_error

        result = await client.call_tool("get_title", {})
        assert not result.is_error
        assert result.content[0].text == "MCP Test"

        result = await client.call_tool(
            "assert_text",
            {"text": "Hello MCP"},
        )
        assert not result.is_error

        result = await client.call_tool("close_browser", {})
        assert not result.is_error

    print(f"{name}: OK")


async def main() -> None:
    for name, command in SERVERS:
        await test_server(name, command)


if __name__ == "__main__":
    asyncio.run(main())
