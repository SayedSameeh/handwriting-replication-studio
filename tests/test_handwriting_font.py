import tempfile
import unittest
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from handwriting.sheet import PAGE_W, create_character_sheet, extract_glyphs, load_sheet_images, sheet_manifest
from handwriting.font_builder import build_font
from project.store import save_project, load_project
from main import Studio

TEMP_ROOT=Path(__file__).resolve().parents[1]/'.test-tmp'
TEMP_ROOT.mkdir(exist_ok=True)


class HandwritingFontTests(unittest.TestCase):
    def test_printable_sheet_extracts_photo_pages_and_builds_ttf(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root=Path(tmp); blank=root/'blank.pdf'; create_character_sheet(blank)
            pages=load_sheet_images(blank); scale=pages[0].width/PAGE_W
            photos=[]
            # Synthetic pen strokes exercise cell extraction without requiring personal samples.
            for page_no,(image,meta) in enumerate(zip(pages,sheet_manifest())):
                draw=ImageDraw.Draw(image)
                for cell in meta['characters']:
                    x,y,w,h=cell['bbox']; x*=scale; y*=scale; w*=scale; h*=scale
                    draw.line((x+12,y+8,x+w/2,y+h-8,x+w-12,y+8),fill=(25,25,25),width=8)
                array=np.asarray(image); h,w=array.shape[:2]
                src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
                dst=np.float32([[70,50],[w-50,0],[w-10,h-50],[0,h-10]])
                warped=cv2.warpPerspective(array,cv2.getPerspectiveTransform(src,dst),(w,h),borderValue=(255,255,255))
                photo=root/f'sheet-{page_no+1}.jpg'; Image.fromarray(warped).save(photo,quality=95); photos.append(photo)
            glyphs,details=extract_glyphs(photos)
            self.assertEqual(details['glyph_count'],len(sheet_manifest()[0]['characters'])+len(sheet_manifest()[1]['characters']))
            font_path=root/'sample.ttf'; info=build_font(glyphs,font_path,'Test Handwriting')
            self.assertTrue(font_path.is_file()); self.assertEqual(info['renderer'],'user_glyph_font')
            font=ImageFont.truetype(str(font_path),36); self.assertGreater(font.getlength('Aa9!'),0)
            otf_path=root/'sample.otf'; otf_info=build_font(glyphs,otf_path,'Test Handwriting'); self.assertTrue(otf_path.is_file())
            otf=ImageFont.truetype(str(otf_path),36); self.assertGreater(otf.getlength('Aa9!'),0)
            project_path=root/'project'; original=Image.new('RGB',(80,80),'white')
            save_project(project_path,{'pages':[{'original':original,'preview':original.copy(),'regions':[]}],'profile':{'name':'Test','font_path':str(font_path),'renderer':'user_glyph_font'},'settings':{}})
            reopened=load_project(project_path)
            self.assertTrue(Path(reopened['profile']['font_path']).is_file())
            self.assertEqual(reopened['profile']['renderer'],'user_glyph_font')

    def test_incomplete_sheet_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            blank=Path(tmp)/'blank.pdf'; create_character_sheet(blank)
            with self.assertRaisesRegex(ValueError,'Only 0'):
                extract_glyphs([blank])

    def test_blank_baseline_is_not_treated_as_written_glyphs(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            blank=Path(tmp)/'blank.pdf'; create_character_sheet(blank)
            with self.assertRaisesRegex(ValueError,'Only 0'):
                extract_glyphs([blank])

    def test_unknown_character_keeps_source_region_untouched(self):
        original=Image.new('RGB',(160,80),'white'); ImageDraw.Draw(original).text((20,20),'AB',fill='black')
        page={'original':original,'regions':[{'bbox':[10,10,100,40],'text':'AB','protected':False}]}
        preview,failed,overflow=Studio._render_task(page,{'characters':['A']},{'variation':False})
        self.assertTrue(np.array_equal(np.asarray(preview),np.asarray(original)))
        self.assertEqual(overflow,[0])


if __name__=='__main__': unittest.main()
