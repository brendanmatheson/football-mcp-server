import os
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def main():
    transport = StreamableHttpTransport(
        url="https://football-mcp-server-production.up.railway.app/mcp",
        headers={"X-API-Key": os.environ["FOOTBALL_MCP_API_KEY"]}
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        print(f"Connected: {len(tools)} tools available")

asyncio.run(main())