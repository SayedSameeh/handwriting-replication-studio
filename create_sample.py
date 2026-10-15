from pathlib import Path
from PIL import Image, ImageDraw
from project.store import save_project
from image_processing.restore import restore_regions
from rendering.page import render_page

def main():
    out=Path('sample_project'); out.mkdir(exist_ok=True); im=Image.new('RGB',(1275,1650),'#fbf8ef'); d=ImageDraw.Draw(im)
    for y in range(180,1600,48): d.line((90,y,1190,y),fill='#c7d8e5',width=2)
    d.line((165,100,165,1600),fill='#dfb4b4',width=2)
    d.text((205,190),'Science Assignment',fill='#27374a'); d.text((205,287),'1. Water changes from liquid to gas by evaporation.',fill='#27374a'); d.text((205,383),'2. Plants use sunlight to make food.',fill='#27374a')
    project={'pages':[{'original':im,'preview':None,'dpi':300,'source':'synthetic-sample','regions':[{'text':'Science Assignment','bbox':[195,175,550,40],'baseline':215,'confidence':1.0,'protected':False,'locked':False,'status':'review'},{'text':'1. Water changes from liquid to gas by evaporation.','bbox':[195,270,980,40],'baseline':310,'confidence':1.0,'protected':False,'locked':False,'status':'review'},{'text':'2. Plants use sunlight to make food.','bbox':[195,365,800,40],'baseline':405,'confidence':1.0,'protected':False,'locked':False,'status':'review'}]}],'profile':{'name':'Sample profile','samples':[],'font_path':'','renderer':'font_variation_fallback'},'settings':{'variation':True,'ink_color':'#172a42'}}
    page=project['pages'][0]; clean,_=restore_regions(page['original'],page['regions']); page['preview'],_=render_page(clean,page['regions'],project['profile'],project['settings'])
    save_project(out,project); print(f'Created {out.resolve()}')

if __name__=='__main__':main()
