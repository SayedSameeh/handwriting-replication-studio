from __future__ import annotations
from pathlib import Path
from PIL import Image
import json, shutil

def save_project(path: str|Path, project: dict) -> None:
    path=Path(path); path.mkdir(parents=True,exist_ok=True); (path/'pages').mkdir(exist_ok=True)
    metadata={k:v for k,v in project.items() if k!='pages'}; pages=[]
    profile=metadata.get('profile',{})
    font_path=profile.get('font_path') if isinstance(profile,dict) else None
    if font_path and Path(font_path).is_file():
        font_dir=path/'fonts'; font_dir.mkdir(exist_ok=True); asset=font_dir/Path(font_path).name
        if Path(font_path).resolve()!=asset.resolve(): shutil.copy2(font_path,asset)
        profile['font_asset']=str(asset.relative_to(path).as_posix()); profile['font_path']=str(asset.resolve())
    for i,p in enumerate(project['pages']):
        original=f'pages/page_{i+1:03}_original.png'; p['original'].save(path/original)
        reconstructed=f'pages/page_{i+1:03}_preview.png'
        if p.get('preview') is not None: p['preview'].save(path/reconstructed)
        pages.append({k:v for k,v in p.items() if k not in ('original','preview')} | {'original_asset':original,'preview_asset':reconstructed if p.get('preview') is not None else None})
    metadata['pages']=pages; metadata['format']='handwriting-replication-studio'; metadata['version']=1
    (path/'project.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')

def load_project(path: str|Path) -> dict:
    path=Path(path); meta=json.loads((path/'project.json').read_text(encoding='utf-8'))
    profile=meta.get('profile',{})
    if isinstance(profile,dict) and profile.get('font_asset'):
        profile['font_path']=str((path/profile['font_asset']).resolve())
    pages=[]
    for p in meta.pop('pages'):
        q=dict(p); q['original']=Image.open(path/p.pop('original_asset')).convert('RGB'); preview=p.pop('preview_asset'); q['preview']=Image.open(path/preview).convert('RGB') if preview else None; q.update(p); pages.append(q)
    meta['pages']=pages; return meta
