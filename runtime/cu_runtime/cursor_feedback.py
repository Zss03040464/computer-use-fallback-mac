from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
import time
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFilter


CURSOR_STYLE = "aqua-glass-arrow-v2"
CURSOR_SHAPE = (
    (0.5, 0.5),
    (0.5, 13.6),
    (3.4, 10.7),
    (5.6, 17.2),
    (7.9, 16.2),
    (5.5, 9.5),
    (12.4, 9.4),
)
CURSOR_CORE_WIDTH = 13
CURSOR_CORE_HEIGHT = 18
CURSOR_FILL_RGBA = (242, 247, 250, 88)
CURSOR_EDGE_RGBA = (253, 254, 255, 224)
CURSOR_AQUA_RGBA = (132, 218, 238, 52)
CURSOR_GLOW_RGBA = (214, 239, 246, 70)
CURSOR_SUPERSAMPLE = 4
PULSE_DURATION_MS = 700


@dataclass(frozen=True)
class CursorFeedback:
    display_x: int
    display_y: int
    target_bundle_id: str
    target_pid: int
    target_window_id: int
    action: str
    phase: str
    updated_at_ms: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "CursorFeedback | None":
        if value is None:
            return None
        try:
            phase = str(value["phase"])
            target_bundle_id = str(value["targetBundleId"])
            action = str(value["action"])
            updated_at_ms = int(value["updatedAtMs"])
            if phase not in {"steady", "pressed", "released"}:
                return None
            if not target_bundle_id or not action or updated_at_ms < 0:
                return None
            return cls(
                display_x=int(value["displayX"]),
                display_y=int(value["displayY"]),
                target_bundle_id=target_bundle_id,
                target_pid=int(value["targetPid"]),
                target_window_id=int(value["targetWindowId"]),
                action=action,
                phase=phase,
                updated_at_ms=updated_at_ms,
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class CursorVisual:
    pulse: float
    age_ms: int


def cursor_visual(feedback: CursorFeedback, now_ms: int | None = None) -> CursorVisual:
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    age_ms = max(0, now - feedback.updated_at_ms)
    if feedback.phase == "pressed":
        pulse = 1.0
    elif feedback.phase == "released":
        pulse = max(0.0, 1.0 - age_ms / PULSE_DURATION_MS)
    else:
        pulse = 0.0
    return CursorVisual(pulse=pulse, age_ms=age_ms)


def _empty_metadata(reason: str, feedback: CursorFeedback | None = None) -> dict[str, Any]:
    return {
        "drawn": False,
        "style": CURSOR_STYLE,
        "phase": feedback.phase if feedback else None,
        "ageMs": None,
        "imagePoint": None,
        "reason": reason,
    }


def render_cursor_patch(scale: float, pulse: float) -> tuple[Image.Image, tuple[int, int]]:
    logical_scale = max(0.25, float(scale))
    pulse_strength = max(0.0, min(1.0, float(pulse)))
    padding = max(2, math.ceil(6.0 * logical_scale))
    width = max(1, math.ceil(CURSOR_CORE_WIDTH * logical_scale) + padding * 2)
    height = max(1, math.ceil(CURSOR_CORE_HEIGHT * logical_scale) + padding * 2)
    hotspot = (padding, padding)

    supersample = CURSOR_SUPERSAMPLE
    render_scale = logical_scale * supersample
    rendered = Image.new("RGBA", (width * supersample, height * supersample), (0, 0, 0, 0))
    points = [
        (
            round(hotspot[0] * supersample + dx * render_scale),
            round(hotspot[1] * supersample + dy * render_scale),
        )
        for dx, dy in CURSOR_SHAPE
    ]
    closed_points = points + [points[0]]

    glow = Image.new("RGBA", rendered.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_alpha = round(22 + 26 * pulse_strength)
    glow_draw.line(
        closed_points,
        fill=CURSOR_GLOW_RGBA[:3] + (glow_alpha,),
        width=max(1, round((6.0 + 2.0 * pulse_strength) * render_scale)),
        joint="curve",
    )
    glow = glow.filter(
        ImageFilter.GaussianBlur(
            radius=max(1.0, (1.25 + 0.35 * pulse_strength) * render_scale)
        )
    )
    rendered.alpha_composite(glow)

    draw = ImageDraw.Draw(rendered)
    draw.polygon(points, fill=CURSOR_FILL_RGBA)
    draw.line(
        closed_points,
        fill=CURSOR_EDGE_RGBA,
        width=max(1, round(1.15 * render_scale)),
        joint="curve",
    )
    draw.line(
        points[2:5],
        fill=CURSOR_AQUA_RGBA,
        width=max(1, round(0.7 * render_scale)),
        joint="curve",
    )

    patch = rendered.resize((width, height), Image.Resampling.LANCZOS)
    return patch, hotspot


def composite_cursor_image(
    image: Image.Image,
    point_x: int,
    point_y: int,
    scale: float,
    pulse: float,
) -> tuple[Image.Image, list[int]]:
    base = image.convert("RGBA")
    patch, hotspot = render_cursor_patch(scale, pulse)
    destination_left = int(round(point_x - hotspot[0]))
    destination_top = int(round(point_y - hotspot[1]))
    left = max(0, destination_left)
    top = max(0, destination_top)
    right = min(base.width, destination_left + patch.width)
    bottom = min(base.height, destination_top + patch.height)
    if right <= left or bottom <= top:
        return base, [left, top, 0, 0]

    source_left = left - destination_left
    source_top = top - destination_top
    visible = patch.crop(
        (
            source_left,
            source_top,
            source_left + (right - left),
            source_top + (bottom - top),
        )
    )
    base.alpha_composite(visible, dest=(left, top))
    return base, [left, top, right - left, bottom - top]


def composite_cursor_png(
    png: bytes,
    feedback: CursorFeedback | None,
    target: Any,
    scale_x: float,
    scale_y: float,
    *,
    now_ms: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    if feedback is None:
        return png, _empty_metadata("no_feedback")
    if (
        feedback.target_bundle_id != str(target.bundle_id)
        or feedback.target_pid != int(target.pid)
        or feedback.target_window_id != int(target.window_id)
    ):
        return png, _empty_metadata("target_mismatch", feedback)

    local_x = feedback.display_x - int(target.x)
    local_y = feedback.display_y - int(target.y)
    if local_x < 0 or local_y < 0 or local_x >= int(target.width) or local_y >= int(target.height):
        return png, _empty_metadata("out_of_bounds", feedback)

    point_x = round(local_x * float(scale_x))
    point_y = round(local_y * float(scale_y))
    image = Image.open(BytesIO(png)).convert("RGBA")
    if point_x < 0 or point_y < 0 or point_x >= image.width or point_y >= image.height:
        return png, _empty_metadata("out_of_bounds", feedback)

    scale = max(1.0, min(float(scale_x), float(scale_y)))
    visual = cursor_visual(feedback, now_ms)
    image, render_bounds = composite_cursor_image(
        image,
        point_x,
        point_y,
        scale,
        visual.pulse,
    )

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), {
        "drawn": True,
        "style": CURSOR_STYLE,
        "phase": feedback.phase,
        "ageMs": visual.age_ms,
        "imagePoint": [point_x, point_y],
        "renderBounds": render_bounds,
        "reason": None,
    }
