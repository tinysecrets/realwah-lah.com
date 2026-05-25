"""Generate WAH-LAH branded mascot via Nano Banana."""
import asyncio
import base64
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")

OUT_DIR = Path("/app/backend/static/mascots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS = {
    "wahlah_genie": (
        "A bold Gen-Z style cartoon mascot character named WAH-LAH — a youthful, confident, "
        "mischievous genie emerging from a glowing golden lamp. Big expressive cartoon eyes, "
        "a wide playful smirk showing confidence, neon iridescent skin in electric cyan-to-hot-pink gradient, "
        "wears a tiny cropped gold vest and hoop earring. Holds glowing golden Bitcoin coins and playing cards "
        "in one hand, casting a magenta-cyan sparkle burst with the other. Dynamic pose mid-dance, "
        "hair/flame trail is holographic purple-pink. Thick bold cel-shaded outlines, flat bright cartoon shading, "
        "NOT 3D, NOT realistic. Background: solid pure transparent. Sticker-style mascot. "
        "Style reference: modern Twitch emote / Fortnite skin art / Adidas Originals mascot illustration."
    ),
    "wahlah_genie_winking": (
        "Same WAH-LAH genie mascot as before — cartoon youthful genie, cyan-pink iridescent skin, "
        "gold vest, hoop earring, holographic purple-pink flame trail instead of legs. "
        "This time: winking one eye with a finger-guns pose, tongue out playfully, "
        "throwing confetti and gold coins. Sticker-style, bold cel-shaded outlines, "
        "flat bright cartoon colors. Transparent background. Gen-Z emote energy."
    ),
    "wahlah_coin_buddy": (
        "A small companion cartoon mascot: anthropomorphic gold coin character with a big W-symbol on its face, "
        "cute tiny arms and legs, wearing cyan sunglasses and a tiny gold crown. "
        "Huge expressive smile, dynamic mid-jump pose giving thumbs up. "
        "Cel-shaded cartoon style, bold black outlines, vibrant flat colors — gold body, cyan accents, "
        "hot pink sparkles around. Transparent background. Sticker-style. "
        "Style reference: Duolingo mascot / Discord Wumpus / modern brand character."
    ),
}


async def gen_one(slug: str, prompt: str) -> bool:
    api_key = os.getenv("EMERGENT_LLM_KEY")
    chat = LlmChat(api_key=api_key, session_id=f"wahlah-mascot-{slug}",
                   system_message="You are an expert branded mascot illustrator.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    try:
        _, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    except Exception as e:
        print(f"[{slug}] API error: {e}", file=sys.stderr)
        return False
    if not images:
        print(f"[{slug}] no image returned", file=sys.stderr)
        return False
    img = images[0]
    out = OUT_DIR / f"{slug}.png"
    out.write_bytes(base64.b64decode(img["data"]))
    print(f"[{slug}] saved -> {out} ({out.stat().st_size//1024} KB, {img['mime_type']})")
    return True


async def main():
    results = {}
    for slug, prompt in PROMPTS.items():
        results[slug] = await gen_one(slug, prompt)
    print("\nSummary:", results)


if __name__ == "__main__":
    asyncio.run(main())
