from __future__ import annotations
import sys, logging
from pathlib import Path
from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QThread, Signal, QSignalBlocker, QTimer
from PySide6.QtGui import QAction, QPixmap, QImage, QDesktopServices, QKeySequence
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QListWidget,QLabel,QPushButton,QFileDialog,QMessageBox,QTableWidget,QTableWidgetItem,QTextEdit,QLineEdit,QFormLayout,QSpinBox,QCheckBox,QComboBox,QProgressBar,QGraphicsScene,QToolBar,QStatusBar,QDialog,QTabWidget,QScrollArea,QDialogButtonBox,QGroupBox,QGridLayout)
from document.io import load_pages
from layout.ocr import recognize
from image_processing.restore import restore_regions
from rendering.page import render_page
from project.store import save_project, load_project
from handwriting.profile import analyze, save_profile, load_profile
from handwriting.sheet import create_character_sheet, extract_glyphs
from handwriting.font_builder import build_font
from export.pdf import export_pdf
from quality.checks import validate_page
from ui.page_canvas import PageCanvas

logging.basicConfig(filename='studio.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

class Work(QThread):
    done=Signal(object); failed=Signal(str)
    def __init__(self, fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))

def pixmap(im: Image.Image, maxw=1000,maxh=850):
    im=im.convert('RGB'); data=im.tobytes(); q=QImage(data,im.width,im.height,im.width*3,QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(q).scaled(maxw,maxh,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)

class GlyphReviewDialog(QDialog):
    """Visual pass over the captured glyph cells before a font is compiled."""
    def __init__(self,glyphs,missing,parent=None):
        super().__init__(parent); self.setWindowTitle('Review handwriting samples'); self.resize(900,650)
        layout=QVBoxLayout(self); layout.addWidget(QLabel('Check the extracted characters. If one is wrong, correct the sheet and upload it again.'))
        if missing: layout.addWidget(QLabel('Blank or unreadable cells: '+', '.join(repr(ch) for ch in missing)))
        scroll=QScrollArea(); scroll.setWidgetResizable(True); inner=QWidget(); grid=QGridLayout(inner); grid.setSpacing(8)
        for i,(char,sample) in enumerate(glyphs.items()):
            card=QWidget(); card_layout=QVBoxLayout(card); card_layout.setContentsMargins(3,3,3,3)
            label=QLabel('SPACE' if char==' ' else repr(char)[1:-1]); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mask=sample['mask']; preview=Image.new('L',(64,64),255)
            if mask.size:
                glyph=Image.fromarray(255-mask).convert('L'); glyph.thumbnail((48,48)); preview.paste(glyph,((64-glyph.width)//2,(64-glyph.height)//2))
            image=QLabel(); image.setAlignment(Qt.AlignmentFlag.AlignCenter); image.setPixmap(pixmap(preview,64,64));
            card_layout.addWidget(label); card_layout.addWidget(image); card.setStyleSheet('QWidget{background:#f6f8fb;color:#1c2734;border:1px solid #d5dce4;border-radius:4px}')
            grid.addWidget(card,i//10,i%10)
        scroll.setWidget(inner); layout.addWidget(scroll)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok); buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Looks good'); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

class Studio(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Handwriting Replication Studio'); self.resize(1480,940)
        self.project={'pages':[],'profile':{'name':'Default','font_path':'','renderer':'font_variation_fallback'},'settings':{'variation':True,'ink_color':'#172a42'}}
        self.path=None; self.page_index=0; self.history=[]; self.future=[]; self.dirty=False
        self._text_edit_active=False
        self._ui(); self._style(); self._text_snapshot_timer=QTimer(self); self._text_snapshot_timer.setSingleShot(True); self._text_snapshot_timer.setInterval(700); self._text_snapshot_timer.timeout.connect(lambda:setattr(self,'_text_edit_active',False)); self._refresh()
    def _ui(self):
        file_menu=self.menuBar().addMenu('File'); edit_menu=self.menuBar().addMenu('Edit'); profile_menu=self.menuBar().addMenu('Handwriting'); help_menu=self.menuBar().addMenu('Help')
        actions={}
        entries=[('import','Open assignment…',self.import_file),('open','Open project…',self.open_project),('sample','Try sample project',self.open_sample),('save','Save',self.save),('save_as','Save project as…',self.save_as),('pdf','Export PDF…',self.export),('png','Export page images…',self.export_pngs),('exit','Exit',self.close),('undo','Undo',self.undo),('redo','Redo',self.redo),('profile','Create handwriting profile…',self.create_profile_dialog),('load_profile','Load handwriting profile…',self.load_handwriting_profile),('quick','Quick start',self.show_quick_start)]
        for key,label,fn in entries:
            action=QAction(label,self); action.triggered.connect(fn); actions[key]=action
        actions['save'].setShortcut(QKeySequence.StandardKey.Save); actions['undo'].setShortcut(QKeySequence.StandardKey.Undo); actions['redo'].setShortcut(QKeySequence.StandardKey.Redo)
        for key in ('import','open','sample','save','save_as','pdf','png'): file_menu.addAction(actions[key])
        file_menu.addSeparator(); file_menu.addAction(actions['exit']); edit_menu.addActions([actions['undo'],actions['redo']]); profile_menu.addActions([actions['profile'],actions['load_profile']]); help_menu.addAction(actions['quick'])
        bar=QToolBar('Main'); bar.setMovable(False); self.addToolBar(bar)
        for key in ('import','profile','save','pdf'): bar.addAction(actions[key])

        root=QWidget(); self.setCentralWidget(root); main=QVBoxLayout(root); split=QSplitter(Qt.Orientation.Horizontal); main.addWidget(split)
        left=QWidget(); ll=QVBoxLayout(left); ll.addWidget(QLabel('PAGES')); self.pages=QListWidget(); self.pages.currentRowChanged.connect(self.select_page); ll.addWidget(self.pages,1)
        card=QGroupBox('Handwriting profile'); card_layout=QVBoxLayout(card); self.profile_label=QLabel('No personal font yet'); self.profile_label.setWordWrap(True); card_layout.addWidget(self.profile_label); profile_button=QPushButton('Create profile'); profile_button.clicked.connect(self.create_profile_dialog); card_layout.addWidget(profile_button); ll.addWidget(card); split.addWidget(left)

        center=QWidget(); cl=QVBoxLayout(center); tools=QHBoxLayout(); self.compare=QComboBox(); self.compare.addItems(['Reconstructed','Original','Overlay','Difference']); self.compare.currentIndexChanged.connect(self._refresh); tools.addWidget(QLabel('View')); tools.addWidget(self.compare); self.ocr_btn=QPushButton('Detect text'); self.ocr_btn.clicked.connect(self.ocr); tools.addWidget(self.ocr_btn); self.build_btn=QPushButton('Rebuild page'); self.build_btn.clicked.connect(self.reconstruct); tools.addWidget(self.build_btn); self.build_all_btn=QPushButton('Rebuild all pages'); self.build_all_btn.clicked.connect(self.reconstruct_all); tools.addWidget(self.build_all_btn); self.compare_button=QPushButton('Compare side by side'); self.compare_button.clicked.connect(self.compare_side_by_side); tools.addWidget(self.compare_button); cl.addLayout(tools)
        self.welcome=QWidget(); welcome_layout=QVBoxLayout(self.welcome); welcome_layout.addStretch(1); title=QLabel('<h2>Start a handwriting project</h2><p>Open your assignment, create a handwriting profile, then review the text regions before rebuilding.</p>'); title.setWordWrap(True); welcome_layout.addWidget(title,0,Qt.AlignmentFlag.AlignCenter); welcome_buttons=QHBoxLayout(); open_button=QPushButton('Open assignment'); open_button.clicked.connect(self.import_file); sample_button=QPushButton('Try sample project'); sample_button.clicked.connect(self.open_sample); welcome_buttons.addWidget(open_button); welcome_buttons.addWidget(sample_button); welcome_layout.addLayout(welcome_buttons); welcome_layout.addStretch(1); cl.addWidget(self.welcome)
        self.scene=QGraphicsScene(); self.canvas=PageCanvas(self.scene); self.canvas.region_selected.connect(self.canvas_select_region); self.canvas.region_created.connect(self.add_manual_region); self.canvas.region_geometry_changed.connect(self.canvas_geometry_changed); self.canvas.draw_mode_changed.connect(self.draw_mode_changed); cl.addWidget(self.canvas,1); self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); cl.addWidget(self.progress); split.addWidget(center)

        self.right_tabs=QTabWidget(); split.addWidget(self.right_tabs)
        edit=QWidget(); edit_layout=QVBoxLayout(edit); edit_layout.addWidget(QLabel('Text regions')); self.regions=QTableWidget(0,4); self.regions.setHorizontalHeaderLabels(['Text','OCR','Keep','Lock']); self.regions.horizontalHeader().setStretchLastSection(True); self.regions.itemSelectionChanged.connect(self.edit_region); edit_layout.addWidget(self.regions,2)
        region_actions=QHBoxLayout(); self.draw_button=QPushButton('Draw line box'); self.draw_button.setCheckable(True); self.draw_button.toggled.connect(self.canvas.set_draw_mode); self.split_region_button=QPushButton('Split selected'); self.split_region_button.clicked.connect(self.split_region); self.delete_region_button=QPushButton('Delete'); self.delete_region_button.clicked.connect(self.delete_region); region_actions.addWidget(self.draw_button); region_actions.addWidget(self.split_region_button); region_actions.addWidget(self.delete_region_button); edit_layout.addLayout(region_actions)
        edit_layout.addWidget(QLabel('Selected line')); self.text=QTextEdit(); self.text.textChanged.connect(self.text_changed); self.text.setPlaceholderText('Select a line box or draw one, then enter its text.'); edit_layout.addWidget(self.text,1)
        buttons=QHBoxLayout(); self.protect=QPushButton('Keep original'); self.protect.clicked.connect(self.toggle_protected); self.lock=QPushButton('Lock position'); self.lock.clicked.connect(self.toggle_lock); buttons.addWidget(self.protect); buttons.addWidget(self.lock); edit_layout.addLayout(buttons)
        geometry=QGroupBox('Exact position'); geometry.setCheckable(True); geometry.setChecked(False); geom_layout=QVBoxLayout(geometry); boxform=QFormLayout(); self.box_inputs=[]
        for label in ('X','Y','Width','Height','Baseline'):
            sb=QSpinBox(); sb.setRange(0,50000); self.box_inputs.append(sb); boxform.addRow(label,sb)
        geom_layout.addLayout(boxform); apply_box=QPushButton('Apply position'); apply_box.clicked.connect(self.apply_geometry); geom_layout.addWidget(apply_box); geometry.toggled.connect(lambda shown:[w.setVisible(shown) for w in geometry.findChildren(QWidget)]); [w.hide() for w in geometry.findChildren(QWidget)]; edit_layout.addWidget(geometry); self.right_tabs.addTab(edit,'Edit text')

        style=QWidget(); style_layout=QVBoxLayout(style); style_layout.addWidget(QLabel('Handwriting and ink'))
        self.font=QLineEdit(); self.font.setPlaceholderText('Personal font appears here after profile creation'); fb=QPushButton('Choose font…'); fb.clicked.connect(self.choose_font); fontrow=QHBoxLayout(); fontrow.addWidget(self.font); fontrow.addWidget(fb); style_layout.addLayout(fontrow)
        self.variation=QCheckBox('Small baseline variation'); self.variation.setChecked(True); style_layout.addWidget(self.variation); style_layout.addWidget(QLabel('Ink color')); self.ink=QComboBox(); self.ink.addItems(['Blue ink','#172a42','Black ink','#171717','Blue-black','#263b52']); style_layout.addWidget(self.ink); style_layout.addStretch(1); self.right_tabs.addTab(style,'Appearance')
        self.variation.toggled.connect(self.settings_changed); self.ink.currentTextChanged.connect(self.settings_changed); self.font.textChanged.connect(self.settings_changed)
        self.message=QLabel('Open an assignment to begin, or try the included sample project.'); self.message.setWordWrap(True); main.addWidget(self.message); split.setSizes([180,900,370]); self.setStatusBar(QStatusBar())
    def _style(self): self.setStyleSheet('QMainWindow{background:#10141b;color:#e5eaf1} QWidget{color:#e5eaf1;background:#10141b} QToolBar{background:#171e28;border:0;spacing:6px} QMenuBar,QMenu{background:#171e28;color:#e5eaf1} QMenu::item:selected{background:#315b78} QTabWidget::pane{background:#151b24;border:1px solid #293647} QTabBar::tab{background:#202b39;color:#dce5ef;padding:8px 14px;border:1px solid #293647} QTabBar::tab:selected{background:#315b78} QPushButton{padding:8px;background:#253449;border:1px solid #35475d;border-radius:5px} QPushButton:hover{background:#315b78} QTableWidget,QTextEdit,QLineEdit,QListWidget,QGraphicsView,QComboBox{background:#151b24;border:1px solid #293647;color:#e5eaf1} QHeaderView::section{background:#202b39;color:#e5eaf1;padding:5px} QGroupBox{border:1px solid #293647;border-radius:5px;margin-top:8px;padding:8px} QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 4px} QProgressBar{height:7px}')
    def warn(self,e): QMessageBox.warning(self,'Handwriting Replication Studio',str(e)); logging.exception(str(e))
    def _mark_dirty(self, stale_preview=False, all_pages=False):
        self.dirty=True
        if stale_preview:
            pages=self.project.get('pages',[]) if all_pages else ([self.current()] if self.current() else [])
            for page in pages: page['preview_stale']=True
        self.setWindowTitle('Handwriting Replication Studio *')

    def _mark_clean(self):
        self.dirty=False
        self.setWindowTitle('Handwriting Replication Studio')

    def _sync_settings(self):
        color=self.ink.currentText()
        self.project.setdefault('settings',{}).update({
            'font_path':self.font.text(),
            'variation':self.variation.isChecked(),
            'ink_color':color if color.startswith('#') else ('#1d4d78' if 'Blue' in color else '#171717'),
        })

    def settings_changed(self,*_):
        self._sync_settings()
        self._mark_dirty(stale_preview=True,all_pages=True)

    def _confirm_unsaved(self):
        if not self.dirty: return True
        if not self.project.get('pages'):
            self._mark_clean(); return True
        answer=QMessageBox.warning(self,'Unsaved project','Save your changes before continuing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        if answer==QMessageBox.StandardButton.Cancel: return False
        if answer==QMessageBox.StandardButton.Discard: return True
        self.save()
        return not self.dirty

    def import_file(self):
        if not self._confirm_unsaved(): return
        f,_=QFileDialog.getOpenFileName(self,'Import assignment','','Documents and images (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)')
        if not f:return
        try:
            profile=self.project['profile']; settings=self.project['settings']
            self.project={'pages':[{'original':im,'preview':None,'regions':[],'dpi':300,'source':Path(f).name,'preview_stale':True} for im in load_pages(f)],'profile':profile,'settings':settings}
            self.path=None; self.history=[]; self.future=[]; self.pages.clear()
            for i,p in enumerate(self.project['pages']): self.pages.addItem(f'Page {i+1}  ·  {p["original"].width} × {p["original"].height}')
            self.pages.setCurrentRow(0); self._mark_dirty(); self.message.setText('Pages imported. Detect text or draw a line box, then review before rebuilding.'); self._refresh()
        except Exception as e:self.warn(e)

    def current(self): return self.project['pages'][self.page_index] if 0<=self.page_index<len(self.project['pages']) else None
    def select_page(self,i): self.page_index=i; self._refresh()

    def _refresh(self,*_):
        self.scene.clear(); p=self.current()
        if not p:
            self.welcome.show(); self.canvas.hide(); self.ocr_btn.setEnabled(False); self.build_btn.setEnabled(False); self.build_all_btn.setEnabled(False); self.compare_button.setEnabled(False)
            self.regions.blockSignals(True); self.regions.setRowCount(0); self.regions.blockSignals(False)
            return
        self.welcome.hide(); self.canvas.show(); self.ocr_btn.setEnabled(True); self.build_btn.setEnabled(True); self.build_all_btn.setEnabled(True); self.compare_button.setEnabled(True)
        im=p.get('preview') or p['original']; mode=self.compare.currentIndex()
        if mode==1: im=p['original']
        elif mode==2 and p.get('preview'):
            im=Image.blend(p['original'].convert('RGB'),p['preview'].convert('RGB'),.5)
        elif mode==3 and p.get('preview'):
            from PIL import ImageChops,ImageEnhance
            im=ImageEnhance.Contrast(ImageChops.difference(p['original'].convert('RGB'),p['preview'].convert('RGB'))).enhance(4)
        pm=pixmap(im); self.scene.addPixmap(pm); display_size=(pm.width(),pm.height()); self.canvas.set_page_geometry(display_size,p['original'].size,p.get('regions',[]),self.regions.currentRow()); self.canvas.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
        selected=self.regions.currentRow()
        self.regions.blockSignals(True); self.regions.setRowCount(len(p.get('regions',[])))
        for i,r in enumerate(p.get('regions',[])):
            vals=[r.get('text',''),f'{r.get("confidence",0):.0%}', 'Yes' if r.get('protected') else 'No','Yes' if r.get('locked') else 'No']
            for j,v in enumerate(vals):
                item=QTableWidgetItem(str(v)); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); self.regions.setItem(i,j,item)
        if 0<=selected<len(p.get('regions',[])): self.regions.setCurrentCell(selected,0)
        self.regions.blockSignals(False)
        self.canvas.set_page_geometry(display_size,p['original'].size,p.get('regions',[]),self.regions.currentRow())
        profile=self.project.get('profile',{}); count=profile.get('glyph_count',0)
        self.profile_label.setText(f'{profile.get("name","No personal font yet")} · {count} characters' if count else 'No personal font yet')
        blockers=[QSignalBlocker(self.font),QSignalBlocker(self.variation),QSignalBlocker(self.ink)]
        self.font.setText(profile.get('font_path','') or self.project.get('settings',{}).get('font_path',''))
        self.variation.setChecked(self.project.get('settings',{}).get('variation',True))
        saved_color=self.project.get('settings',{}).get('ink_color','#172a42')
        color_index=self.ink.findText(saved_color)
        if color_index>=0: self.ink.setCurrentIndex(color_index)
        del blockers
        if 0<=self.regions.currentRow()<len(p.get('regions',[])): self.edit_region()
        if p.get('preview_stale'): self.statusBar().showMessage('Edits changed since the last rebuild',5000)

    def open_sample(self):
        if not self._confirm_unsaved(): return
        self._load_project_folder(Path(__file__).resolve().parent/'sample_project')

    def _load_project_folder(self,folder):
        self.project=load_project(folder); self.path=None if Path(folder).resolve()==(Path(__file__).resolve().parent/'sample_project').resolve() else str(folder); self.history=[]; self.future=[]; self.pages.clear(); self.page_index=0
        for i,p in enumerate(self.project['pages']): self.pages.addItem(f'Page {i+1}  ·  {p["original"].width} × {p["original"].height}')
        self._mark_clean(); self.pages.setCurrentRow(0); self._refresh()

    def show_quick_start(self):
        dialog=QDialog(self); dialog.setWindowTitle('Quick start'); dialog.resize(520,300); layout=QVBoxLayout(dialog)
        intro=QLabel('<h2>Quick start</h2><p>1. Open an assignment or try the sample.<br>2. Detect text or draw boxes around lines.<br>3. Review the text and protect anything you want to keep.<br>4. Choose a handwriting profile, rebuild, compare, then export.</p>')
        intro.setWordWrap(True); layout.addWidget(intro)
        sample=QPushButton('Open sample project'); sample.clicked.connect(lambda checked=False:(dialog.accept(),self.open_sample()))
        own=QPushButton('Open my assignment'); own.clicked.connect(lambda checked=False:(dialog.accept(),self.import_file()))
        close=QPushButton('Close'); close.clicked.connect(dialog.reject); layout.addWidget(sample); layout.addWidget(own); layout.addWidget(close); dialog.exec()
    def ocr(self):
        p=self.current()
        if not p:return
        self._set_busy(True); self.worker=Work(lambda: recognize(p['original'])); self.worker.done.connect(lambda rows:self.ocr_done(p,rows)); self.worker.failed.connect(self.worker_error); self.worker.finished.connect(lambda:self._set_busy(False)); self.worker.start()
    def ocr_done(self,p,rows):
        self._snapshot(); p['regions']=rows; self._mark_dirty(stale_preview=True); self._refresh()
        self.message.setText(f'OCR proposed {len(rows)} line regions. Confidence is advisory; review every line and use Protected for equations/diagrams. Empty results? Install Tesseract OCR and add it to PATH.')
    def worker_error(self,e):self.warn(e)
    def _set_busy(self,busy):
        for widget in (self.pages,self.canvas,self.regions,self.text,self.right_tabs,self.draw_button,self.split_region_button,self.delete_region_button,self.protect,self.lock):
            widget.setEnabled(not busy)
        self.menuBar().setEnabled(not busy)
        for widget in (self.ocr_btn,self.build_btn,self.build_all_btn): widget.setEnabled(not busy and bool(self.project.get('pages')))
        if busy:self.progress.show()
        else:self.progress.hide()
    def edit_region(self):
        p=self.current(); row=self.regions.currentRow()
        if not p or row<0 or row>=len(p.get('regions',[])):return
        self.canvas.selected_index=row; self.canvas.viewport().update()
        self.text.blockSignals(True); self.text.setPlainText(p['regions'][row].get('text','')); self.text.blockSignals(False)
        self._text_edit_active=False
        self.protect.setText('Replace this line' if p['regions'][row].get('protected') else 'Keep original')
        self.lock.setText('Unlock position' if p['regions'][row].get('locked') else 'Lock position')
        x,y,w,h=p['regions'][row]['bbox']
        for inp,val in zip(self.box_inputs,(x,y,w,h,p['regions'][row].get('baseline',y+h))): inp.setValue(int(val))

    def canvas_select_region(self,index):
        if index>=0:
            self.regions.setCurrentCell(index,0); self.right_tabs.setCurrentIndex(0)
        else:
            self.regions.clearSelection(); self.canvas.selected_index=-1; self.canvas.viewport().update()

    def draw_mode_changed(self,enabled):
        self.draw_button.blockSignals(True); self.draw_button.setChecked(enabled); self.draw_button.blockSignals(False)
        self.draw_button.setText('Cancel drawing' if enabled else 'Draw line box')

    def add_manual_region(self,bbox):
        p=self.current()
        if not p:return
        self._snapshot(); x,y,w,h=bbox
        p.setdefault('regions',[]).append({'text':'','bbox':bbox,'baseline':y+h,'confidence':0.0,'protected':False,'locked':False,'status':'manual'})
        self._mark_dirty(stale_preview=True); self._refresh(); row=len(p['regions'])-1; self.regions.setCurrentCell(row,0); self.text.setFocus(); self.message.setText('Line box added. Type its transcription in the selected-line field.')

    def canvas_geometry_changed(self,index,bbox):
        p=self.current()
        if not p or not 0<=index<len(p.get('regions',[])):return
        region=p['regions'][index]
        if region.get('locked'):return
        self._snapshot(); region['bbox']=bbox; region['baseline']=bbox[1]+bbox[3]; region['status']='edited'
        self._mark_dirty(stale_preview=True); self._refresh(); self.regions.setCurrentCell(index,0)
        self.message.setText('Line box adjusted. Use Undo to restore the previous position.')

    def delete_region(self):
        p=self.current(); index=self.regions.currentRow()
        if not p or not 0<=index<len(p.get('regions',[])):return
        self._snapshot(); p['regions'].pop(index); self._mark_dirty(stale_preview=True); self._refresh()
        if p.get('regions'): self.regions.setCurrentCell(min(index,len(p['regions'])-1),0)

    def split_region(self):
        p=self.current(); index=self.regions.currentRow()
        if not p or not 0<=index<len(p.get('regions',[])):return
        region=p['regions'][index]; x,y,w,h=map(int,region['bbox'])
        if w<30:
            self.message.setText('This box is too narrow to split. Widen it first.'); return
        text=region.get('text',''); words=text.split()
        midpoint=max(1,len(words)//2)
        left_text=' '.join(words[:midpoint]) if len(words)>1 else text
        right_text=' '.join(words[midpoint:]) if len(words)>1 else ''
        cut=w//2; self._snapshot()
        first=dict(region); first.update({'text':left_text,'bbox':[x,y,cut,h],'baseline':region.get('baseline',y+h),'locked':False,'status':'manual'})
        second=dict(region); second.update({'text':right_text,'bbox':[x+cut,y,w-cut,h],'baseline':region.get('baseline',y+h),'locked':False,'status':'manual'})
        p['regions'][index:index+1]=[first,second]; self._mark_dirty(stale_preview=True); self._refresh(); self.regions.setCurrentCell(index+1,0)
        self.message.setText('Region split side by side. Check the text in both halves and adjust their boxes on the page.')

    def text_changed(self):
        p=self.current(); row=self.regions.currentRow()
        if p and 0<=row<len(p.get('regions',[])):
            if not self._text_edit_active:
                self._snapshot(); self._text_edit_active=True
            self._text_snapshot_timer.start(); p['regions'][row]['text']=self.text.toPlainText().replace('\n',' '); p['regions'][row]['status']='edited'; self._mark_dirty(stale_preview=True)
            self.regions.item(row,0).setText(p['regions'][row]['text']); self.canvas.viewport().update()
    def _snapshot(self):
        import copy
        state={'pages':[{'regions':copy.deepcopy(p.get('regions',[])),'preview':p.get('preview'),'preview_stale':p.get('preview_stale',False),'render_warnings':copy.deepcopy(p.get('render_warnings',[]))} for p in self.project.get('pages',[])], 'profile':copy.deepcopy(self.project.get('profile',{})), 'settings':copy.deepcopy(self.project.get('settings',{}))}
        self.history.append(state); self.history=self.history[-40:]; self.future.clear()
    def _apply_state(self,state):
        import copy
        for page,saved in zip(self.project.get('pages',[]),state.get('pages',[])):
            page['regions']=copy.deepcopy(saved['regions']); page['preview']=saved['preview']; page['preview_stale']=saved.get('preview_stale',False); page['render_warnings']=copy.deepcopy(saved.get('render_warnings',[]))
        self.project['profile']=copy.deepcopy(state.get('profile',{})); self.project['settings']=copy.deepcopy(state.get('settings',{}))
    def undo(self):
        if self.history:
            self.future.append(self._capture_state()); self._apply_state(self.history.pop()); self._mark_dirty(); self._refresh()
    def redo(self):
        if self.future:
            self.history.append(self._capture_state()); self._apply_state(self.future.pop()); self._mark_dirty(); self._refresh()
    def _capture_state(self):
        import copy
        return {'pages':[{'regions':copy.deepcopy(p.get('regions',[])),'preview':p.get('preview'),'preview_stale':p.get('preview_stale',False),'render_warnings':copy.deepcopy(p.get('render_warnings',[]))} for p in self.project.get('pages',[])], 'profile':copy.deepcopy(self.project.get('profile',{})), 'settings':copy.deepcopy(self.project.get('settings',{}))}
    def toggle_protected(self):
        p=self.current(); row=self.regions.currentRow()
        if p and 0<=row<len(p['regions']):self._snapshot(); p['regions'][row]['protected']=not p['regions'][row].get('protected',False); self._mark_dirty(stale_preview=True); self._refresh()
    def apply_geometry(self):
        p=self.current(); row=self.regions.currentRow()
        if not p or not 0<=row<len(p.get('regions',[])): return
        r=p['regions'][row]
        if r.get('locked'):
            self.message.setText('This region is position-locked. Toggle the Lock cell in its row before moving it.'); return
        self._snapshot(); x,y,w,h,baseline=[s.value() for s in self.box_inputs]; r['bbox']=[x,y,w,h]; r['baseline']=baseline; r['status']='edited'; self._mark_dirty(stale_preview=True); self.message.setText('Region geometry updated.'); self._refresh()
    def toggle_lock(self):
        p=self.current(); row=self.regions.currentRow()
        if p and 0<=row<len(p.get('regions',[])):
            self._snapshot(); p['regions'][row]['locked']=not p['regions'][row].get('locked',False); self._mark_dirty(); self._refresh()
    def reconstruct(self):
        p=self.current()
        if not p:return
        self._snapshot(); self._sync_settings(); p['preview_stale']=True; self._mark_dirty(); profile=self.project['profile']; settings=self.project['settings']
        self._set_busy(True)
        self.worker=Work(lambda: self._render_task(p,profile,dict(settings))); self.worker.done.connect(lambda result:self._render_done(p,result)); self.worker.failed.connect(self.worker_error); self.worker.finished.connect(lambda:self._set_busy(False)); self.worker.start()

    def reconstruct_all(self):
        if not self.project.get('pages'):return
        self._snapshot(); self._sync_settings(); pages=list(self.project['pages']); profile=dict(self.project['profile']); settings=dict(self.project['settings'])
        for page in pages: page['preview_stale']=True
        self._mark_dirty()
        self._set_busy(True)
        def build_pages():
            return [(page,self._render_task(page,profile,settings)) for page in pages]
        self.worker=Work(build_pages); self.worker.done.connect(self._render_all_done); self.worker.failed.connect(self.worker_error); self.worker.finished.connect(lambda:self._set_busy(False)); self.worker.start()
    @staticmethod
    def _render_task(page,profile,settings):
        regions=[dict(r) for r in page['regions']]; unsupported=[]; supported=set(profile.get('characters',[]))
        for i,r in enumerate(regions):
            if not r.get('text','').strip():
                r['protected']=True
                continue
            if supported:
                missing={ch for ch in r.get('text','') if not ch.isspace() and ch not in supported}
                if missing:
                    r['protected']=True; unsupported.append(i)
        clean,failed=restore_regions(page['original'],regions); out,overflow=render_page(clean,regions,profile,settings); return out,failed,overflow+unsupported
    def _render_done(self,page,result):
        warnings=self._store_render_result(page,result)
        self.compare.setCurrentIndex(0); self._mark_dirty(); self._refresh()
        self.message.setText('Reconstruction ready. '+(f'Review regions {sorted(warnings)}; export checks will list each issue.' if warnings else 'Compare against the original, then save or export.'))

    def _render_all_done(self,results):
        flagged=[]
        for page_number,(page,result) in enumerate(results,1):
            flagged.extend((page_number,index+1) for index in self._store_render_result(page,result))
        self.compare.setCurrentIndex(0); self._mark_dirty(); self._refresh()
        self.message.setText(f'Rebuilt {len(results)} pages. '+(f'Review page/region pairs {flagged}; export checks will list each issue.' if flagged else 'Compare the pages, then save or export.'))

    def _store_render_result(self,page,result):
        out,failed,content_issues=result; page['preview']=out; page['preview_stale']=False
        warnings={}
        for index in failed: warnings[index]='Original text could not be fully removed.'
        for index in content_issues:
            previous=warnings.get(index)
            detail='Text does not fit the box or the handwriting font lacks a character.'
            warnings[index]=f'{previous} {detail}' if previous else detail
        page['render_warnings']=[{'region':index,'message':message} for index,message in sorted(warnings.items())]
        return set(warnings)
    def create_profile_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle('Create handwriting profile'); dialog.resize(560,420); layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('<h2>Create your handwriting font</h2><p>Print the app’s character sheet, fill one character per box, then upload the completed PDF or its JPG photos. Ordinary notebook pages cannot be reliably split into individual letters automatically.</p>'))
        name=QLineEdit('My Handwriting'); form=QFormLayout(); form.addRow('Font name',name); layout.addLayout(form)
        template_status=QLabel('Step 1 · Create and print the blank character sheet.'); template_status.setWordWrap(True); layout.addWidget(template_status)
        template_button=QPushButton('Create character sheet PDF…'); layout.addWidget(template_button)
        import_status=QLabel('Step 2 · After filling it in, upload the completed sheet. Use a dark pen and include all four corner markers.'); import_status.setWordWrap(True); layout.addWidget(import_status)
        upload_button=QPushButton('Upload completed PDF / JPG…'); layout.addWidget(upload_button)
        self._pending_glyphs=None; self._pending_details=None; self._pending_paths=[]
        build_button=QPushButton('Review characters and save TTF…'); build_button.setEnabled(False); layout.addWidget(build_button)
        close_button=QPushButton('Close'); close_button.clicked.connect(dialog.reject); layout.addWidget(close_button)
        def make_sheet():
            path,_=QFileDialog.getSaveFileName(dialog,'Save blank character sheet','handwriting-character-sheet.pdf','PDF (*.pdf)')
            if not path:return
            try:
                create_character_sheet(path); template_status.setText(f'Sheet saved: {path}\nPrint all pages, fill in the characters, then scan to PDF or photograph both pages.')
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except Exception as e:self.warn(e)
        def import_sheets():
            paths,_=QFileDialog.getOpenFileNames(dialog,'Select completed character sheets','','PDF or images (*.pdf *.jpg *.jpeg *.png)')
            if not paths:return
            paths=sorted(paths,key=lambda p:Path(p).name.casefold()) if all(Path(p).suffix.lower()!='.pdf' for p in paths) else paths
            try:
                glyphs,details=extract_glyphs(paths)
                review=GlyphReviewDialog(glyphs,details['missing_characters'],dialog)
                if review.exec()!=QDialog.DialogCode.Accepted:return
                self._pending_glyphs=glyphs; self._pending_details=details; self._pending_paths=paths
                missing=len(details['missing_characters']); import_status.setText(f'Found {details["glyph_count"]} character samples. '+(f'{missing} cells were blank or unreadable.' if missing else 'All template cells were read.'))
                build_button.setEnabled(True)
            except Exception as e:self.warn(e)
        def build_profile():
            if not self._pending_glyphs:return
            path,_=QFileDialog.getSaveFileName(dialog,'Save personal handwriting font','my-handwriting.ttf','Font file (*.ttf *.otf)')
            if not path:return
            if Path(path).suffix.lower() not in ('.ttf','.otf'):path += '.ttf'
            try:
                info=build_font(self._pending_glyphs,path,name.text().strip() or 'My Handwriting')
                details=self._pending_details or {}
                profile={'name':name.text().strip() or 'My Handwriting','renderer':'user_glyph_font','font_path':info['font_path'],'font_format':info['font_format'],'source_sheets':details.get('source_sheet',self._pending_paths),'glyph_count':info['glyph_count'],'characters':list(self._pending_glyphs.keys())+[' '],'missing_characters':details.get('missing_characters',[]),'metrics':{'median_glyph_height_px':details.get('median_glyph_height',0),'median_glyph_width_px':details.get('median_glyph_width',0),'mean_ink_gray':details.get('ink_gray_mean')}}
                profile_path=str(Path(path).with_suffix('.profile.json')); save_profile(profile,profile_path)
                self.project['profile']=profile; self.font.setText(str(Path(path).resolve())); self.profile_label.setText(f'{profile["name"]} · {profile["glyph_count"]} characters'); self._mark_dirty(stale_preview=True,all_pages=True)
                self.message.setText(f'Handwriting font and profile saved:\n{path}\n{profile_path}')
                QMessageBox.information(dialog,'Profile ready',f'Created a {info["font_format"]} font from {profile["glyph_count"]} character samples.\n\nThe font is selected for page reconstruction. This is a static font: handwritten connections between letters may not match pen-written cursive.')
                dialog.accept()
            except Exception as e:self.warn(e)
        template_button.clicked.connect(make_sheet); upload_button.clicked.connect(import_sheets); build_button.clicked.connect(build_profile)
        dialog.exec()
    def choose_font(self):
        f,_=QFileDialog.getOpenFileName(self,'Choose handwriting font','','Fonts (*.ttf *.otf)')
        if f:
            self.font.setText(f)
            current=self.project.get('profile',{}).get('font_path','')
            if not current or Path(current).resolve()!=Path(f).resolve(): self.project['profile']={'name':Path(f).stem,'renderer':'external_font','font_path':f,'glyph_count':0}
            self._mark_dirty(stale_preview=True,all_pages=True)
    def load_handwriting_profile(self):
        f,_=QFileDialog.getOpenFileName(self,'Load handwriting profile','','Profile (*.json)')
        if f:
            try:
                self.project['profile']=load_profile(f); self.font.setText(self.project['profile'].get('font_path','')); self.profile_label.setText(f'{self.project["profile"].get("name","Handwriting profile")} · {self.project["profile"].get("glyph_count",0)} characters'); self._mark_dirty(stale_preview=True,all_pages=True)
            except Exception as e:self.warn(e)

    def _save_to(self,path):
        if not self.project['pages']:return False
        try:
            self._sync_settings(); save_project(path,self.project); self.path=str(path)
            saved_font=self.project.get('profile',{}).get('font_path','')
            blocker=QSignalBlocker(self.font); self.font.setText(saved_font); del blocker
            self.project.setdefault('settings',{})['font_path']=saved_font
            self._mark_clean(); self.statusBar().showMessage('Project saved. Open this folder’s project.json to resume.',5000); return True
        except Exception as e:self.warn(e); return False

    def save(self):
        if not self.project['pages']:return False
        if self.path:return self._save_to(self.path)
        return self.save_as()

    def save_as(self):
        if not self.project['pages']:return False
        path=QFileDialog.getExistingDirectory(self,'Choose project folder',str(self.path or Path.cwd()))
        return self._save_to(path) if path else False

    def open_project(self):
        if not self._confirm_unsaved(): return
        path=QFileDialog.getOpenFileName(self,'Open project','','Project metadata (project.json)')[0]
        if not path:return
        try:
            self._load_project_folder(Path(path).parent)
        except Exception as e:self.warn(e)

    def compare_side_by_side(self):
        page=self.current()
        if not page:return
        dialog=QDialog(self); dialog.setWindowTitle('Compare original and reconstruction'); dialog.resize(1250,850); layout=QHBoxLayout(dialog)
        preview_title='Reconstructed page' if page.get('preview') and not page.get('preview_stale') else ('Last reconstruction (out of date)' if page.get('preview') else 'Not rebuilt yet (showing original)')
        for title,image in [('Original page',page['original']),(preview_title,page.get('preview') or page['original'])]:
            column=QVBoxLayout(); label=QLabel(title); label.setAlignment(Qt.AlignmentFlag.AlignCenter); view=QLabel(); view.setAlignment(Qt.AlignmentFlag.AlignCenter); view.setPixmap(pixmap(image,580,760)); view.setMinimumSize(400,400)
            scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(view); column.addWidget(label); column.addWidget(scroll); layout.addLayout(column)
        dialog.exec()

    def _confirm_export_warnings(self):
        issues=[f'Page {i+1}: {message}' for i,page in enumerate(self.project.get('pages',[])) for message in validate_page(page)]
        if not issues:return True
        box=QMessageBox(self); box.setIcon(QMessageBox.Icon.Warning); box.setWindowTitle('Review before export')
        box.setText(f'{len(issues)} item(s) may affect your export. Review the details before continuing.')
        box.setDetailedText('\n'.join(issues)); box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Yes).setText('Export anyway'); box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec()==QMessageBox.StandardButton.Yes

    def export(self):
        images=[p.get('preview') or p['original'] for p in self.project['pages']]
        if not images:return
        if not self._confirm_export_warnings():return
        f,_=QFileDialog.getSaveFileName(self,'Export PDF','reconstructed.pdf','PDF (*.pdf)')
        if f:
            try:export_pdf(images,f); self.statusBar().showMessage('PDF exported with per-page dimensions preserved',5000)
            except Exception as e:self.warn(e)
    def export_pngs(self):
        if not self.project['pages']:return
        if not self._confirm_export_warnings():return
        d=QFileDialog.getExistingDirectory(self,'Export pages as PNG')
        if d:
            for i,p in enumerate(self.project['pages']): (p.get('preview') or p['original']).save(Path(d)/f'page_{i+1:03}.png')
            self.statusBar().showMessage('PNG pages exported',4000)

    def closeEvent(self,event):
        if self._confirm_unsaved(): event.accept()
        else: event.ignore()

def main():
    app=QApplication(sys.argv); win=Studio(); win.show(); sys.exit(app.exec())
if __name__=='__main__':main()
