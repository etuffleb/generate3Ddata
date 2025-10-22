"""Generate a stylised bottle image from a label.

This module provides a small command line utility that accepts a label image
and composites it on top of a procedurally generated plastic bottle.  The
result is a PNG image that can be used to quickly prototype what a label might
look like when wrapped around a bottle.

Example
-------
    python generate_bottle.py label.png studio_background.jpg --output bottle.png

The script only requires Pillow which can be installed with
``pip install pillow``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageOps

try:  # Pillow >= 9.1
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - fallback for older Pillow
    RESAMPLE_LANCZOS = Image.LANCZOS

try:  # Pillow >= 10.0 provides the Transform enum
    TRANSFORM_MESH = Image.Transform.MESH
except AttributeError:  # pragma: no cover - compatibility for older Pillow
    TRANSFORM_MESH = Image.MESH

Color = Tuple[int, int, int]

DEBUG_MODE = False


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp *value* into the inclusive range [minimum, maximum]."""

    return max(minimum, min(maximum, value))

@dataclass
class BottleGeometry:
    """Holds the key measurements that define the bottle layout."""

    canvas_size: Tuple[int, int] = (900, 1400)
    body_width_ratio: float = 0.38
    body_height_ratio: float = 0.52
    neck_width_ratio: float = 0.22
    neck_height_ratio: float = 0.16
    shoulder_height_ratio: float = 0.08
    cap_height_ratio: float = 0.055

    def body_box(self) -> Tuple[float, float, float, float]:
        width, height = self.canvas_size
        body_width = width * self.body_width_ratio
        body_height = height * self.body_height_ratio
        top = height * 0.32
        left = width / 2 - body_width / 2
        return (left, top, left + body_width, top + body_height)

    def neck_box(self) -> Tuple[float, float, float, float]:
        width, height = self.canvas_size
        neck_width = width * self.neck_width_ratio
        body_top = self.body_box()[1]
        neck_height = height * self.neck_height_ratio
        left = width / 2 - neck_width / 2
        return (left, body_top - neck_height, left + neck_width, body_top)

    def shoulder_box(self) -> Tuple[float, float, float, float]:
        width, height = self.canvas_size
        body = self.body_box()
        shoulder_height = height * self.shoulder_height_ratio
        left = body[0] - (body[2] - body[0]) * 0.12
        right = body[2] + (body[2] - body[0]) * 0.12
        top = body[1] - shoulder_height
        bottom = body[1] + shoulder_height * 0.35
        return (left, top, right, bottom)

    def cap_box(self) -> Tuple[float, float, float, float]:
        neck = self.neck_box()
        height = self.canvas_size[1]
        cap_height = height * self.cap_height_ratio
        neck_center = (neck[0] + neck[2]) / 2
        cap_width = (neck[2] - neck[0]) * 0.8
        left = neck_center - cap_width / 2
        return (left, neck[1] - cap_height, left + cap_width, neck[1])

    def label_box(self) -> Tuple[int, int, int, int]:
        body = self.body_box()
        width = body[2] - body[0]
        height = body[3] - body[1]
        label_width = int(width * 0.88)
        label_height = int(height * 0.4)
        center_x = (body[0] + body[2]) / 2
        label_left = int(center_x - label_width / 2)
        label_top = int(body[1] + height * 0.32)
        return (
            label_left,
            label_top,
            label_left + label_width,
            label_top + label_height,
        )


def parse_color(value: str) -> Color:
    """Parse a color value accepted by Pillow (name or hex)."""

    try:
        r, g, b = ImageColor.getrgb(value)
    except ValueError as exc:  # pragma: no cover - handled by argparse
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return (r, g, b)


def draw_bottle(geometry: BottleGeometry, bottle_color: Color, cap_color: Color) -> Image.Image:
    """Render the bottle silhouette and return it as an RGBA image."""

    width, height = geometry.canvas_size
    bottle_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bottle_layer)

    body = geometry.body_box()
    bottle_rgba = bottle_color + (110,)
    draw.rounded_rectangle(body, radius=(body[2] - body[0]) * 0.18, fill=bottle_rgba)

    neck = geometry.neck_box()
    draw.rounded_rectangle(neck, radius=(neck[2] - neck[0]) * 0.3, fill=bottle_rgba)

    shoulder = geometry.shoulder_box()
    draw.ellipse(shoulder, fill=bottle_rgba)
    cap = geometry.cap_box()
    cap_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cap_draw = ImageDraw.Draw(cap_layer)
    cap_rgba = cap_color + (255,)
    cap_draw.rounded_rectangle(cap, radius=(cap[2] - cap[0]) * 0.25, fill=cap_rgba)

    # Add subtle top ellipse for the cap and soft highlight.
    top_height = (cap[3] - cap[1]) * 0.35
    cap_draw.ellipse(
        (
            cap[0] + (cap[2] - cap[0]) * 0.08,
            cap[1] - top_height * 0.4,
            cap[2] - (cap[2] - cap[0]) * 0.08,
            cap[1] + top_height,
        ),
        fill=(255, 255, 255, 80),
    )

    # Horizontal ridges mimic screw threads.
    ridge_count = 5
    for i in range(ridge_count):
        y = cap[1] + (cap[3] - cap[1]) * (i + 1) / (ridge_count + 1)
        cap_draw.line(
            [(cap[0] + 4, y), (cap[2] - 4, y)],
            fill=(255, 255, 255, 90 if i % 2 == 0 else 60),
            width=1,
        )

    bottle_layer = Image.alpha_composite(bottle_layer, cap_layer)

    # Interior refraction glow.
    refraction = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    refraction_draw = ImageDraw.Draw(refraction)
    inner_box = (
        body[0] + (body[2] - body[0]) * 0.08,
        body[1] + (body[3] - body[1]) * 0.1,
        body[2] - (body[2] - body[0]) * 0.08,
        body[3] - (body[3] - body[1]) * 0.15,
    )
    refraction_draw.rounded_rectangle(inner_box, radius=(inner_box[2] - inner_box[0]) * 0.3, fill=(255, 255, 255, 70))
    refraction = refraction.filter(ImageFilter.GaussianBlur(radius=60))
    bottle_layer = Image.alpha_composite(bottle_layer, refraction)

    # Add a soft highlight on the left side of the bottle to simulate lighting.
    highlight = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    body_width = body[2] - body[0]
    highlight_box = (
        int(body[0] + body_width * 0.05),
        int(body[1] + (body[3] - body[1]) * 0.05),
        int(body[0] + body_width * 0.35),
        int(body[3] - (body[3] - body[1]) * 0.15),
    )
    highlight_draw.ellipse(highlight_box, fill=(255, 255, 255, 150))
    highlight = highlight.filter(ImageFilter.GaussianBlur(radius=40))
    bottle_layer = Image.alpha_composite(bottle_layer, highlight)

    # Subtle darker edge on the right for depth.
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_box = (
        int(body[2] - body_width * 0.3),
        int(body[1] + (body[3] - body[1]) * 0.1),
        int(body[2] + body_width * 0.1),
        int(body[3]),
    )
    shadow_draw.ellipse(shadow_box, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=50))
    bottle_layer = Image.alpha_composite(bottle_layer, shadow)

    return bottle_layer


def curve_label(label: Image.Image, curvature: float = 0.28) -> Image.Image:
    """Warp the label slightly so it hugs the cylindrical bottle body."""

    width, height = label.size
    slices = max(10, int(width / 20))
    mesh = []

    for slice_index in range(slices):
        x0 = width * slice_index / slices
        x1 = width * (slice_index + 1) / slices
        dest_box = (x0, 0, x1, height)

        mid_x = (x0 + x1) / 2
        # Map to the range [-1, 1].
        rel = (mid_x / width) * 2 - 1
        scale = 1 - curvature * (rel ** 2)
        scale = clamp(scale, 0.55, 1.0)
        src_slice_width = (x1 - x0) / scale

        src_mid_x = width / 2 + (mid_x - width / 2) / scale
        src_x0 = clamp(src_mid_x - src_slice_width / 2, 0, width)
        src_x1 = clamp(src_mid_x + src_slice_width / 2, 0, width)

        top_offset = curvature * 18 * (1 - abs(rel))
        src_quad = (
            src_x0,
            clamp(0 - top_offset, 0, height),
            src_x1,
            clamp(0 - top_offset, 0, height),
            src_x1,
            clamp(height + top_offset, 0, height),
            src_x0,
            clamp(height + top_offset, 0, height),
        )
        mesh.append((dest_box, src_quad))

    return label.transform(label.size, TRANSFORM_MESH, mesh, RESAMPLE_LANCZOS)


def prepare_label(label_path: Path, target_box: Tuple[int, int, int, int]) -> Image.Image:
    """Load and reshape the label so it fits the bottle nicely."""

    label = Image.open(label_path).convert("RGBA")
    target_width = target_box[2] - target_box[0]
    target_height = target_box[3] - target_box[1]

    label = ImageOps.contain(label, (target_width, target_height), method=RESAMPLE_LANCZOS)

    label = curve_label(label)

    # Simulate the curvature of the bottle by fading the edges slightly.
    fade = Image.new("L", label.size, color=255)
    fade_draw = ImageDraw.Draw(fade)
    w, h = label.size
    gradient_width = max(1, int(w * 0.2))
    for i in range(gradient_width):
        alpha = int(255 * (1 - i / gradient_width * 0.75))
        fade_draw.line([(i, 0), (i, h)], fill=alpha)
        fade_draw.line([(w - 1 - i, 0), (w - 1 - i, h)], fill=alpha)
    label.putalpha(ImageChops.multiply(label.split()[-1], fade))

    return label


def compose_scene(
    label_image: Image.Image,
    bottle_layer: Image.Image,
    geometry: BottleGeometry,
    background_image: Image.Image,
) -> Image.Image:
    """Combine the background, bottle and label layers."""

    background = ImageOps.fit(background_image, geometry.canvas_size, method=RESAMPLE_LANCZOS).convert("RGBA")
    scene = Image.alpha_composite(background, bottle_layer)

    label_box = geometry.label_box()
    label_left, label_top = label_box[:2]
    label_position = (
        label_left + (label_box[2] - label_box[0] - label_image.width) // 2,
        label_top + (label_box[3] - label_box[1] - label_image.height) // 2,
    )
    scene.paste(label_image, label_position, label_image)

    # Subtle drop shadow for the bottle.
    shadow = Image.new("RGBA", geometry.canvas_size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    body = geometry.body_box()
    shadow_box = (
        int(body[0] - (body[2] - body[0]) * 0.1),
        int(body[3] + (geometry.canvas_size[1] - body[3]) * 0.02),
        int(body[2] + (body[2] - body[0]) * 0.1),
        int(body[3] + (geometry.canvas_size[1] - body[3]) * 0.08),
    )
    shadow_draw.ellipse(shadow_box, fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=30))
    scene = Image.alpha_composite(shadow, scene)

    return scene


def generate_bottle(
    label_path: Path,
    background_path: Path,
    output_path: Path,
    bottle_color: Color,
    cap_color: Color,
) -> None:
    """High level function that orchestrates the bottle generation."""

    geometry = BottleGeometry()
    bottle_layer = draw_bottle(geometry, bottle_color, cap_color)
    label_image = prepare_label(label_path, geometry.label_box())
    background_image = Image.open(background_path)
    scene = compose_scene(label_image, bottle_layer, geometry, background_image)
    scene.save(output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a bottle render from a label image.")
    parser.add_argument("label", type=Path, help="Path to the input label image (PNG, JPG, ...).")
    parser.add_argument("background", type=Path, help="Path to the background image that the bottle sits on.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Path for the generated image (defaults to <label>_bottle.png).",
    )
    parser.add_argument(
        "--bottle-color",
        type=parse_color,
        default="#48a9e6",
        help="Bottle fill colour (any Pillow-supported string, default: light blue).",
    )
    parser.add_argument(
        "--cap-color",
        type=parse_color,
        default="#245b96",
        help="Bottle cap colour (default: darker blue).",
    )
    return parser


def main() -> None:
    if DEBUG_MODE:
        label_path = Path('/Users/ekaterina/Desktop/cocacola.png')
        output_path = Path('/Users/ekaterina/test_codex/bottle.png')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        background_path = Path('/Users/ekaterina/Desktop/background.png')
        generate_bottle(label_path, background_path, output_path, (125, 198, 245), (36, 91, 150))

    else:
        parser = build_parser()
        args = parser.parse_args()
        label_path: Path = args.label
        background_path: Path = args.background
        if not label_path.exists():
            parser.error(f"Label image '{label_path}' does not exist.")
        if not background_path.exists():
            parser.error(f"Background image '{background_path}' does not exist.")
        output_path: Path
        if args.output is None:
            output_path = label_path.with_name(label_path.stem + "_bottle.png")
        else:
            output_path = args.output

        output_path.parent.mkdir(parents=True, exist_ok=True)
        generate_bottle(label_path, background_path, output_path, args.bottle_color, args.cap_color)
        print(f"Bottle image saved to {output_path}")


if __name__ == "__main__":
    main()
