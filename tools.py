"""Utility helpers shared by the bottle generation modules."""

from __future__ import annotations

import argparse
from typing import Iterable, Sequence, Tuple

from PIL import ImageColor

Color = Tuple[int, int, int]


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp *value* into the inclusive range [minimum, maximum]."""

    return max(minimum, min(maximum, value))


def parse_color(value: str) -> Color:
    """Parse a color value accepted by Pillow (name or hex)."""

    try:
        r, g, b = ImageColor.getrgb(value)
    except ValueError as exc:  # pragma: no cover - handled by argparse
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return (r, g, b)


def stabilise_mesh(
    mesh: Iterable[Tuple[Sequence[float], Sequence[float]]], *, width: int
) -> Tuple[Tuple[Tuple[int, int, int, int], Tuple[float, ...]], ...]:
    """Normalise mesh data so Pillow receives clean, ordered quads.

    Pillow requires integer bounding boxes for :pyfunc:`Image.transform` mesh
    operations.  Rounding can create overlapping or inverted boxes which in
    turn jumbles pixels in the final warped label.  This helper walks the
    generated mesh and ensures each destination box stays monotonic while also
    keeping at least one pixel of width so adjacent slices line up cleanly.
    """

    stabilised = []
    previous_right = 0
    for bbox, quad in mesh:
        left, top, right, bottom = bbox
        left_i = max(previous_right, int(round(left)))
        right_i = int(round(right))
        if right_i <= left_i:
            right_i = left_i + 1
        previous_right = right_i
        stabilised.append(((left_i, int(round(top)), right_i, int(round(bottom))), tuple(float(x) for x in quad)))

    if stabilised:
        # Force the last slice to end exactly at the expected width so there is
        # no visible gap caused by rounding error.
        last_bbox, last_quad = stabilised[-1]
        if last_bbox[2] != width:
            stabilised[-1] = ((last_bbox[0], last_bbox[1], width, last_bbox[3]), last_quad)

    return tuple(stabilised)

