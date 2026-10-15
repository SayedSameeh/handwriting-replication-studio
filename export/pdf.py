from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
import io

def export_pdf(images: list[Image.Image], path: str|Path, dpi: int=300) -> None:
    if not images: raise ValueError('There are no pages to export')
    first=images[0]; c=canvas.Canvas(str(path),pagesize=(first.width*72/dpi,first.height*72/dpi))
    for im in images:
        c.setPageSize((im.width*72/dpi,im.height*72/dpi)); b=io.BytesIO(); im.convert('RGB').save(b,format='PNG'); b.seek(0)
        c.drawImage(ImageReader(b),0,0,width=im.width*72/dpi,height=im.height*72/dpi); c.showPage()
    c.save()
