"""Operator re-run of the `games` seed.

Startup auto-seeds only when the collection is empty. This script forces an
idempotent upsert by stable slug so an operator can refresh logo URLs / names
after the fact.

Usage:
    python scripts/seed_games.py

Env:
    MONGO_URL        (or MONGODB_URI / MONGO_URI) — Mongo connection
    DB_NAME          defaults to "wahlah_prod"
"""
import os

from motor.motor_asyncio import AsyncIOMotorClient

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_seed import GAMES, upsert_games  # noqa: E402


def _mongo_uri() -> str:
    for var in ("MONGO_URL", "MONGODB_URI", "MONGO_URI"):
        val = os.getenv(var)
        if val:
            return val
    raise SystemExit("MONGO_URL (or MONGODB_URI / MONGO_URI) is required.")


async def main() -> None:
    client = AsyncIOMotorClient(_mongo_uri())
    db = client[os.getenv("DB_NAME", "wahlah_prod")]

    print("Seeding games up by slug...")
    for slug, (name, logo_url, *_rest) in GAMES.items():
        print(f"  {name:<15} -> {logo_url}")

    summary = await upsert_games(db)
    print(
        f"\nDone. Created {summary['created']}, updated {summary['updated']}. "
        f"Total games: {summary['total']}"
    )
    await client.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())