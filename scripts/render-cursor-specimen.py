#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.cu_runtime.cursor_feedback import CURSOR_STYLE, render_cursor_patch


WIDTH = 900
HEIGHT = 360
PANEL_WIDTH = 300
BACKGROUNDS = (
    ("dark", (45, 43, 44), (248, 249, 250)),
    ("mid", (116, 119, 123), (250, 251, 252)),
    ("light", (236, 239, 242), (35, 39, 43)),
)


def render_specimen(output_path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    for index, (name, background, text_color) in enumerate(BACKGROUNDS):
        left = index * PANEL_WIDTH
        draw.rectangle((left, 0, left + PANEL_WIDTH, HEIGHT), fill=background)
        draw.text((left + 18, 18), f"{name} background", fill=text_color)
        draw.text((left + 18, 42), CURSOR_STYLE, fill=text_color)

        steady, steady_hotspot = render_cursor_patch(1.0, 0.0)
        steady_point = (left + 75, 170)
        canvas.paste(
            steady,
            (
                steady_point[0] - steady_hotspot[0],
                steady_point[1] - steady_hotspot[1],
            ),
            steady,
        )
        draw.text((left + 42, 225), "steady 1x", fill=text_color)

        pressed, pressed_hotspot = render_cursor_patch(2.0, 1.0)
        pressed_point = (left + 210, 165)
        canvas.paste(
            pressed,
            (
                pressed_point[0] - pressed_hotspot[0],
                pressed_point[1] - pressed_hotspot[1],
            ),
            pressed,
        )
        draw.text((left + 174, 225), "pressed 2x", fill=text_color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: render-cursor-specimen.py OUTPUT.png", file=sys.stderr)
        return 2
    output_path = Path(sys.argv[1]).expanduser().resolve()
    render_specimen(output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
