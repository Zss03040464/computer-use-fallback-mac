#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
HELPER_PATH = ROOT / "runtime" / "mac_helper.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("mac_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper from {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_pixel_changed(image: Image.Image, x: int, y: int) -> None:
    pixel = image.getpixel((x, y))
    if pixel == (0, 0, 0):
        raise AssertionError(f"Expected pixel ({x}, {y}) to be changed by virtual cursor overlay")


def assert_pixel_unchanged(image: Image.Image, x: int, y: int) -> None:
    pixel = image.getpixel((x, y))
    if pixel != (0, 0, 0):
        raise AssertionError(f"Expected pixel ({x}, {y}) to remain black, got {pixel}")


def main() -> None:
    helper = load_helper()
    image = Image.new("RGB", (120, 120), (0, 0, 0))
    display = {
        "originX": 0,
        "originY": 0,
        "width": 120,
        "height": 120,
        "scaleFactor": 1.0,
        "displayId": 1,
    }

    result = helper.draw_virtual_cursor_overlay(
        image,
        display,
        {"x": 30, "y": 35},
    )

    if not result.get("drawn"):
        raise AssertionError(f"Expected cursor overlay to be drawn, got {result}")
    if result.get("style") != "fallback-official-aqua-arrow-v2":
        raise AssertionError(f"Expected fallback-official-aqua-arrow-v2 style, got {result}")

    assert_pixel_changed(image, 30, 35)
    assert_pixel_changed(image, 35, 44)
    assert_pixel_unchanged(image, 100, 100)

    offscreen = Image.new("RGB", (120, 120), (0, 0, 0))
    offscreen_result = helper.draw_virtual_cursor_overlay(
        offscreen,
        display,
        {"x": 200, "y": 200},
    )
    if offscreen_result.get("drawn"):
        raise AssertionError(f"Expected offscreen cursor not to be drawn, got {offscreen_result}")
    assert_pixel_unchanged(offscreen, 100, 100)

    print("Virtual cursor visual overlay test: PASS")


if __name__ == "__main__":
    main()
