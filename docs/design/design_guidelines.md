# WAH-LAH Design Guidelines

> Full opinionated style guide is in **`/app/docs/design/design_guidelines.json`**.
> This markdown is the human-readable quick-ref.

## Theme
**Dark · Electric & Neon meets Jewel & Luxury** — premium velvet-rope exclusivity fused with a playful, charismatic Genie character. Every layout choice should feel like stepping into a modern magic show.

## Colors (palette inspired by the Genie)
| Token | Hex | Role |
|---|---|---|
| `--cyan-500` | `#06B6D4` | Primary — buttons, key actions |
| `--magenta-500` | `#D946EF` | Accent — highlights, Genie glow |
| `--gold-400` | `#FBBF24` | Highlight — winnings, banners |
| `--indigo-500` | `#6366F1` | Support — secondary text, nebula |
| `--warm-black-base` | `#0B061A` | Surface — page background |
| `--warm-black-elevated` | `#130A2A` | Elevated cards |
| `--warm-black-modal` | `#1F1140` | Modals, chat bubbles |

Full 50→950 ramps for cyan, magenta, gold, indigo in the JSON.

## Typography
- **Display / Headings**: `Fredoka` (400/500/600/700) — modern, friendly, with softened geometry that matches the Genie's playful personality.
- **Body / UI**: `DM Sans` (400/500/600/700) — clean, inviting, highly legible.
- Cinzel is retained only for the "WAH-LAH" wordmark on brand surfaces.

## Motion easing
- `ease-magic`: `cubic-bezier(.3, 1.6, .4, 1)` — banners, hero pops (overshoots like a magic reveal)
- `ease-smooth`: `cubic-bezier(.2, 1, .4, 1)` — hover lifts, page entrances
- `ease-press`: `cubic-bezier(.4, 0, .6, 1)` — button presses

## Mascot rules
- `genie_hero.png` — auth pages + Boss Mode idle
- `genie_pointing.png` — deposit celebration + floating top-right
- `genie_side.png` — traveler (flies across dashboard)
- `genie_lamp_static.png` — card-genie lamp pose
- `genie_small_peek.png` — card-genie peek + header orbiter
- Always honor `prefers-reduced-motion`.

See `/app/docs/design/design_guidelines.json` for full component specs, shadow tokens, spacing scale, iconography rules, and microcopy voice examples.
