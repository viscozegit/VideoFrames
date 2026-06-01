"""Generate macOS .icns icon for Video Frames app.

Design: rounded-square gradient background with a stylized film strip
showing three frame thumbnails — visually communicating "video → frames".
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONSET = ASSETS / "AppIcon.iconset"
ICNS_PATH = ASSETS / "AppIcon.icns"

# macOS iconset sizes: (filename, pixel size)
ICONSET_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

BASE_SIZE = 1024  # render master at 1024 then downscale


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _gradient_bg(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        color = _lerp(top, bottom, t)
        for x in range(size):
            px[x, y] = color
    return img


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def render_master(size: int = BASE_SIZE) -> Image.Image:
    # macOS Big Sur icon shape: ~22.37% corner radius of the icon size
    radius = int(size * 0.2237)

    # Background: indigo → violet gradient
    bg = _gradient_bg(size, top=(99, 102, 241), bottom=(139, 92, 246))

    # Apply rounded-square mask
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), _rounded_mask(size, radius))

    draw = ImageDraw.Draw(icon)

    # --- Film strip ---
    # Strip occupies roughly the middle band of the icon
    strip_h = int(size * 0.48)
    strip_w = int(size * 0.78)
    strip_x = (size - strip_w) // 2
    strip_y = (size - strip_h) // 2
    strip_radius = int(size * 0.04)

    # Soft shadow under the strip
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_offset = int(size * 0.012)
    shadow_draw.rounded_rectangle(
        (strip_x, strip_y + shadow_offset, strip_x + strip_w, strip_y + strip_h + shadow_offset),
        radius=strip_radius,
        fill=(0, 0, 0, 90),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=size * 0.012))
    icon.alpha_composite(shadow)

    # Film strip body (near-black)
    draw.rounded_rectangle(
        (strip_x, strip_y, strip_x + strip_w, strip_y + strip_h),
        radius=strip_radius,
        fill=(24, 24, 27, 255),
    )

    # Perforations (sprocket holes) on top and bottom edges
    perf_count = 8
    perf_w = int(strip_w / (perf_count * 1.6))
    perf_h = int(size * 0.028)
    perf_radius = int(perf_h * 0.35)
    perf_margin_y = int(size * 0.018)
    gap = (strip_w - perf_w * perf_count) / (perf_count + 1)
    for i in range(perf_count):
        px0 = int(strip_x + gap + i * (perf_w + gap))
        # top row
        py0_top = strip_y + perf_margin_y
        draw.rounded_rectangle(
            (px0, py0_top, px0 + perf_w, py0_top + perf_h),
            radius=perf_radius,
            fill=(255, 255, 255, 235),
        )
        # bottom row
        py0_bot = strip_y + strip_h - perf_margin_y - perf_h
        draw.rounded_rectangle(
            (px0, py0_bot, px0 + perf_w, py0_bot + perf_h),
            radius=perf_radius,
            fill=(255, 255, 255, 235),
        )

    # --- Three frame thumbnails inside the strip ---
    inner_margin_x = int(size * 0.035)
    inner_margin_y = perf_margin_y + perf_h + int(size * 0.018)
    frames_area_x = strip_x + inner_margin_x
    frames_area_y = strip_y + inner_margin_y
    frames_area_w = strip_w - inner_margin_x * 2
    frames_area_h = strip_h - inner_margin_y * 2

    frame_count = 3
    frame_gap = int(size * 0.022)
    frame_w = (frames_area_w - frame_gap * (frame_count - 1)) // frame_count
    frame_h = frames_area_h
    frame_radius = int(size * 0.018)

    # Frame fill colors — bright, progressively varied to suggest motion
    frame_fills = [
        ((253, 224, 71), (251, 146, 60)),    # yellow → orange
        ((96, 165, 250), (59, 130, 246)),    # light blue → blue
        ((52, 211, 153), (16, 185, 129)),    # light green → green
    ]

    for i in range(frame_count):
        fx = frames_area_x + i * (frame_w + frame_gap)
        fy = frames_area_y
        # Build a small gradient tile for the frame
        tile = _gradient_bg(max(frame_w, frame_h), frame_fills[i][0], frame_fills[i][1])
        tile = tile.resize((frame_w, frame_h))
        tile_rgba = tile.convert("RGBA")
        # Rounded mask for the tile
        tile_mask = Image.new("L", (frame_w, frame_h), 0)
        ImageDraw.Draw(tile_mask).rounded_rectangle(
            (0, 0, frame_w - 1, frame_h - 1), radius=frame_radius, fill=255
        )
        icon.paste(tile_rgba, (fx, fy), tile_mask)

    # --- Small play triangle on the center frame for a "video" cue ---
    center_idx = 1
    cx0 = frames_area_x + center_idx * (frame_w + frame_gap)
    cy0 = frames_area_y
    tri_size = int(min(frame_w, frame_h) * 0.42)
    tri_cx = cx0 + frame_w // 2
    tri_cy = cy0 + frame_h // 2
    # Nudge optical center slightly right for the triangle
    tri_offset = int(tri_size * 0.08)
    tri_points = [
        (tri_cx - tri_size // 2 + tri_offset, tri_cy - tri_size // 2),
        (tri_cx - tri_size // 2 + tri_offset, tri_cy + tri_size // 2),
        (tri_cx + tri_size // 2 + tri_offset, tri_cy),
    ]
    draw.polygon(tri_points, fill=(255, 255, 255, 240))

    # Subtle top-down highlight that fades out smoothly (no hard band)
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hl_alpha = Image.new("L", (size, size), 0)
    hl_px = hl_alpha.load()
    for y in range(size):
        t = y / (size - 1)
        # fade from ~28 at top to 0 at midpoint, 0 below
        a = int(max(0.0, 1.0 - t * 2.0) * 28)
        if a:
            for x in range(size):
                hl_px[x, y] = a
    highlight.putalpha(hl_alpha)
    # Tint to white
    white = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    white.putalpha(hl_alpha)
    # Mask to the rounded-icon shape
    icon_mask = _rounded_mask(size, radius)
    icon.alpha_composite(Image.composite(white, Image.new("RGBA", (size, size)), icon_mask))

    return icon


def build_iconset(master: Image.Image) -> None:
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True, exist_ok=True)
    for name, pixel_size in ICONSET_SIZES:
        resized = master.resize((pixel_size, pixel_size), Image.LANCZOS)
        resized.save(ICONSET / name, format="PNG")


def build_icns() -> None:
    subprocess.run(
        ["iconutil", "--convert", "icns", str(ICONSET), "--output", str(ICNS_PATH)],
        check=True,
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = render_master(BASE_SIZE)
    # Save a 1024 preview alongside the iconset
    master.save(ASSETS / "AppIcon_1024.png", format="PNG")
    build_iconset(master)
    build_icns()
    print(f"Wrote {ICNS_PATH}")


if __name__ == "__main__":
    main()
