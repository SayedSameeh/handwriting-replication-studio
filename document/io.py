from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageOps
import pymupdf

def load_pages(path: str | Path, dpi: int = 300) -> list[Image.Image]:
    """Load raster images or render every PDF page at dpi without changing its aspect ratio."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() == ".pdf":
        pages = []
        with pymupdf.open(path) as doc:
            for page in doc:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
                pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        if not pages:
            raise ValueError("The PDF contains no pages")
        return pages
    try:
        with Image.open(path) as im:
            frames = getattr(im, "n_frames", 1)
            return [ImageOps.exif_transpose(im.seek(i) or im).convert("RGB").copy() for i in range(frames)]
    except Exception as e:
        raise ValueError(f"Unsupported or unreadable image: {e}") from e
