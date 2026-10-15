"""Build a real, monochrome TrueType font from reviewed character-sheet crops."""
from __future__ import annotations

from pathlib import Path
import re
import cv2
import numpy as np
from fontTools.agl import UV2AGL
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

UNITS=1000
ASCENT=820
DESCENT=-240


def _glyph_name(char: str) -> str:
    if char==" ": return "space"
    return UV2AGL.get(ord(char),f"uni{ord(char):04X}")


def _contours(mask: np.ndarray):
    found,hierarchy=cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None: return [],None
    contours=[]
    for index,cnt in enumerate(found):
        area=abs(cv2.contourArea(cnt))
        if area<1: continue
        epsilon=max(.6,cv2.arcLength(cnt,True)*.002)
        points=cv2.approxPolyDP(cnt,epsilon,True).reshape(-1,2)
        if len(points)>=3: contours.append((index,points))
    return contours,hierarchy[0]


def _make_glyph(sample,scale:float,char:str,is_ttf:bool):
    pen=TTGlyphPen(None) if is_ttf else T2CharStringPen(310,None)
    if char==" " or sample is None:
        return (pen.glyph() if is_ttf else pen.getCharString(private=None,globalSubrs=None)), 310
    mask=sample["mask"] if isinstance(sample,dict) else sample
    baseline=float(sample.get("baseline",mask.shape[0]) if isinstance(sample,dict) else mask.shape[0])
    contours,hierarchy=_contours(mask)
    if not contours:
        return (pen.glyph() if is_ttf else pen.getCharString(private=None,globalSubrs=None)), 310
    ys,xs=np.where(mask>0)
    width=int(xs.max())+1; left=int(xs.min()); top=int(ys.min())
    width_scale=min(scale,650/max(width-left,1))
    advance=max(180,int((width-left)*width_scale+100))
    xoff=50
    for index,points in contours:
        mapped=[(round(xoff+(float(x)-left)*width_scale),round((baseline-float(y))*width_scale)) for x,y in points]
        # TrueType outer contours wind clockwise; holes wind the opposite direction.
        signed=sum(mapped[i][0]*mapped[(i+1)%len(mapped)][1]-mapped[(i+1)%len(mapped)][0]*mapped[i][1] for i in range(len(mapped)))
        is_hole=hierarchy[index][3] != -1
        if (not is_hole and signed>0) or (is_hole and signed<0): mapped.reverse()
        pen.moveTo(mapped[0])
        for point in mapped[1:]: pen.lineTo(point)
        pen.closePath()
    if not is_ttf: pen.width=advance
    return (pen.glyph() if is_ttf else pen.getCharString(private=None,globalSubrs=None)),advance


def build_font(glyph_samples:dict[str,dict|np.ndarray], output:str|Path, family_name:str="My Handwriting") -> dict:
    """Compile reviewed glyph masks into a TTF or OTF using one sample per character."""
    if not glyph_samples: raise ValueError("There are no reviewed character samples to build a font from.")
    uppercase=[]
    for char,sample in glyph_samples.items():
        if char.isupper() and sample is not None:
            mask=sample["mask"] if isinstance(sample,dict) else sample
            base=float(sample.get("baseline",mask.shape[0]) if isinstance(sample,dict) else mask.shape[0])
            ys=np.where(mask>0)[0]
            if len(ys): uppercase.append(base-float(ys.min()))
    ref=float(np.median(uppercase)) if uppercase else float(np.median([ (s["mask"] if isinstance(s,dict) else s).shape[0] for s in glyph_samples.values() if s is not None]))
    scale=min(18.0,700/max(ref,1))
    cmap={ord(ch):_glyph_name(ch) for ch in glyph_samples}
    order=[".notdef"]+list(dict.fromkeys(cmap.values()))
    output=Path(output); is_ttf=output.suffix.lower()!='.otf'
    glyphs={}; charstrings={}; metrics={}
    pen=TTGlyphPen(None) if is_ttf else T2CharStringPen(620,None)
    pen.moveTo((50,0)); pen.lineTo((550,0)); pen.lineTo((550,700)); pen.lineTo((50,700)); pen.closePath()
    missing_glyph=pen.glyph() if is_ttf else pen.getCharString(private=None,globalSubrs=None)
    if is_ttf: glyphs[".notdef"]=missing_glyph
    else: charstrings[".notdef"]=missing_glyph
    metrics[".notdef"]=(620,0)
    for char,sample in glyph_samples.items():
        name=cmap[ord(char)]
        built,advance=_make_glyph(sample,scale,char,is_ttf)
        if is_ttf: glyphs[name]=built
        else: charstrings[name]=built
        metrics[name]=(advance,0)
    if "space" not in glyphs:
        if "space" not in charstrings:
            pen=TTGlyphPen(None) if is_ttf else T2CharStringPen(310,None)
            empty=pen.glyph() if is_ttf else pen.getCharString(private=None,globalSubrs=None)
            if is_ttf: glyphs["space"]=empty
            else: charstrings["space"]=empty
            metrics["space"]=(310,0); order.append("space"); cmap[32]="space"
    fb=FontBuilder(UNITS,isTTF=is_ttf)
    fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
    if is_ttf: fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT,descent=DESCENT)
    family=re.sub(r"[^A-Za-z0-9 ]","",family_name).strip() or "My Handwriting"
    ps_name=(re.sub(r"[^A-Za-z0-9]","",family) or "MyHandwriting")+"-Regular"
    if not is_ttf: fb.setupCFF(ps_name,{"FamilyName":family,"FullName":family+" Regular","Weight":"Regular"},charstrings,{})
    fb.setupNameTable({"familyName":family,"styleName":"Regular","uniqueFontIdentifier":family+" Regular 1.0","fullName":family+" Regular","psName":ps_name,"version":"Version 1.0"})
    fb.setupOS2(sTypoAscender=ASCENT,sTypoDescender=DESCENT,usWinAscent=ASCENT,usWinDescent=abs(DESCENT))
    fb.setupPost(); fb.setupMaxp()
    output.parent.mkdir(parents=True,exist_ok=True); fb.save(output)
    return {"font_path":str(output.resolve()),"font_format":"TrueType outlines (.ttf)" if is_ttf else "CFF OpenType outlines (.otf)","family_name":family,"glyph_count":len([ch for ch in glyph_samples if ch!=' ']),"scale":scale,"units_per_em":UNITS,"renderer":"user_glyph_font"}


def build_ttf(glyph_samples:dict[str,dict|np.ndarray], output:str|Path, family_name:str="My Handwriting") -> dict:
    """Backward-compatible TrueType builder entrypoint."""
    return build_font(glyph_samples,output,family_name)
