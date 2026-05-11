"""
MCP server — 3 tools, HTTP Streamable transport, API key auth.
Mounted at /mcp inside FastAPI.

Tools:
  query_mood(region, compare_with)
  query_trends(hours, mode)
  query_timeline(topic, since)
"""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server import Server
from mcp.types import TextContent, Tool

from earth_pulse.db import DatabasePort
from earth_pulse.temporal.synthesis import SynthesisEngine

_TOOLS: list[Tool] = [
    Tool(
        name="query_mood",
        description=(
            "Returns the emotional and geopolitical mood of humanity or a specific region. "
            "Pass region=None for global mood. "
            "Pass compare_with to compare two regions side-by-side."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "region": {
                    "type": ["string", "null"],
                    "description": (
                        "One of: Africa, Asia, Europe, Latin America, "
                        "Middle East, North America, Oceania, Global. Null for global."
                    ),
                    "default": None,
                },
                "compare_with": {
                    "type": ["string", "null"],
                    "description": "Second region for side-by-side comparison.",
                    "default": None,
                },
            },
        },
    ),
    Tool(
        name="query_trends",
        description=(
            "Returns trend intelligence for a given time window. "
            "mode='emerging' shows accelerating topics, "
            "mode='shifts' shows narrative framing changes, "
            "mode='pulse' shows humanity's current collective focus."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Lookback window in hours.",
                    "default": 24,
                },
                "mode": {
                    "type": "string",
                    "enum": ["emerging", "shifts", "pulse"],
                    "description": "Analysis mode.",
                    "default": "pulse",
                },
            },
        },
    ),
    Tool(
        name="query_timeline",
        description=(
            "Returns the narrative evolution of a topic over time. "
            "Useful for understanding how a story or theme has changed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to trace (e.g. 'AI', 'climate', 'Ukraine').",
                },
                "since": {
                    "type": ["string", "null"],
                    "description": (
                        "ISO 8601 date string to look back from. "
                        "Null for all available history."
                    ),
                    "default": None,
                },
            },
            "required": ["topic"],
        },
    ),
]


def build_mcp_server(db: DatabasePort, synthesis: SynthesisEngine) -> Server:
    server = Server("earth-pulse")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        now = datetime.now(tz=UTC)

        if name == "query_mood":
            return await _query_mood(db, synthesis, arguments, now)
        elif name == "query_trends":
            return await _query_trends(db, synthesis, arguments, now)
        elif name == "query_timeline":
            return await _query_timeline(db, synthesis, arguments, now)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _query_mood(
    db: DatabasePort,
    synthesis: SynthesisEngine,
    args: dict,
    now: datetime,
) -> list[TextContent]:
    import json as _json

    region: str | None = args.get("region")
    compare_with: str | None = args.get("compare_with")
    hours = 48

    if compare_with:
        pairs_a = db.get_enriched_articles(region=region, hours=hours)
        pairs_b = db.get_enriched_articles(region=compare_with, hours=hours)
        instruction = (
            f"Compare the emotional and geopolitical atmosphere of {region or 'the world'} "
            f"versus {compare_with}. Focus on emotional differences, economic outlook, "
            "geopolitical tensions, and societal concerns."
        )
        pairs = pairs_a + pairs_b
    else:
        pairs = db.get_enriched_articles(region=region, hours=hours)
        if region:
            instruction = (
                f"Interpret the emotional and geopolitical mood of {region} "
                "based on recent journalism. Describe the dominant emotions, "
                "concerns, and societal atmosphere."
            )
        else:
            instruction = (
                "Interpret the global emotional and geopolitical mood of humanity "
                "based on recent journalism. Describe the dominant emotions, "
                "collective concerns, and civilizational atmosphere."
            )

    synthesis_text, source_ids = await synthesis.synthesize(pairs, instruction, hours=hours)
    result = _json.dumps(
        {
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": hours,
        }
    )
    return [TextContent(type="text", text=result)]


async def _query_trends(
    db: DatabasePort,
    synthesis: SynthesisEngine,
    args: dict,
    now: datetime,
) -> list[TextContent]:
    import json as _json

    hours: int = int(args.get("hours", 24))
    mode: str = args.get("mode", "pulse")

    pairs = db.get_enriched_articles(hours=hours)

    if mode == "emerging":
        instruction = (
            f"Identify which topics are rapidly accelerating in coverage and urgency "
            f"over the last {hours} hours. What narratives are gaining momentum globally?"
        )
    elif mode == "shifts":
        instruction = (
            f"Identify significant shifts in how topics are being framed "
            f"over the last {hours} hours. "
            "What narratives have changed direction? What stories are being recontextualized?"
        )
    else:  # pulse
        instruction = (
            f"What is humanity collectively focused on in the last {hours} hours? "
            "What changed? What topics dominate global attention? "
            "What is the pulse of civilization right now?"
        )

    synthesis_text, source_ids = await synthesis.synthesize(pairs, instruction, hours=hours)
    result = _json.dumps(
        {
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": hours,
        }
    )
    return [TextContent(type="text", text=result)]


async def _query_timeline(
    db: DatabasePort,
    synthesis: SynthesisEngine,
    args: dict,
    now: datetime,
) -> list[TextContent]:
    import json as _json

    topic: str = args.get("topic", "")
    since_str: str | None = args.get("since")
    since: datetime | None = None
    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
        except ValueError:
            since = None

    pairs = db.get_timeline_articles(topic=topic, since=since)
    period_hours = int((now - since).total_seconds() / 3600) if since else 0

    instruction = (
        f"Trace the narrative evolution of '{topic}' over time. "
        "How has the coverage, framing, and emotional tone changed? "
        "What phases has this story gone through? "
        "What turning points are visible in the data?"
    )

    synthesis_text, source_ids = await synthesis.synthesize(pairs, instruction, hours=period_hours)
    result = _json.dumps(
        {
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": period_hours,
        }
    )
    return [TextContent(type="text", text=result)]
