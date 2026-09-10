"""Strip baked-in background from Nano-Banana-generated PNGs. Uses rembg (u2net)."""
from pathlib import Path
from rembg import remove, new_session

M = Path("/app/frontend/public/mascots")
session = new_session("u2net")

for p in sorted(M.glob("genie_*.png")):
    inp = p.read_bytes()
    out = remove(inp, session=session, alpha_matting=True, alpha_matting_foreground_threshold=240,
                 alpha_matting_background_threshold=10, alpha_matting_erode_size=10)
    p.write_bytes(out)
    print(f"{p.name}: {len(inp)//1024}K -> {len(out)//1024}K (bg removed)")
