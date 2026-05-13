"""
Pure FastMCP / Starlette server — no FastAPI.
MCP endpoint: POST /mcp  (HTTP Streamable, stateless)
Health check:  GET  /health
Auth: Authorization: Bearer <key> required on /mcp paths.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from earth_pulse.config import Settings
from earth_pulse.db import DatabasePort
from earth_pulse.temporal import SynthesisEngine, compute_analytics

# Token bucket parameters (OWASP LLM10 — unbounded consumption)
_RATE_LIMIT_RPS = 1.0          # refill rate: 1 token per second = 60 req/min
_RATE_LIMIT_BURST = 10         # max burst capacity


def create_app(
    settings: Settings, db: DatabasePort, synthesis: SynthesisEngine
) -> object:
    """Return a Starlette ASGI app (via FastMCP) with auth middleware and health route."""
    if not settings.server.api_key:
        raise ValueError(
            "server.api_key is required. "
            "Set it in config.toml or SERVER__API_KEY env var."
        )

    # FastMCP owns /mcp natively — stateless_http=True means no initialize handshake
    # required; every POST to /mcp is self-contained.
    # DNS rebinding protection disabled — we sit behind Cloudflare Tunnel (Host mismatch).
    mcp = FastMCP(
        "earth-pulse",
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    _register_tools(mcp, db, synthesis)
    _fix_tool_schemas(mcp)

    # Health check registered as a Starlette custom route on the FastMCP app.
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Build the raw Starlette app — no FastAPI layer.
    starlette_app = mcp.streamable_http_app()

    # Wrap with auth middleware: guard /mcp paths, pass /health through freely.
    api_key = settings.server.api_key
    starlette_app.add_middleware(_TokenBucketRateLimiter)  # type: ignore[arg-type]
    starlette_app.add_middleware(_AuthMiddleware, api_key=api_key)  # type: ignore[arg-type]

    return starlette_app


class _AuthMiddleware(BaseHTTPMiddleware):
    """Require Bearer token on /mcp paths; pass everything else through."""

    def __init__(self, app: Callable, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        path = request.url.path.rstrip("/")
        if path == "/mcp" or path.startswith("/mcp/"):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Missing or invalid Authorization header"},
                )
            token = auth.removeprefix("Bearer ").strip()
            if token != self._api_key:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid API key"},
                )
        return await call_next(request)


class _TokenBucketRateLimiter(BaseHTTPMiddleware):
    """Token bucket rate limiter on /mcp paths (OWASP LLM10).

    Refills at _RATE_LIMIT_RPS tokens/second up to _RATE_LIMIT_BURST.
    Returns 429 with Retry-After when the bucket is empty.
    Keyed per API key (single bucket in MVP — one key).
    """

    def __init__(self, app: Callable) -> None:
        super().__init__(app)
        # bucket state: {api_key: (tokens, last_refill_time)}
        self._buckets: dict[str, tuple[float, float]] = {}

    def _consume(self, key: str) -> float | None:
        """Consume one token. Returns None on success, or retry_after seconds on failure."""
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (_RATE_LIMIT_BURST, now))
        # Refill
        elapsed = now - last
        tokens = min(_RATE_LIMIT_BURST, tokens + elapsed * _RATE_LIMIT_RPS)
        if tokens < 1.0:
            retry_after = (1.0 - tokens) / _RATE_LIMIT_RPS
            self._buckets[key] = (tokens, now)
            return retry_after
        self._buckets[key] = (tokens - 1.0, now)
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        path = request.url.path.rstrip("/")
        if path == "/mcp" or path.startswith("/mcp/"):
            auth = request.headers.get("Authorization", "")
            key = auth.removeprefix("Bearer ").strip() or "__anonymous__"
            retry_after = self._consume(key)
            if retry_after is not None:
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded"},
                    headers={"Retry-After": str(int(retry_after) + 1)},
                )
        return await call_next(request)


def _fix_tool_schemas(mcp: FastMCP) -> None:
    """Transform all tool schemas to be OpenAI strict-mode compatible.

    OpenAI requires:
    1. Every key in 'properties' listed in 'required'
    2. 'additionalProperties': false on every object
    3. No anyOf/oneOf patterns — collapse 'T | None' to {"type": ["T", "null"]}

    Applied recursively so nested objects and array items are also fixed.
    """
    tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
    for tool in tools.values():
        transformed = _transform_schema(copy.deepcopy(tool.parameters))
        tool.parameters.clear()
        tool.parameters.update(transformed)


def _transform_schema(schema: dict) -> dict:  # type: ignore[type-arg]
    """Recursively transform a JSON schema to be OpenAI strict-mode compatible."""
    if schema.get("type") == "object" or "properties" in schema:
        _transform_object(schema)
    return schema


def _transform_object(obj: dict) -> None:  # type: ignore[type-arg]
    """In-place: fix an object schema and all its properties recursively."""
    props = obj.get("properties", {})
    for prop_schema in props.values():
        _transform_property(prop_schema)
    if props:
        obj["required"] = list(props.keys())
    obj["additionalProperties"] = False


def _transform_property(prop: dict) -> None:  # type: ignore[type-arg]
    """In-place: collapse anyOf/oneOf nullable patterns; recurse into objects/arrays."""
    # Collapse anyOf: [T, null]  →  type: [T, null]
    if "anyOf" in prop:
        types = _extract_types_from_union(prop.pop("anyOf"))
        prop["type"] = types if len(types) > 1 else types[0]

    # Collapse oneOf: [T, null]  →  type: [T, null]
    elif "oneOf" in prop:
        types = _extract_types_from_union(prop.pop("oneOf"))
        prop["type"] = types if len(types) > 1 else types[0]

    # Recurse into nested objects
    if prop.get("type") == "object" or "properties" in prop:
        _transform_object(prop)

    # Recurse into array items
    if prop.get("type") == "array" and isinstance(prop.get("items"), dict):
        _transform_property(prop["items"])


def _extract_types_from_union(variants: list) -> list:  # type: ignore[type-arg]
    """Return a list of type strings from anyOf/oneOf variants."""
    types = []
    for variant in variants:
        t = variant.get("type")
        if t:
            types.append(t)
    return types if types else ["string", "null"]


def _emotion_summary(pairs: list) -> str:  # type: ignore[type-arg]
    """Return a compact aggregate of emotional scores across article/enrichment pairs."""
    if not pairs:
        return "no data"
    count = len(pairs)
    avg = lambda key: sum(getattr(e, key) for _, e in pairs) / count  # noqa: E731
    top_emotions: dict[str, int] = {}
    for _, e in pairs:
        top_emotions[e.emotion] = top_emotions.get(e.emotion, 0) + 1
    dominant = sorted(top_emotions.items(), key=lambda x: x[1], reverse=True)[:3]
    dominant_str = ", ".join(f"{k}({v})" for k, v in dominant)
    return (
        f"n={count}, "
        f"avg_anxiety={avg('anxiety_score'):.2f}, "
        f"avg_optimism={avg('optimism_score'):.2f}, "
        f"avg_conflict={avg('conflict_score'):.2f}, "
        f"avg_stability={avg('stability_score'):.2f}, "
        f"avg_urgency={avg('urgency_score'):.2f}, "
        f"dominant_emotions=[{dominant_str}]"
    )


def _register_tools(mcp: FastMCP, db: DatabasePort, synthesis: SynthesisEngine) -> None:
    @mcp.tool(
        description=(
            "Returns the emotional, geopolitical, and societal mood of humanity or a specific "
            "region, based on enriched news journalism. "
            "Use this tool for questions like: "
            "'What is the emotional mood of Europe?', "
            "'Is global anxiety increasing?', "
            "'How does Asia compare emotionally to North America?', "
            "'What emotions dominate technology news?', "
            "'Is humanity becoming more hopeful?', "
            "'What fears dominate modern society?', "
            "'What signs of optimism appeared this week?'. "
            "region: one of Africa, Asia, Europe, Latin America, Middle East, "
            "North America, Oceania, Global — or null for worldwide. "
            "compare_with: a second region to compare side-by-side. "
            "hours: how far back to look (default 48, use 168 for weekly trends, "
            "720 for monthly)."
        )
    )
    async def query_mood(
        region: str | None = None,
        compare_with: str | None = None,
        hours: int = 48,
    ) -> str:
        now = datetime.now(tz=UTC)
        if compare_with:
            pairs_a = db.get_enriched_articles(region=region, hours=hours)
            pairs_b = db.get_enriched_articles(region=compare_with, hours=hours)
            pairs = pairs_a + pairs_b
            emotion_summary = _emotion_summary(pairs)
            instruction = (
                f"Compare the emotional and geopolitical atmosphere of "
                f"{region or 'the world'} versus {compare_with} "
                f"over the last {hours} hours. "
                "Focus on emotional differences, dominant anxieties, economic outlook, "
                "geopolitical tensions, and societal concerns. "
                f"Aggregate emotional scores across articles: {emotion_summary}. "
                "Use these scores to support your interpretation."
            )
        else:
            pairs = db.get_enriched_articles(region=region, hours=hours)
            emotion_summary = _emotion_summary(pairs)
            scope = region or "humanity globally"
            instruction = (
                f"Interpret the emotional and geopolitical mood of {scope} "
                f"over the last {hours} hours. "
                "Describe the dominant emotions, collective anxieties, signs of hope or tension, "
                "and the overall civilizational atmosphere. "
                f"Aggregate emotional scores across articles: {emotion_summary}. "
                "Use these scores to ground your synthesis — if anxiety_score is high, "
                "describe what is driving it; if optimism_score is rising, describe what "
                "is fueling it."
            )
        analytics = compute_analytics(pairs, period_hours=hours)
        synthesis_text, source_ids = await synthesis.synthesize(
            pairs, instruction, hours=hours, analytics=analytics
        )
        return json.dumps({
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": hours,
        })

    @mcp.tool(
        description=(
            "Returns trend intelligence for a given time window. "
            "Use this tool for questions like: "
            "'What changed in the world today?', "
            "'What stories are dominating global attention?', "
            "'What tensions are increasing?', "
            "'What is humanity collectively obsessed with right now?', "
            "'What topics are accelerating in the news?', "
            "'How has the framing of a topic shifted?'. "
            "hours: time window to analyse (default 24). "
            "mode: 'pulse' = what humanity is focused on right now (default); "
            "'emerging' = topics rapidly accelerating in coverage and urgency; "
            "'shifts' = narratives that have changed direction or been recontextualised."
        )
    )
    async def query_trends(hours: int = 24, mode: str = "pulse") -> str:
        now = datetime.now(tz=UTC)
        pairs = db.get_enriched_articles(hours=hours)
        if mode == "emerging":
            instruction = (
                f"Identify which topics are rapidly accelerating in coverage and urgency "
                f"over the last {hours} hours. What narratives are gaining momentum globally? "
                "What tensions are visibly increasing? "
                "What stories went from background to foreground?"
            )
        elif mode == "shifts":
            instruction = (
                f"Identify significant shifts in how topics are being framed "
                f"over the last {hours} hours. "
                "What narratives have changed direction? What stories are being recontextualised? "
                "What was the dominant framing before, and what is it now?"
            )
        else:
            instruction = (
                f"What is humanity collectively focused on in the last {hours} hours? "
                "What changed? What topics dominate global attention? "
                "What tensions are increasing? What is the pulse of civilisation right now? "
                "Name the dominant stories, the dominant emotions, and the dominant anxieties."
            )
        analytics = compute_analytics(pairs, period_hours=hours)
        synthesis_text, source_ids = await synthesis.synthesize(
            pairs, instruction, hours=hours, analytics=analytics
        )
        return json.dumps({
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": hours,
        })

    @mcp.tool(
        description=(
            "Returns the narrative and emotional evolution of a specific topic over time. "
            "Use this tool for questions like: "
            "'How did AI coverage evolve over the last year?', "
            "'When did inflation become a dominant narrative?', "
            "'How has climate anxiety changed since 2023?', "
            "'How has the tone around the Ukraine conflict shifted?', "
            "'How has coverage of X changed?'. "
            "topic: the subject to trace — e.g. 'AI', 'inflation', 'climate', 'Ukraine'. "
            "since: ISO 8601 date string for the start of the window "
            "(e.g. '2025-01-01T00:00:00Z'). Omit to search all available history. "
            "Data is available from November 2025 onwards."
        )
    )
    async def query_timeline(topic: str, since: str | None = None) -> str:
        now = datetime.now(tz=UTC)
        since_dt: datetime | None = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = None
        pairs = db.get_timeline_articles(topic=topic, since=since_dt)
        period_hours = int((now - since_dt).total_seconds() / 3600) if since_dt else 0
        emotion_summary = _emotion_summary(pairs)
        instruction = (
            f"Trace the narrative and emotional evolution of '{topic}' over time. "
            "How has the coverage, framing, and emotional tone changed across the articles? "
            "What phases has this story gone through? "
            "What turning points are visible in the data? "
            "How has the balance of anxiety, optimism, conflict, and stability shifted? "
            f"Aggregate emotional scores: {emotion_summary}. "
            "Ground your synthesis in these scores."
        )
        analytics = compute_analytics(pairs, period_hours=period_hours)
        synthesis_text, source_ids = await synthesis.synthesize(
            pairs, instruction, hours=period_hours, analytics=analytics
        )
        return json.dumps({
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": period_hours,
        })

    @mcp.tool(
        description=(
            "Resolves a list of article IDs to their source metadata (title and URL). "
            "Use this tool when you have article IDs from a previous tool response and want "
            "to retrieve the original source articles for citation, verification, or display. "
            "ids: list of article ID strings as returned in the 'sources' field of any tool. "
            "Unknown or invalid IDs are silently omitted from the response."
        )
    )
    async def get_sources(ids: list[str]) -> str:
        articles = db.get_articles_by_ids(ids)
        return json.dumps([
            {"id": a.id, "title": a.title, "url": a.url}
            for a in articles
        ])

    @mcp.tool(
        description=(
            "Compares the emotional and geopolitical mood of a region (or the world) "
            "between two time windows — 'now' versus a baseline period in the past. "
            "Use this tool for questions like: "
            "'Is the world more anxious than it was last week?', "
            "'Has European optimism changed since last month?', "
            "'Is Middle East conflict escalating or de-escalating compared to 7 days ago?', "
            "'How has global mood shifted over the past fortnight?'. "
            "region: one of Africa, Asia, Europe, Latin America, Middle East, "
            "North America, Oceania, Global — or null for worldwide. "
            "hours: size of each comparison window in hours (default 24). "
            "compare_days_ago: how many days back to place the baseline window (default 7)."
        )
    )
    async def query_mood_diff(
        region: str | None = None,
        hours: int = 24,
        compare_days_ago: int = 7,
    ) -> str:
        now = datetime.now(tz=UTC)
        baseline_offset = timedelta(days=compare_days_ago)

        # "Now" window: articles from the last `hours` hours.
        pairs_now = db.get_enriched_articles(region=region, hours=hours)

        # "Then" window: articles published within the same `hours`-hour span
        # but anchored `compare_days_ago` days in the past.
        # We fetch a wider window then filter manually so we can reuse the existing DB method.
        then_end = now - baseline_offset
        then_start = then_end - timedelta(hours=hours)
        pairs_raw_then = db.get_enriched_articles(
            region=region,
            hours=int((now - then_start).total_seconds() // 3600) + 1,
        )
        pairs_then = [
            (a, e)
            for a, e in pairs_raw_then
            if then_start <= a.published_at <= then_end
        ]

        analytics_now = compute_analytics(pairs_now, period_hours=hours)
        analytics_then = compute_analytics(pairs_then, period_hours=hours)

        emotion_now = _emotion_summary(pairs_now)
        emotion_then = _emotion_summary(pairs_then)

        scope = region or "humanity globally"
        instruction = (
            f"Compare the emotional and geopolitical mood of {scope} between two periods:\n"
            f"- NOW: the last {hours} hours\n"
            f"- THEN: the same {hours}-hour window {compare_days_ago} days ago\n\n"
            "Use <analytics_now> and <analytics_then> to ground your comparison.\n"
            f"NOW emotional scores: {emotion_now}\n"
            f"THEN emotional scores: {emotion_then}\n\n"
            "Describe: what has changed, what has intensified, what has faded. "
            "Name the dominant shift — is the mood darker, lighter, more conflicted, "
            "more hopeful? What narratives emerged or disappeared? "
            "Be specific about direction and magnitude of change."
        )

        # Synthesise with now-window articles as the primary corpus.
        # Inject both analytics blocks by building a combined XML context.
        now_xml = (
            analytics_now.to_xml_block()
            .replace("<analytics>", "<analytics_now>")
            .replace("</analytics>", "</analytics_now>")
        )
        then_xml = (
            analytics_then.to_xml_block()
            .replace("<analytics>", "<analytics_then>")
            .replace("</analytics>", "</analytics_then>")
        )
        combined_analytics_xml = now_xml + "\n" + then_xml

        # Use a minimal analytics placeholder so synthesis doesn't double-inject;
        # we pass the combined XML as a pre-built override via a thin wrapper.
        class _CombinedAnalytics:
            def to_xml_block(self) -> str:
                return combined_analytics_xml

        synthesis_text, source_ids = await synthesis.synthesize(
            pairs_now + pairs_then,
            instruction,
            hours=hours,
            analytics=_CombinedAnalytics(),  # type: ignore[arg-type]
        )
        return json.dumps({
            "synthesis": synthesis_text,
            "sources": source_ids,
            "generated_at": now.isoformat(),
            "period_hours": hours,
            "compare_days_ago": compare_days_ago,
        })

