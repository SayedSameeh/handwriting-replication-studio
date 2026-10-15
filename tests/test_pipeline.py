import tempfile, unittest
from pathlib import Path
from PIL import Image, ImageDraw
from document.io import load_pages
from image_processing.restore import restore_regions
from rendering.page import render_page
from project.store import save_project, load_project
from export.pdf import export_pdf
from quality.checks import validate_page

tempfile.tempdir = str(Path(__file__).resolve().parents[1] / '.test-tmp')
Path(tempfile.tempdir).mkdir(exist_ok=True)

class PipelineTests(unittest.TestCase):
    def sample(self):
        im=Image.new('RGB',(600,800),'white'); d=ImageDraw.Draw(im); d.line((30,100,570,100),fill='#aabbcc',width=1); d.text((60,70),'Sample text',fill='black'); return im
    def test_image_import_and_multi_frame(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.png'; self.sample().save(p); self.assertEqual(load_pages(p)[0].size,(600,800))
            multi=Path(d)/'multi.pdf'; export_pdf([self.sample(),Image.new('RGB',(300,400),'white')],multi,dpi=300)
            pages=load_pages(multi,dpi=300); self.assertEqual(len(pages),2); self.assertEqual(pages[1].size,(300,400))
    def test_invalid_import_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'invalid.png'; p.write_text('not an image')
            with self.assertRaises(ValueError): load_pages(p)
    def test_mask_restoration_and_geometry(self):
        im=self.sample(); clean,failed=restore_regions(im,[{'bbox':[50,55,200,35]}]); self.assertEqual(clean.size,im.size); self.assertEqual(failed,[])
    def test_project_roundtrip_and_correction(self):
        with tempfile.TemporaryDirectory() as d:
            project={'pages':[{'original':self.sample(),'preview':None,'regions':[{'bbox':[1,2,30,10],'text':'Corrected','confidence':.4,'protected':False}]}],'profile':{},'settings':{}}
            save_project(d,project); got=load_project(d); self.assertEqual(got['pages'][0]['regions'][0]['text'],'Corrected'); self.assertEqual(got['pages'][0]['original'].size,(600,800))
    def test_pdf_pages_keep_dimensions(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'out.pdf'; export_pdf([self.sample()],f,dpi=300)
            doc=pymupdf.open(f); rect=doc[0].rect; doc.close(); self.assertAlmostEqual(rect.width,600*72/300,places=2); self.assertAlmostEqual(rect.height,800*72/300,places=2)
    def test_quality_flags(self):
        p={'original':self.sample(),'preview':None,'regions':[{'bbox':[0,0,20,20],'confidence':.2},{'bbox':[10,10,20,20],'confidence':1}]}
        issues=validate_page(p); self.assertTrue(any('low OCR confidence' in x for x in issues)); self.assertTrue(any('overlap' in x for x in issues))

if __name__=='__main__': unittest.main()
