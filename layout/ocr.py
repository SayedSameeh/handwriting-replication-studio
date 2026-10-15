from __future__ import annotations
from PIL import Image

def recognize(image: Image.Image) -> list[dict]:
    """Tesseract-backed OCR; empty result means the optional engine is unavailable or found nothing."""
    try:
        import pytesseract
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config="--psm 6")
    except Exception:
        return []
    lines: dict[tuple[int,int,int], list[int]] = {}
    for i, raw in enumerate(data["text"]):
        word = raw.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)
    out = []
    for indices in lines.values():
        xs = [data["left"][i] for i in indices]; ys = [data["top"][i] for i in indices]
        rs = [data["left"][i] + data["width"][i] for i in indices]; bs = [data["top"][i] + data["height"][i] for i in indices]
        words = [data["text"][i].strip() for i in indices]
        conf = [float(data["conf"][i]) for i in indices if float(data["conf"][i]) >= 0]
        confidence=round(sum(conf)/len(conf)/100, 3) if conf else 0
        # Keep uncertain OCR regions unchanged until the user explicitly reviews them.
        out.append({"text": " ".join(words), "bbox": [min(xs), min(ys), max(rs)-min(xs), max(bs)-min(ys)], "baseline": max(bs), "confidence": confidence, "locked": False, "protected": confidence < .5, "status": "review"})
    return out
