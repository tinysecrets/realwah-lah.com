"""Generate THE WAH-LAH genie mascot — single character, multiple poses, premium 3D look."""
import asyncio
import base64
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")

OUT_DIR = Path("/app/frontend/public/mascots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# SHARED CHARACTER DESCRIPTION — used in every prompt for consistency
CHAR = (
    "WAH-LAH is a confident young adult male genie mascot character. "
    "Premium stylized 3D render, semi-realistic proportions (like a modern Pixar / Overwatch hero / "
    "Fortnite skin quality), thick cel-shaded outlines are OFF — use soft subsurface rendered skin. "
    "Skin: light teal-to-lavender iridescent gradient, subtle shimmer. "
    "Hair: short crisp fade with a top-knot, jet-black with electric magenta highlights. "
    "Face: sharp jawline, mischievous smirk, a small goatee, one earring (gold hoop, left ear), "
    "bright cyan glowing eyes with gold flecks. "
    "Outfit: gold embroidered cropped vest open at chest (revealing chest tattoo of a W), "
    "flowing translucent magenta-to-cyan smoke instead of legs (genie tail), "
    "thick gold bracelets on both wrists, gold choker with a glowing pink gem. "
    "He carries a polished brass-gold lamp with a glowing magenta mist curling from the spout. "
    "Pure transparent background, clean alpha, no scenery, no ground shadow. "
    "High detail, high contrast, vibrant saturated colors. Sticker-style cutout. Render at 1024x1024."
)

POSES = {
    "genie_hero": (
        "Hero pose: front-facing, confident grin, floating upright, arms wide in a 'welcome' gesture, "
        "the lamp floats beside him at hip-height spewing a thick magenta-gold smoke cloud. "
        "Sparkle particles around him. Camera: slight low angle, dynamic composition. "
        "He owns the frame like he runs the show."
    ),
    "genie_pointing": (
        "Finger-pointing pose: leaning forward, winking, pointing his index finger directly at the camera "
        "with a playful smirk. Gold coins and playing cards float around his hand. "
        "The lamp is tucked under his other arm. Sparkle burst from his pointing fingertip."
    ),
    "genie_side": (
        "Side-flying pose: in profile, flying horizontally left-to-right like he just zoomed in, "
        "lamp held out in front, smoke trailing behind him forming a long magenta-cyan streak. "
        "Cheeky smile, hair swept back by speed. Compositionally fills a horizontal frame."
    ),
    "genie_small_peek": (
        "Small head-only variant: just his head and shoulders peeking from behind an invisible edge "
        "(left side), one hand giving a thumbs-up, one eyebrow raised, smirking. "
        "Compact composition, tight crop, transparent background — designed to peek from a corner."
    ),
    "genie_lamp_static": (
        "Just the lamp alone — polished brass-gold magic lamp, no genie. "
        "Ornate Middle-Eastern / Moroccan engravings, thick magenta and cyan smoke curling from the spout, "
        "small gold coins spilling from the opening. Floating at slight tilt. Transparent background."
    ),
}


async def gen_one(slug: str, pose: str) -> bool:
    api_key = os.getenv("EMERGENT_LLM_KEY")
    chat = LlmChat(api_key=api_key, session_id=f"wahlah-{slug}",
                   system_message="You are an elite 3D character illustrator for top mobile game brands.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    prompt = f"{CHAR}\n\nPOSE: {pose}"
    try:
        _, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    except Exception as e:
        print(f"[{slug}] error: {e}", file=sys.stderr)
        return False
    if not images:
        print(f"[{slug}] no image", file=sys.stderr)
        return False
    out = OUT_DIR / f"{slug}.png"
    out.write_bytes(base64.b64decode(images[0]["data"]))
    print(f"[{slug}] -> {out} ({out.stat().st_size//1024} KB)")
    return True


async def main():
    # Clear old cheap mascots first
    for old in ["wahlah_genie.png", "wahlah_genie_winking.png", "wahlah_coin_buddy.png"]:
        p = OUT_DIR / old
        if p.exists():
            p.unlink()
    results = {}
    for slug, pose in POSES.items():
        results[slug] = await gen_one(slug, pose)
    print("\nDone:", results)


if __name__ == "__main__":
    asyncio.run(main())
