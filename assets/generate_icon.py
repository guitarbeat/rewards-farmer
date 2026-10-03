"""Generate the Rewards Farmer launcher icon and header artwork."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS_DIR = Path(__file__).resolve().parent
ICON_PATH = ASSETS_DIR / "rewards-farmer.ico"
PNG_PATH = ASSETS_DIR / "rewards-farmer.png"

SIZES = (16, 24, 32, 48, 64, 128, 256)

# Accent palette used by the desktop shortcut icon
TEAL_TOP = (18, 156, 125)
TEAL_BOTTOM = (6, 88, 118)
TEAL_EDGE = (4, 62, 82)
GOLD_OUTER = (212, 146, 10)
GOLD_MID = (255, 203, 44)
GOLD_INNER = (255, 232, 138)
GOLD_SHADOW = (120, 72, 8)
LEAF = (86, 186, 72)
LEAF_DARK = (52, 132, 58)


def _lerp(a: int, b: int, t: float) -> int:
	return int(a + (b - a) * t)


def _lerp_color(
	a: tuple[int, int, int],
	b: tuple[int, int, int],
	t: float,
) -> tuple[int, int, int, int]:
	return (_lerp(a[0], b[0], t), _lerp(a[1], b[1], t), _lerp(a[2], b[2], t), 255)


def _scale(value: int, size: int, base: int = 256) -> int:
	return max(1, round(value * size / base))


def _draw_vertical_gradient_round_rect(
	draw: ImageDraw.ImageDraw,
	box: tuple[int, int, int, int],
	radius: int,
	top: tuple[int, int, int],
	bottom: tuple[int, int, int],
) -> None:
	x0, y0, x1, y1 = box
	for y in range(y0, y1 + 1):
		t = (y - y0) / max(1, y1 - y0)
		color = _lerp_color(top, bottom, t)
		draw.rounded_rectangle((x0, y, x1, y), radius=radius, fill=color)


def _draw_radial_coin(
	draw: ImageDraw.ImageDraw,
	center: tuple[int, int],
	radius: int,
) -> None:
	cx, cy = center

	draw.ellipse(
		(cx - radius + _scale(4, radius * 4), cy - radius + _scale(6, radius * 4), cx + radius + _scale(4, radius * 4), cy + radius + _scale(8, radius * 4)),
		fill=(*GOLD_SHADOW, 90),
	)

	for index, (scale, color) in enumerate(
		(
			(1.0, GOLD_OUTER),
			(0.88, GOLD_MID),
			(0.74, GOLD_INNER),
		)
	):
		r = max(2, round(radius * scale))
		offset_y = _scale(1, radius * 4) if index == 0 else 0
		draw.ellipse((cx - r, cy - r + offset_y, cx + r, cy + r + offset_y), fill=(*color, 255))

	ring = max(1, radius // 10)
	draw.ellipse(
		(cx - radius + ring, cy - radius + ring, cx + radius - ring, cy + radius - ring),
		outline=(*GOLD_OUTER, 180),
		width=max(1, ring // 2),
	)

	shine_w = max(2, radius // 2)
	shine_h = max(2, radius // 3)
	draw.ellipse(
		(
			cx - radius // 2,
			cy - radius + _scale(8, radius * 4),
			cx - radius // 2 + shine_w,
			cy - radius + _scale(8, radius * 4) + shine_h,
		),
		fill=(255, 250, 230, 210),
	)


def _draw_star(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int) -> None:
	cx, cy = center
	points: list[tuple[float, float]] = []

	for index in range(10):
		angle = math.radians(-90 + index * 36)
		r = radius if index % 2 == 0 else radius * 0.42
		points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

	draw.polygon(points, fill=(176, 106, 8, 255))


def _draw_wheat_stalk(
	draw: ImageDraw.ImageDraw,
	base: tuple[int, int],
	height: int,
	lean: float,
) -> None:
	x, y = base
	stem_w = max(1, height // 12)
	top_y = y - height

	draw.line((x, y, x + lean, top_y), fill=(*LEAF_DARK, 255), width=stem_w)

	grain_w = max(2, height // 8)
	grain_h = max(2, height // 10)
	steps = 5
	for step in range(steps):
		t = step / max(1, steps - 1)
		gy = y - height + step * (height // steps)
		gx = x + lean * t
		direction = -1 if step % 2 == 0 else 1
		draw.ellipse(
			(
				gx + direction * grain_w // 2 - grain_w // 2,
				gy - grain_h // 2,
				gx + direction * grain_w // 2 + grain_w // 2,
				gy + grain_h // 2,
			),
			fill=(*LEAF, 240 if step % 2 else 255),
		)


def _draw_leaf_cluster(draw: ImageDraw.ImageDraw, anchor: tuple[int, int], size: int) -> None:
	x, y = anchor
	leaf = max(2, size // 8)
	draw.ellipse((x - leaf * 2, y - leaf, x, y + leaf), fill=(*LEAF, 255))
	draw.ellipse((x, y - leaf * 2, x + leaf * 2, y), fill=(*LEAF_DARK, 255))


def _render_icon(size: int) -> Image.Image:
	image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
	draw = ImageDraw.Draw(image)

	margin = _scale(18, size)
	radius = _scale(54, size)
	panel = (margin, margin, size - margin, size - margin)

	_draw_vertical_gradient_round_rect(draw, panel, radius, TEAL_TOP, TEAL_BOTTOM)
	draw.rounded_rectangle(panel, radius=radius, outline=(*TEAL_EDGE, 255), width=max(1, _scale(4, size)))

	gloss_h = _scale(52, size)
	draw.rounded_rectangle(
		(
			panel[0] + _scale(12, size),
			panel[1] + _scale(10, size),
			panel[0] + _scale(150, size),
			panel[1] + gloss_h,
		),
		radius=_scale(36, size),
		fill=(255, 255, 255, 28),
	)

	coin_r = _scale(72, size)
	coin_cx = size // 2
	coin_cy = size // 2 + _scale(6, size)

	if size >= 48:
		_draw_wheat_stalk(draw, (coin_cx - coin_r - _scale(8, size), panel[3] - _scale(24, size)), _scale(78, size), -8)
		_draw_wheat_stalk(draw, (coin_cx + coin_r + _scale(8, size), panel[3] - _scale(20, size)), _scale(70, size), 8)

	_draw_radial_coin(draw, (coin_cx, coin_cy), coin_r)

	if size >= 32:
		_draw_star(draw, (coin_cx, coin_cy + _scale(2, size)), max(4, coin_r // 2))

	if size >= 56:
		_draw_leaf_cluster(draw, (panel[2] - _scale(36, size), panel[3] - _scale(28, size)), size)

	return image


def draw_icon(size: int) -> Image.Image:
	"""Render with supersampling so small ICO sizes stay smooth."""
	if size >= 128:
		return _render_icon(size)

	scale = 4 if size <= 24 else 2
	rendered = _render_icon(size * scale)
	return rendered.resize((size, size), Image.Resampling.LANCZOS)


def main() -> Path:
	ASSETS_DIR.mkdir(parents=True, exist_ok=True)
	images = [draw_icon(icon_size) for icon_size in SIZES]
	images[0].save(
		ICON_PATH,
		format="ICO",
		sizes=[(icon_size, icon_size) for icon_size in SIZES],
		append_images=images[1:],
	)
	images[-1].save(PNG_PATH, format="PNG")
	return ICON_PATH


if __name__ == "__main__":
	print(main())
