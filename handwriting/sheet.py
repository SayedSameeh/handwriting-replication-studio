"""Printable glyph-sheet templates and conversion of completed PDF/JPG sheets to glyph crops."""
from __future__ import annotations

from pathlib import Path
import string
import cv2
import numpy as np
from PIL import Image
import pymupdf
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = 595.0, 842.0
TARGET_W, TARGET_H = 2480, 3508
COLS, ROWS = 5, 9
CHARS = list(string.ascii_uppercase + string.ascii_lowercase + string.digits + ".,!?'\"-:;()+=/[]{}<>×÷√πΣ")
CHARS = list(dict.fromkeys(CHARS))
LEFT, TOP, RIGHT, BOTTOM = 34.0, 72.0, 34.0, 36.0
CELL_W = (PAGE_W - LEFT - RIGHT) / COLS
CELL_H = (PAGE_H - TOP - BOTTOM) / ROWS


def _cell(char_index: int) -> tuple[int, tuple[float, float, float, float], float]:
    page_index, local = divmod(char_index, COLS * ROWS)
    row, col = divmod(local, COLS)
    x, y = LEFT + col * CELL_W, TOP + row * CELL_H
    return page_index, (x + 9, y + 18, CELL_W - 18, CELL_H - 27), y + CELL_H - 20


def sheet_manifest() -> list[dict]:
    pages=[]
    for i,ch in enumerate(CHARS):
        page,bbox,baseline=_cell(i)
        while len(pages)<=page: pages.append({"characters":[]})
        pages[page]["characters"].append({"char":ch,"bbox":bbox,"baseline":baseline})
    return pages


def _draw_marker(c: canvas.Canvas, x: float, y: float) -> None:
    """Nested square fiducial, with (x,y) as the page's top-left coordinate."""
    c.setFillColorRGB(0,0,0); c.rect(x-8,y-8,16,16,stroke=0,fill=1)
    c.setFillColorRGB(1,1,1); c.rect(x-5,y-5,10,10,stroke=0,fill=1)
    c.setFillColorRGB(0,0,0); c.rect(x-2,y-2,4,4,stroke=0,fill=1)


def create_character_sheet(path: str | Path) -> None:
    """Create the 2-page A4 printable template used by the local profile builder."""
    pages=sheet_manifest(); c=canvas.Canvas(str(path),pagesize=(PAGE_W,PAGE_H))
    for pno,page in enumerate(pages):
        c.setFillColorRGB(.10,.16,.23); c.setFont("Helvetica-Bold",15)
        c.drawString(LEFT,PAGE_H-39,f"Handwriting Studio · Character sheet {pno+1} of {len(pages)}")
        c.setFont("Helvetica",8); c.setFillColorRGB(.3,.35,.4)
        c.drawString(LEFT,PAGE_H-53,"Write one character in each box. Use a dark pen and keep all four corner markers visible.")
        c.setStrokeColorRGB(.55,.62,.69); c.setLineWidth(.55)
        for r in range(ROWS+1):
            y=TOP+r*CELL_H; c.line(LEFT,PAGE_H-y,PAGE_W-RIGHT,PAGE_H-y)
        for col in range(COLS+1):
            x=LEFT+col*CELL_W; c.line(x,PAGE_H-TOP,x,PAGE_H-(PAGE_H-BOTTOM))
        for item in page["characters"]:
            x,y,w,h=item["bbox"]; bx=x-9; by=y-18
            label="SPACE (leave blank)" if item["char"]==" " else repr(item["char"])[1:-1]
            c.setFont("Helvetica",8); c.setFillColorRGB(.35,.4,.46); c.drawString(bx+5,PAGE_H-(by+13),label)
            base=item["baseline"]; c.setStrokeColorRGB(.75,.8,.83); c.setDash(2,2); c.line(x,PAGE_H-base,x+w,PAGE_H-base); c.setDash()
        for mx,my in ((24,24),(PAGE_W-24,24),(24,PAGE_H-24),(PAGE_W-24,PAGE_H-24)):
            _draw_marker(c,mx,PAGE_H-my)
        c.showPage()
    c.save()


def _order_points(points: list[tuple[float,float]]) -> np.ndarray:
    pts=np.array(points,dtype=np.float32)
    sums=pts.sum(axis=1); diffs=np.diff(pts,axis=1).reshape(-1)
    return np.array([pts[np.argmin(sums)],pts[np.argmin(diffs)],pts[np.argmax(sums)],pts[np.argmax(diffs)]],dtype=np.float32)


def _rectify_photo(image: Image.Image) -> Image.Image:
    rgb=np.asarray(image.convert("RGB")); gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    bw=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    contours,hier=cv2.findContours(bw,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    if hier is not None:
        for i,cnt in enumerate(contours):
            if hier[0][i][3] != -1 or hier[0][i][2] == -1: continue
            area=cv2.contourArea(cnt); x,y,w,h=cv2.boundingRect(cnt)
            if area<80 or area>gray.size*.02 or not .75<w/max(h,1)<1.3: continue
            child=hier[0][i][2]
            if child<0 or hier[0][child][2]<0: continue
            candidates.append((area,(x+w/2,y+h/2)))
    # Markers can include their nested contours; keep the largest candidate near each corner.
    unique=[]
    for area,pt in sorted(candidates,reverse=True):
        if all(np.linalg.norm(np.array(pt)-np.array(old[1]))>min(gray.shape)*.025 for old in unique): unique.append((area,pt))
    if len(unique)<4:
        raise ValueError("I couldn't find all four sheet markers. Photograph the completed app template flat, with every corner visible, or upload its scanned PDF.")
    pts=[p for _,p in unique[:4]]; ordered=_order_points(pts)
    target=np.array([[24/PAGE_W*TARGET_W,24/PAGE_H*TARGET_H],[(PAGE_W-24)/PAGE_W*TARGET_W,24/PAGE_H*TARGET_H],[(PAGE_W-24)/PAGE_W*TARGET_W,(PAGE_H-24)/PAGE_H*TARGET_H],[24/PAGE_W*TARGET_W,(PAGE_H-24)/PAGE_H*TARGET_H]],dtype=np.float32)
    matrix=cv2.getPerspectiveTransform(ordered,target)
    fixed=cv2.warpPerspective(rgb,matrix,(TARGET_W,TARGET_H),borderValue=(255,255,255))
    return Image.fromarray(fixed)


def load_sheet_images(paths: str | Path | list[str | Path]) -> list[Image.Image]:
    """Read PDF sheets directly or rectify JPG/PNG photographs using the corner markers."""
    if isinstance(paths,(str,Path)): paths=[paths]
    pages=[]
    for path in paths:
        path=Path(path)
        if path.suffix.lower()==".pdf":
            with pymupdf.open(path) as doc:
                for page in doc:
                    pix=page.get_pixmap(matrix=pymupdf.Matrix(TARGET_W/PAGE_W,TARGET_W/PAGE_W),alpha=False)
                    pages.append(Image.frombytes("RGB",(pix.width,pix.height),pix.samples).resize((TARGET_W,TARGET_H)))
        else:
            with Image.open(path) as im:
                if getattr(im,"n_frames",1)>1: raise ValueError("Upload each completed character-sheet JPG separately, or combine the pages into a PDF.")
                pages.append(_rectify_photo(im))
    return pages


def extract_glyphs(path: str | Path | list[str | Path]) -> tuple[dict[str,dict],dict]:
    manifest=sheet_manifest(); images=load_sheet_images(path)
    if len(images)!=len(manifest):
        raise ValueError(f"This sheet needs {len(manifest)} pages, but the file has {len(images)}. Use the complete character sheet generated by the app.")
    glyphs={}; heights=[]; widths=[]; ink_samples=[]
    for page_index,(image,meta) in enumerate(zip(images,manifest)):
        gray=cv2.cvtColor(np.asarray(image.convert("RGB")),cv2.COLOR_RGB2GRAY)
        sx,sy=image.width/PAGE_W,image.height/PAGE_H
        for item in meta["characters"]:
            x,y,w,h=item["bbox"]; x0=int(x*sx); y0=int(y*sy); x1=int((x+w)*sx); y1=int((y+h)*sy)
            roi=gray[y0:y1,x0:x1].copy()
            if roi.size==0: continue
            # Erase the light printed baseline guide while preserving dark pen strokes that touch it.
            line_y=int((item["baseline"]-y)*sy)
            ly0=max(0,line_y-3); ly1=min(roi.shape[0],line_y+4)
            band=roi[ly0:ly1]
            band[band>105]=255
            roi[ly0:ly1]=band
            _,mask=cv2.threshold(cv2.GaussianBlur(roi,(3,3),0),0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
            n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
            keep=np.zeros(mask.shape,np.uint8)
            for ci in range(1,n):
                area=int(stats[ci,cv2.CC_STAT_AREA])
                if area>=max(2,int(mask.size*.000015)): keep[labels==ci]=255
            ys,xs=np.where(keep>0)
            if len(xs):
                gx0,gx1=int(xs.min()),int(xs.max())+1; gy0,gy1=int(ys.min()),int(ys.max())+1
                crop=keep[gy0:gy1,gx0:gx1]
                baseline=(item["baseline"]-y)*sy-gy0
                glyphs[item["char"]]={"mask":crop,"baseline":baseline}
                heights.append(crop.shape[0]); widths.append(crop.shape[1]); ink_samples.append(float(np.mean(roi[gy0:gy1,gx0:gx1][crop>0])))
            elif item["char"]==" ": glyphs[" "]={"mask":np.zeros((1,1),np.uint8),"baseline":0}
    missing=[ch for ch in CHARS if ch not in glyphs and ch!=" "]
    if len(glyphs)<len(CHARS)*.72:
        raise ValueError(f"Only {len(glyphs)} of {len(CHARS)} character cells contain visible ink. Make sure you completed the generated template with dark ink and uploaded every page.")
    details={"glyph_count":len(glyphs),"missing_characters":missing,"median_glyph_height":float(np.median(heights)) if heights else 0,"median_glyph_width":float(np.median(widths)) if widths else 0,"ink_gray_mean":float(np.mean(ink_samples)) if ink_samples else None,"source_sheet":[str(p) for p in ([path] if isinstance(path,(str,Path)) else path)]}
    return glyphs,details
