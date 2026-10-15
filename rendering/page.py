from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont
import random

def render_page(clean: Image.Image, regions: list[dict], profile: dict, settings: dict) -> tuple[Image.Image,list[int]]:
    out=clean.convert("RGB").copy(); failed=[]; draw=ImageDraw.Draw(out)
    font_path=profile.get("font_path") or settings.get("font_path") or "C:/Windows/Fonts/SCRIPTBL.TTF"
    for i,r in enumerate(regions):
        if r.get("protected"): continue
        x,y,w,h=map(int,r["bbox"]); text=r.get("text","")
        if not text.strip(): continue
        size=max(8,min(int(h*.78), int(settings.get("font_size", h*.78))))
        try: font=ImageFont.truetype(font_path,size=size)
        except OSError: font=ImageFont.load_default()
        color=settings.get("ink_color", "#172a42")
        box=draw.textbbox((0,0),text,font=font); tw=box[2]-box[0]; th=box[3]-box[1]
        scale=min(1.0,(w-2)/max(tw,1),(h-2)/max(th,1))
        if scale < .56: failed.append(i); continue
        if scale < .98:
            font=ImageFont.truetype(font_path,max(8,int(size*scale))) if font_path.lower().endswith((".ttf",".otf")) else font
            box=draw.textbbox((0,0),text,font=font); th=box[3]-box[1]
        rng=random.Random(i+int(settings.get("variation_seed",11)))
        baseline=int(r.get("baseline",y+h)); offset=rng.randint(-1,1) if settings.get("variation",True) else 0
        final_box=draw.textbbox((0,0),text,font=font)
        text_origin=(x,baseline-final_box[3]+offset)
        ink_box=draw.textbbox(text_origin,text,font=font)
        if ink_box[0] < x or ink_box[1] < y or ink_box[2] > x+w or ink_box[3] > y+h:
            failed.append(i); continue
        if ink_box[0] < 0 or ink_box[1] < 0 or ink_box[2] > out.width or ink_box[3] > out.height:
            failed.append(i); continue
        draw.text(text_origin,text,font=font,fill=color)
    return out,failed
