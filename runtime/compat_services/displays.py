from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import CompatServiceError


@dataclass(frozen=True)
class DisplayInfo:
    display_id: int
    x: float
    y: float
    logical_width: int
    logical_height: int
    pixel_width: int
    pixel_height: int

    @property
    def scale_x(self) -> float:
        return self.pixel_width / self.logical_width

    @property
    def scale_y(self) -> float:
        return self.pixel_height / self.logical_height


class DisplayProvider(Protocol):
    def active_displays(self) -> list[DisplayInfo]:
        ...

    def main_display_id(self) -> int:
        ...


class QuartzDisplayProvider:
    def active_displays(self) -> list[DisplayInfo]:
        import Quartz

        error, identifiers, _count = Quartz.CGGetActiveDisplayList(64, None, None)
        if error != 0:
            raise CompatServiceError(
                "display_discovery_failed",
                "CoreGraphics could not enumerate active displays",
                {"status": int(error)},
            )
        displays = []
        for identifier in identifiers:
            bounds = Quartz.CGDisplayBounds(identifier)
            displays.append(
                DisplayInfo(
                    display_id=int(identifier),
                    x=float(bounds.origin.x),
                    y=float(bounds.origin.y),
                    logical_width=int(round(bounds.size.width)),
                    logical_height=int(round(bounds.size.height)),
                    pixel_width=int(Quartz.CGDisplayPixelsWide(identifier)),
                    pixel_height=int(Quartz.CGDisplayPixelsHigh(identifier)),
                )
            )
        return displays

    def main_display_id(self) -> int:
        import Quartz

        return int(Quartz.CGMainDisplayID())


class DisplayService:
    def __init__(self, provider: DisplayProvider) -> None:
        self.provider = provider

    def resolve(self, display_id: int | None) -> DisplayInfo:
        requested = self.provider.main_display_id() if display_id is None else int(display_id)
        for display in self.provider.active_displays():
            if display.display_id == requested:
                return display
        raise CompatServiceError(
            "display_not_found",
            "Requested display is not active",
            {"displayId": requested},
        )

    def map_coordinates(self, payload: dict) -> dict:
        display = self.resolve(payload.get("displayId"))
        try:
            x = float(payload["x"])
            y = float(payload["y"])
        except (KeyError, TypeError, ValueError):
            raise CompatServiceError("invalid_coordinates", "Coordinates must be numbers")

        destination = payload.get("to")
        if destination == "physical":
            mapped_x = display.x + (x - display.x) * display.scale_x
            mapped_y = display.y + (y - display.y) * display.scale_y
        elif destination == "logical":
            mapped_x = display.x + (x - display.x) / display.scale_x
            mapped_y = display.y + (y - display.y) / display.scale_y
        else:
            raise CompatServiceError(
                "invalid_coordinate_space",
                "Coordinate destination must be logical or physical",
            )
        return {
            "displayId": display.display_id,
            "x": round(mapped_x),
            "y": round(mapped_y),
            "space": destination,
        }
