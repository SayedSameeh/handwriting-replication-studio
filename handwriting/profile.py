from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageStat
import json
from .sheet import extract_glyphs
from .font_builder import build_font

def analyze(paths: list[str]) -> dict:
    heights=[]; contrasts=[]
    for p in paths:
        with Image.open(p) as im:
            g=im.convert("L"); heights.append(max(1, int(g.height * .055))); contrasts.append(round(ImageStat.Stat(g).stddev[0],1))
    return {"name":"My handwriting", "samples":paths, "estimated_height":int(sum(heights)/max(1,len(heights))), "contrast":sum(contrasts)/max(1,len(contrasts)), "font_path":"", "renderer":"font_variation_fallback"}

def save_profile(profile: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(profile, indent=2), encoding="utf-8")

def load_profile(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def create_profile_from_sheets(sheet_paths: list[str], font_path: str | Path, profile_path: str | Path) -> dict:
    """Extract a completed app character sheet, compile its font, and persist profile metadata."""
    glyphs,details=extract_glyphs(sheet_paths)
    font_info=build_font(glyphs,font_path)
    profile={"name":font_info["family_name"],"renderer":"user_glyph_font","font_path":font_info["font_path"],"font_format":font_info["font_format"],"source_sheets":details["source_sheet"],"glyph_count":details["glyph_count"],"missing_characters":details["missing_characters"],"metrics":{"median_glyph_height_px":details["median_glyph_height"],"median_glyph_width_px":details["median_glyph_width"],"mean_ink_gray":details["ink_gray_mean"]}}
    save_profile(profile,profile_path)
    return profile
