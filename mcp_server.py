# -*- coding: utf-8 -*-
"""mcp_server.py — PLACEE registry MCP server（stdio transport）

7個tool對應API endpoint。Claude Desktop 接入（claude_desktop_config.json）：
{
  "mcpServers": {
    "placee-registry": {
      "command": "python",
      "args": ["C:\\...\\hk-placee-registry\\mcp_server.py"],
      "env": { "PLACEE_API_BASE": "http://localhost:8765" }
    }
  }
}
"""
import os

import requests
from mcp.server.fastmcp import FastMCP

BASE = os.environ.get("PLACEE_API_BASE", "http://localhost:8765")

mcp = FastMCP("placee-registry")


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{BASE}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def registry_meta() -> dict:
    """庫概況：db更新時間、承配人行數、具名數、事件數、規則版本。"""
    return _get("/registry/meta")


@mcp.tool()
def registry_name(q: str) -> dict:
    """承配人姓名查詢（中英模糊）。回傳股票、日期、股數、價、%、source_url。"""
    return _get("/registry/name", {"q": q})


@mcp.tool()
def registry_broker(q: str) -> dict:
    """券商CCASS衛星倉flag查詢（broker_id或名稱模糊）。"""
    return _get("/registry/broker", {"q": q})


@mcp.tool()
def registry_stock(code: str) -> dict:
    """單股全部事件＋承配人＋亮燈＋CCASS flag＋結局。code=5位數。"""
    return _get(f"/registry/stock/{code}")


@mcp.tool()
def registry_alerts(since: str = "2000-01-01") -> dict:
    """亮燈事件（ann_date>=since，score>=1）。"""
    return _get("/registry/alerts", {"since": since})


@mcp.tool()
def registry_repeat(min_count: int = 2) -> dict:
    """跨股重複承配人候選（唔代表同一人）。"""
    return _get("/registry/repeat", {"min_count": min_count})


@mcp.tool()
def registry_crash(days: int = 30, threshold: float = -0.5) -> dict:
    """承配後N日內大跌個案（crash_flag或dd<=threshold）。"""
    return _get("/registry/crash", {"days": days, "threshold": threshold})


if __name__ == "__main__":
    mcp.run(transport="stdio")
