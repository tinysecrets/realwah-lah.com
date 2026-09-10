"""Shared logic for seeding the `games` collection.

Single source of truth for the seven live game brands. Used by:
  - backend startup (auto-seeds if the collection is empty)
  - scripts/seed_games.py (operator re-run; upserts by stable slug)

The logo URLs point at the self-hosted copies in the frontend's
/game-logos/ assets so the brand art never depends on a third party.
"""

LOGO_BASE = "https://wahlah-deployd.pages.dev"

# slug -> (name, logo_path, game_url, description, accent_color)
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


def build_game_docs():
    """Return the list of game documents for insertion (no _id/slug handling)."""
    docs = []
    for slug, (name, logo_url, game_url, description, accent_color) in GAMES.items():
        docs.append({
            "slug": slug,
            # Stable adapter key — the JIT registration framework and distributor
            # pool both resolve the game to a platform via platform_id (falling
            # back to the Mongo _id). Binding it to the stable slug decouples the
            # platform adapter registry from DB ObjectIds that vary per environment.
            "platform_id": slug,
            "name": name,
            "logo_url": logo_url,
            "game_url": game_url,
            "description": description,
            "accent_color": accent_color,
            "is_active": True,
        })
    return docs


async def ensure_games_seeded(db) -> dict:
    """Insert the seven brands only if the collection is empty. Idempotent.

    Re-running after games already exist (e.g. admin-added extras) is a no-op,
    so it never overwrites operator-managed data.
    """
    count = await db.games.count_documents({})
    if count > 0:
        return {"seeded": False, "reason": "games already present", "count": count}
    docs = build_game_docs()
    await db.games.insert_many(docs)
    return {"seeded": True, "count": len(docs)}


async def upsert_games(db) -> dict:
    """Idempotent upsert-by-slug (used by the operator seed script)."""
    created, updated = 0, 0
    for doc in build_game_docs():
        result = await db.games.update_one(
            {"slug": doc["slug"]},
            {"$set": doc},
            upsert=True,
        )
        if result.upserted_id is not None:
            created += 1
        else:
            updated += 1
    total = await db.games.count_documents({})
    return {"created": created, "updated": updated, "total": total}