from __future__ import annotations
import cv2
import numpy as np
from PIL import Image

def restore_regions(source: Image.Image, regions: list[dict]) -> tuple[Image.Image, list[int]]:
    """Inpaint only unprotected region ink; retain horizontal ruling via a protected line mask."""
    rgb = np.asarray(source.convert("RGB")); gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    combined = np.zeros(gray.shape, np.uint8); failed=[]
    for n, region in enumerate(regions):
        if region.get("protected"): continue
        x,y,w,h = map(int, region["bbox"]); x=max(0,x); y=max(0,y); x2=min(gray.shape[1],x+w); y2=min(gray.shape[0],y+h)
        if x2<=x or y2<=y: failed.append(n); continue
        roi=gray[y:y2,x:x2]
        # Dark connected content becomes candidate ink; long horizontal strokes are likely ruling.
        mask=np.where(roi < 150, 255, 0).astype(np.uint8)
        horizontal=cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT,(max(12, (x2-x)//3),1)))
        mask=cv2.subtract(mask,horizontal)
        combined[y:y2,x:x2]=cv2.max(combined[y:y2,x:x2],mask)
    try:
        clean=cv2.inpaint(rgb,combined,3,cv2.INPAINT_TELEA)
    except cv2.error:
        return source.copy(), list(range(len(regions)))
    return Image.fromarray(clean), failed
