"""Seed the `games` collection with the seven live game brands.

Each brand userped by a stable `slug` so re-running this script is
idempotent: existing rows are updated in place rather than duplicated.

Usage:
    python scripts/seed_games.py

Env:
    MONGO_URL        (or MONGODB_URI / MONGO_URI) — Mongo connection
    DB_NAME          defaults to "wahlah_prod"
    GAMES_LOGO_BASE  base URL to the self-hosted logo files; defaults to
                     the live frontend deploy where /game-logos/ is served.
"""
import os

from motor.motor_asyncio import AsyncIOMotorClient


LOGO_BASE = (os.getenv("GAMES_LOGO_BASE") or "https://wahlah-deployd.pages.dev").rstrip("/")

# slug: (name, logo_path, game_url, description, accent_color)
GAMES = {
    "fire_kirin": (
        "Fire Kirin",
        f"{LOGO_BASE}/game-logos/fire-kirin.png",
        "https://firekirincasino.com/",
        "Fire Kirin",
        "#FF5C00",
    ),
    "juwa": (
        "Juwa",
        f"{LOGO_BASE}/game-logos/juwa.png",
        "https://www.juwa777.com/",
        "Juwa",
        "#F7B500",
    ),
    "orion_stars": (
        "Orion Stars",
        f"{LOGO_BASE}/game-logos/orion-stars.png",
        "http://start.orionstars.vip/",
        "Orion Stars",
        "#22C1FF",
    ),
    "ultra_panda": (
        "Ultra Panda",
        f"{LOGO_BASE}/game-logos/ultra-panda.png",
        "https://www.ultrapanda.mobi/",
        "Ultra Panda",
        "#00C896",
    ),
    "panda_master": (
        "Panda Master",
        f"{LOGO_BASE}/game-logos/panda-master.png",
        "https://pandamaster.com/",
        "Panda Master",
        "#B14EFF",
    ),
    "game_vault": (
        "Game Vault",
        f"{LOGO_BASE}/game-logos/game-vault.png",
        "https://gamevaultapps.com/",
        "Game Vault",
        "#FFD23F",
    ),
    "vblink": (
        "vBlink",
        f"{LOGO_BASE}/game-logos/vblink.png",
        "https://www.vblink777.club/",
        "vBlink",
        "#FF3D77",
    ),
}


def _mongo_uri() -> str:
    for var in ("MONGO_URL", "MONGODB_URI", "MONGO_URI"):
        val = os.getenv(var)
        if val:
            return val
    raise SystemExit(
        "MONGO_URL (or MONGODB_URI / MONGO_URI) is required."
    )


async def main() -> None:
    client = AsyncIOMotorClient(_mongo_uri())
    db = client[os.getenv("DB_NAME", "wahlah_prod")]

    created, updated = 0, 0
    for slug, (name, logo_url, game_url, description, accent_color) in GAMES.items():
        doc = {
            "slug": slug,
            "name": name,
            "logo_url": logo_url,
            "game_url": game_url,
            "description": description,
            "accent_color": accent_color,
            "is_active": True,
        }
        result = await db.games.update_one(
            {"slug": slug},
            {"$set": doc},
            upsert=True,
        )
        if result.upserted_id is not None:
            created += 1
        else:
            updated += 1
        print(f"  {name:<15} -> {logo_url}")

    total = await db.games.count_documents({})
    print(f"\nDone. Created {created}, updated {updated}. Total games: {total}")
    await client.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())