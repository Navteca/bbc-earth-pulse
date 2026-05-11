"""
Entry point: uv run python -m earth_pulse.server
"""

from __future__ import annotations

import uvicorn
from openai import AsyncOpenAI

from earth_pulse.config import load_settings
from earth_pulse.db import SQLiteAdapter
from earth_pulse.server import create_app
from earth_pulse.temporal.synthesis import SynthesisEngine


def main() -> None:
    settings = load_settings()
    db = SQLiteAdapter(settings.database.url)
    db.migrate()
    openai_client = AsyncOpenAI(api_key=settings.openai.api_key)
    synthesis = SynthesisEngine(openai_client, settings.openai.chat_model)
    app = create_app(settings, db, synthesis)
    uvicorn.run(app, host=settings.server.host, port=settings.server.port)


if __name__ == "__main__":  # pragma: no cover
    main()
