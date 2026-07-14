#!/usr/bin/env python3
from __future__ import annotations

from PIL import Image

from runtime.cu_runtime.cursor_feedback import CURSOR_STYLE, composite_cursor_image


def assert_pixel_changed(image: Image.Image, x: int, y: int) -> None:
    pixel = image.getpixel((x, y))
    if pixel == (0, 0, 0):
        raise AssertionError(f"Expected pixel ({x}, {y}) to be changed by virtual cursor overlay")


def assert_pixel_unchanged(image: Image.Image, x: int, y: int) -> None:
    pixel = image.getpixel((x, y))
    if pixel != (0, 0, 0):
        raise AssertionError(f"Expected pixel ({x}, {y}) to remain black, got {pixel}")


def main() -> None:
    image = Image.new("RGB", (120, 120), (0, 0, 0))
    rendered, bounds = composite_cursor_image(image, 30, 35, 1.0, 1.0)

    if CURSOR_STYLE != "aqua-glass-arrow-v2":
        raise AssertionError(f"Expected aqua-glass-arrow-v2 style, got {CURSOR_STYLE}")
    if bounds[2] <= 0 or bounds[3] <= 0:
        raise AssertionError(f"Expected visible cursor bounds, got {bounds}")

    assert_pixel_changed(rendered.convert("RGB"), 30, 35)
    assert_pixel_changed(rendered.convert("RGB"), 35, 44)
    assert_pixel_unchanged(rendered.convert("RGB"), 100, 100)

    offscreen = Image.new("RGB", (120, 120), (0, 0, 0))
    offscreen_rendered, offscreen_bounds = composite_cursor_image(offscreen, 200, 200, 1.0, 1.0)
    if offscreen_bounds[2] != 0 or offscreen_bounds[3] != 0:
        raise AssertionError(f"Expected offscreen cursor not to be drawn, got {offscreen_bounds}")
    assert_pixel_unchanged(offscreen_rendered.convert("RGB"), 100, 100)

    print("Virtual cursor visual overlay test: PASS")


if __name__ == "__main__":
    main()
