"""Generate `web/public/favicon.ico` from the same mark as `favicon.svg`.

Why a second icon at all: `favicon.svg` covers every current browser, but one
that does not understand SVG icons ignores the `<link>` and falls back to
requesting `/favicon.ico` at the origin root. With no file there that is a 404
on every page load, logged to the console -- which is how Lighthouse found it,
scoring Best Practices 96 on an otherwise clean page.

Why generated rather than committed by hand: a binary asset with no source is
the kind of thing nobody can edit later. This script is the source. Run with
`--check` to verify the committed file still matches, which is what CI does.

The ICO is written directly rather than through an imaging library. The format
is a small header plus a bottom-up BGRA bitmap, and this repository does not
otherwise need Pillow -- a dependency for one 32x32 image would cost more than
the sixty lines it saves.

Usage:
    python scripts/generate_favicon.py           # write the file
    python scripts/generate_favicon.py --check   # exit 1 if it is stale
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ICO_PATH = Path("web/public/favicon.ico")

#: The light palette, because an .ico cannot follow the reader's theme the way
#: the SVG does. An opaque plate reads against a tab strip of any colour; bars
#: on transparency would vanish into a light one.
PLATE = (0xFF, 0xFF, 0xFF)
BAR = (0x24, 0x56, 0xD6)

#: (x, y, width, height) in a 32x32 grid, scaled for smaller sizes. Unequal
#: heights: the mark is a comparison, which is what the project is for.
BARS_32 = [(6, 19, 5, 8), (13, 11, 5, 16), (21, 5, 5, 22)]

SIZES = (16, 32)


def _render(size: int) -> list[list[tuple[int, int, int, int]]]:
    """One RGBA image, top row first."""
    scale = size / 32
    plate_radius = max(1, round(size / 8))
    bars = [tuple(round(v * scale) for v in bar) for bar in BARS_32]

    rows: list[list[tuple[int, int, int, int]]] = []
    for y in range(size):
        row: list[tuple[int, int, int, int]] = []
        for x in range(size):
            # Rounded corners, cut as a quarter-circle rather than a bevel so
            # the shape survives being drawn 16 pixels wide.
            cx = min(x, size - 1 - x)
            cy = min(y, size - 1 - y)
            if cx < plate_radius and cy < plate_radius:
                dx, dy = plate_radius - 1 - cx, plate_radius - 1 - cy
                if dx * dx + dy * dy > plate_radius * plate_radius:
                    row.append((0, 0, 0, 0))
                    continue
            pixel = (*PLATE, 255)
            for bx, by, bw, bh in bars:
                if bx <= x < bx + bw and by <= y < by + bh:
                    pixel = (*BAR, 255)
                    break
            row.append(pixel)
        rows.append(row)
    return rows


def _dib(size: int) -> bytes:
    """A BITMAPINFOHEADER image: bottom-up BGRA, then the 1bpp AND mask.

    The mask is required by the format even for 32-bit images, and the header
    declares twice the real height because it describes both planes.
    """
    rows = _render(size)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # header size
        size,
        size * 2,  # colour plane + mask plane
        1,  # planes
        32,  # bits per pixel
        0,  # BI_RGB, uncompressed
        0,  # image size, may be zero when uncompressed
        0,
        0,
        0,
        0,
    )
    pixels = bytearray()
    for row in reversed(rows):
        for r, g, b, a in row:
            pixels += bytes((b, g, r, a))

    # Every pixel's transparency already lives in the alpha channel, so the
    # mask is all-zero; it still has to be present and 4-byte aligned per row.
    mask_row_bytes = ((size + 31) // 32) * 4
    mask = bytes(mask_row_bytes * size)
    return header + bytes(pixels) + mask


def build() -> bytes:
    images = [_dib(size) for size in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, image in zip(SIZES, images, strict=True):
        out += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,
            size if size < 256 else 0,
            0,  # palette size; 0 for true colour
            0,  # reserved
            1,  # planes
            32,  # bits per pixel
            len(image),
            offset,
        )
        offset += len(image)
    for image in images:
        out += image
    return bytes(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed icon differs from this source",
    )
    args = parser.parse_args(argv)

    icon = build()
    if args.check:
        if not ICO_PATH.is_file():
            print(f"{ICO_PATH} is missing; run scripts/generate_favicon.py", file=sys.stderr)
            return 1
        if ICO_PATH.read_bytes() != icon:
            print(
                f"{ICO_PATH} is stale; run scripts/generate_favicon.py to regenerate",
                file=sys.stderr,
            )
            return 1
        print(f"{ICO_PATH} matches its source ({len(icon)} bytes, sizes {SIZES}).")
        return 0

    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ICO_PATH.write_bytes(icon)
    print(f"wrote {ICO_PATH} ({len(icon)} bytes, sizes {SIZES})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
