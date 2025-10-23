"""Generate stylised bottle images from a label.

This module provides a small command line utility that accepts a label image
and composites it on top of a procedurally generated plastic bottle.  The
result is a trio of PNG images that can be used to quickly prototype what a
label might look like when wrapped around a bottle from three viewing angles.

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
from typing import Optional, Tuple, cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from tools import clamp, parse_color, stabilise_mesh
import cv2
import numpy as np

try:  # Pillow >= 9.1
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - fallback for older Pillow
    RESAMPLE_LANCZOS = Image.LANCZOS

try:  # Pillow >= 10.0 provides the Transform enum
    TRANSFORM_MESH = Image.Transform.MESH
except AttributeError:  # pragma: no cover - compatibility for older Pillow
    TRANSFORM_MESH = Image.MESH

Color = Tuple[int, int, int]

DEBUG_MODE = True
@dataclass
class BottleGeometry:
    """Holds the key measurements that define the bottle layout."""

    canvas_size: Tuple[int, int] = (900, 1400)
    body_width_ratio: float = 0.38
    body_height_ratio: float = 0.52
    neck_width_ratio: float = 0.15
    neck_height_ratio: float = 0.18
    shoulder_height_ratio: float = 0.06
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
        left = body[0] - (body[2] - body[0]) * 0
        right = body[2] + (body[2] - body[0]) * 0
        top = body[1] - shoulder_height * 0.4
        bottom = body[1] + shoulder_height * 1.5
        return (left, top, right, bottom)

    def cap_box(self) -> Tuple[float, float, float, float]:
        neck = self.neck_box()
        height = self.canvas_size[1]
        cap_height = height * self.cap_height_ratio
        neck_center = (neck[0] + neck[2]) / 2
        cap_width = (neck[2] - neck[0]) * 1.1
        left = neck_center - cap_width / 2
        on_neck = cap_height * 0.25
        return (left, neck[1] - cap_height + on_neck, left + cap_width, neck[1] + on_neck)

    def label_box(self) -> Tuple[int, int, int, int]:
        body = self.body_box()
        width = body[2] - body[0]
        height = body[3] - body[1]
        label_width = int(width)
        label_height = int(height * 0.2)
        center_x = (body[0] + body[2]) / 2
        label_left = int(center_x - label_width / 2)
        label_top = int(body[1] + height * 0.32)
        return (
            label_left,
            label_top,
            label_left + label_width,
            label_top + label_height,
        )
    
def draw_bottle(geometry: BottleGeometry, bottle_color: Color, cap_color: Color) -> Image.Image:
    """Render the bottle silhouette and return it as an RGBA image."""

    width, height = geometry.canvas_size
    bottle_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bottle_layer)

    body = geometry.body_box()
    bottle_rgba = bottle_color + (90,)
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

    # Add vertical grip stripes with a gentle blur to mimic injection-moulded plastic.
    stripe_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    stripe_draw = ImageDraw.Draw(stripe_layer)
    stripe_count = 12
    cap_width = cap[2] - cap[0]
    cap_height = cap[3] - cap[1]
    for i in range(stripe_count):
        mix = (i + 0.5) / stripe_count
        center_emphasis = 1 - abs(mix - 0.5) * 2
        alpha = int(65 + 70 * center_emphasis)
        stripe_left = cap[0] + cap_width * i / stripe_count
        stripe_right = stripe_left + cap_width / (stripe_count * 2.2)
        stripe_draw.rounded_rectangle(
            (
                stripe_left,
                cap[1] + cap_height * 0.1,
                stripe_right,
                cap[3] - cap_height * 0.1,
            ),
            radius=cap_height * 0.15,
            fill=(255, 255, 255, alpha),
        )
    stripe_layer = stripe_layer.filter(ImageFilter.GaussianBlur(radius=3))
    cap_layer = Image.alpha_composite(cap_layer, stripe_layer)

    # Horizontal ridges mimic screw threads.
    ridge_count = 5
    for i in range(ridge_count):
        y = cap[1] + (cap[3] - cap[1]) * (i + 1) / (ridge_count + 1)
        cap_draw.line(
            [(cap[0] + 4, y), (cap[2] - 4, y)],
            fill=(255, 255, 255, 90 if i % 2 == 0 else 60),
            width=1,
        )

    # Emphasise lighting with a bright highlight on the left and a shadow on the right.
    cap_highlight = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cap_highlight_draw = ImageDraw.Draw(cap_highlight)
    cap_highlight_draw.ellipse(
        (
            cap[0] + cap_width * 0.08,
            cap[1] + cap_height * 0.15,
            cap[0] + cap_width * 0.38,
            cap[3] - cap_height * 0.1,
        ),
        fill=(255, 255, 255, 140),
    )
    cap_highlight = cap_highlight.filter(ImageFilter.GaussianBlur(radius=8))
    cap_layer = Image.alpha_composite(cap_layer, cap_highlight)

    cap_shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cap_shadow_draw = ImageDraw.Draw(cap_shadow)
    cap_shadow_draw.rounded_rectangle(
        (
            cap[0] + cap_width * 0.55,
            cap[1] + cap_height * 0.05,
            cap[2] - cap_width * 0.05,
            cap[3] - cap_height * 0.05,
        ),
        radius=cap_height * 0.2,
        fill=(0, 0, 0, 120),
    )
    cap_shadow = cap_shadow.filter(ImageFilter.GaussianBlur(radius=10))
    cap_layer = Image.alpha_composite(cap_layer, cap_shadow)

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


def curve_label(label_pil: Image.Image, 
                theta_max: float = 1.2, 
                vertical_bulge: float = 0.12) -> Image.Image:
    # --- Pillow -> NumPy (RGBA → BGRA) ---
    label_np = np.array(label_pil)
    if label_np.ndim == 2:
        label_bgr = cv2.cvtColor(label_np, cv2.COLOR_GRAY2BGR)
    elif label_np.shape[2] == 4:
        label_bgr = cv2.cvtColor(label_np, cv2.COLOR_RGBA2BGRA)
    else:
        label_bgr = cv2.cvtColor(label_np, cv2.COLOR_RGB2BGR)

    # --- Здесь вызываем remap (код из прошлого примера) ---
    H, W = label_bgr.shape[:2]
    xs = np.linspace(-0.5, 0.5, W, dtype=np.float32)
    ys = np.linspace(0, 1, H, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    sin_th = X / 0.5 * np.sin(theta_max)
    sin_th = np.clip(sin_th, -0.999999, 0.999999)
    theta = np.arcsin(sin_th)
    u = (theta + theta_max) / (2 * theta_max)
    y_offset = vertical_bulge * (1 - np.cos(theta))
    v = np.clip(Y - y_offset, 0, 1)
    map_x = (u * (W - 1)).astype(np.float32)
    map_y = (v * (H - 1)).astype(np.float32)

    warped = cv2.remap(label_bgr, map_x, map_y,
                       interpolation=cv2.INTER_CUBIC,
                       borderMode=cv2.BORDER_REPLICATE)

    # --- NumPy -> Pillow (BGR → RGB) ---
    warped_rgb = cv2.cvtColor(warped, cv2.COLOR_BGRA2RGBA) if warped.shape[2] == 4 else cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
    return Image.fromarray(warped_rgb)



def prepare_label(
    label_image: Image.Image,
    target_box: Tuple[int, int, int, int],
    crop_position: float,
) -> Image.Image:
    """Reshape the label so it fits the bottle nicely with a horizontal crop."""

    target_width = target_box[2] - target_box[0]
    target_height = target_box[3] - target_box[1]

    label = ImageOps.fit(
        label_image,
        (target_width, target_height),
        method=Image.Resampling.BICUBIC,
        centering=(crop_position, 0.5),
    )

    label = curve_label(label)
    label = curve_label(label)

    # Simulate the curvature of the bottle by fading the edges slightly.
    fade = Image.new("L", label.size, color=255)
    fade_draw = ImageDraw.Draw(fade)
    w, h = label.size
    gradient_width = max(1, int(w * 0.4))
    for i in range(gradient_width):
        alpha = 255 - int(255 * (1 - i / gradient_width * 0.97))
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

    background = ImageOps.fit(background_image, geometry.canvas_size, method=Image.Resampling.BICUBIC).convert("RGBA")
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


def average_label_color(label_image: Image.Image) -> Color:
    """Return the average colour of the label, respecting transparency."""

    rgba = np.array(label_image.convert("RGBA"), dtype=np.float32)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3:4] / 255.0
    alpha_sum = float(alpha.sum())

    if alpha_sum > 0:
        weighted_sum = (rgb * alpha).sum(axis=(0, 1))
        mean = weighted_sum / alpha_sum
    else:
        mean = rgb.mean(axis=(0, 1))

    mean_tuple = tuple(int(round(clamp(float(c), 0, 255))) for c in mean)
    return cast(Color, mean_tuple)


def variant_output_path(base_path: Path, variant: str) -> Path:
    suffix = base_path.suffix or ".png"
    stem = base_path.stem
    return base_path.with_name(f"{stem}_{variant}{suffix}")


def generate_bottle(
    label_path: Path,
    background_path: Path,
    output_path: Path,
    bottle_color: Color,
    cap_color: Optional[Color] = None,
) -> None:
    """High level function that orchestrates the bottle generation for three crops."""

    geometry = BottleGeometry()
    label_image = Image.open(label_path).convert("RGBA")
    background_image = Image.open(background_path)

    if cap_color is None:
        cap_color = average_label_color(label_image)

    if output_path.suffix == "":
        output_path = output_path.with_suffix(".png")

    bottle_layer = draw_bottle(geometry, bottle_color, cap_color)

    for variant_name, crop_position in (("left", 0.0), ("center", 0.5), ("right", 1.0)):
        prepared_label = prepare_label(label_image, geometry.label_box(), crop_position)
        scene = compose_scene(prepared_label, bottle_layer, geometry, background_image)
        scene.save(variant_output_path(output_path, variant_name))


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
        default=None,
        help="Bottle cap colour (default: average colour of the label).",
    )
    return parser


def main() -> None:
    if DEBUG_MODE:
        label_path = Path('/Users/ekaterina/Desktop/coca.png')
        output_path = Path('/Users/ekaterina/test_codex/bottle.png')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        background_path = Path('/Users/ekaterina/Desktop/bg.png')
        if output_path.suffix == "":
            output_path = output_path.with_suffix('.png')
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

        if output_path.suffix == "":
            output_path = output_path.with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        generate_bottle(label_path, background_path, output_path, args.bottle_color, args.cap_color)
        print(
            "Generated bottle images:",
            ", ".join(
                str(variant_output_path(output_path, variant))
                for variant in ("left", "center", "right")
            ),
        )


if __name__ == "__main__":
    main()
