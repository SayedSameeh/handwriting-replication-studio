# Handwriting Replication Studio

A local Windows desktop application for building a personal handwriting font from a guided character sheet, placing typed text into page regions, and exporting reconstructed assignments for review.

> **Important:** This is a page-editing and handwriting-style tool. It does not reproduce natural pen strokes or perfectly imitate connected cursive. OCR and page cleanup can be inaccurate, so review every page before exporting.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Install and run on Windows](#install-and-run-on-windows)
- [Quick start](#quick-start)
- [Create a handwriting profile](#create-a-handwriting-profile)
- [Edit pages](#edit-pages)
- [Save and export](#save-and-export)
- [OCR setup](#ocr-setup)
- [Restrictions and known limitations](#restrictions-and-known-limitations)
- [Troubleshooting](#troubleshooting)
- [Project files and privacy](#project-files-and-privacy)
- [License](#license)

## Features

- Import multi-page PDFs or image files (JPG/JPEG, PNG, BMP, TIFF, and WEBP).
- Render PDF pages locally at 300 DPI for editing.
- Optionally suggest text regions using Tesseract OCR; review or correct each suggestion.
- Draw, select, move, resize, split, delete, protect, lock, and precisely position line regions.
- Type or correct text in the selected region and render it using the selected handwriting font.
- Create a handwriting profile by extracting character samples from the app's printable, two-page A4 template. The app builds a TTF or OTF font and saves a JSON profile beside it.
- Review the extracted character samples before building the font; blank or unreadable cells are reported.
- Use an existing TTF/OTF font or load a saved handwriting profile.
- Choose ink color and enable small baseline variation.
- Rebuild one page or all pages.
- Compare the original and rebuilt page using reconstructed, original, overlay, difference, or side-by-side views.
- Run export checks for stale previews, missing text, low OCR confidence, overlapping or invalid regions, and rendering warnings. Review details and choose whether to export anyway.
- Export a multi-page PDF or PNG page images.
- Save a project and reopen it later, including page images, edits, previews, settings, and a copy of the selected font.
- Undo and redo editing changes during the current session; use Ctrl+S to save.
- Open the included sample project to explore the editor without importing a document.

## Requirements

- Windows 10 or 11
- Python 3.11 or 3.12
- Tesseract OCR is optional and must be installed separately to use text detection.

Python packages are listed in [`requirements.txt`](requirements.txt). The setup script creates a virtual environment and installs them.

## Install and run on Windows

1. Install Python 3.11 or 3.12 and make sure the Python launcher (`py`) is available.
2. From this folder, double-click `setup_windows.bat`. It creates `.venv` and installs the dependencies.
3. Double-click `run_studio.bat` to launch the app.

You can also run from PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

If Python 3.12 is unavailable, use `py -3.11` in the first command.

## Quick start

1. Launch the app and choose **Try sample project** to explore, or choose **Open assignment** / **File → Open assignment**.
2. To add text, select **Draw line box** and drag around the area where it should go. Select the box and enter the text in **Edit text → Selected line**. You can also use **Detect text** as a starting point, then inspect its proposed regions and text.
3. Create or load your handwriting profile. Select ink and other options in **Appearance**.
4. Choose **Rebuild page** or **Rebuild all pages**.
5. Review the result against the original. Fix text or boxes and rebuild as needed.
6. Save the project, then choose **File → Export PDF…** or **File → Export page images…**.

Use **Help → Quick start** inside the app for a short in-app guide.

## Create a handwriting profile

1. Choose **Handwriting → Create handwriting profile…** or click **Create profile** in the sidebar.
2. Click **Create character sheet PDF…**, save and print both A4 pages.
3. Fill in one character per box with dark ink. Keep all four corner markers visible and avoid writing outside the boxes.
4. Scan the completed pages to one PDF, or photograph both pages straight-on as JPG or PNG images.
5. Click **Upload completed PDF / JPG…**. Select the PDF, or select both page images. For images, filenames are sorted alphabetically, so name them in page order (for example, `sheet-1.jpg`, `sheet-2.jpg`).
6. Review the extracted samples. If a character is wrong or missing, correct the sheet and upload it again.
7. Click **Review characters and save TTF…**, choose a font name and save location.

The app saves a `.ttf` or `.otf` font and a matching `.profile.json` file. Keep both files together if you move them outside a saved project. A saved project copies its selected font into its `fonts` folder.

The character sheet is the supported way to map handwriting samples to individual characters. Ordinary notebook pages are not automatically transformed into a complete font.

## Edit pages

- **Draw a region:** Click **Draw line box**, then drag over the text area on the page.
- **Select a region:** Click its box on the page or its row in the region table. Enter or correct the transcription in **Selected line**.
- **Move a region:** Drag inside the selected box. Resize it by dragging the lower-right handle.
- **Pan and zoom:** Use the mouse wheel to zoom. Middle- or right-drag to pan.
- **Split or delete:** Select a region and use **Split selected** or **Delete**.
- **Preserve the original:** Use **Keep original** for a region that should not be replaced. Empty regions are kept unchanged during reconstruction.
- **Lock placement:** Use **Lock position** to prevent moving or resizing a region.
- **Precise geometry:** Expand **Exact position** to enter X, Y, width, height, and baseline values in source-image pixels.
- **Review:** Switch among reconstructed, original, overlay, and difference views, or open **Compare side by side**.

## Save and export

- **Save / Save As:** Projects are folders containing `project.json`, page images, and the font asset when available. Reopen a project through **File → Open project…** and select its `project.json`.
- **Unsaved work:** When closing or switching documents, the app offers Save, Discard, or Cancel.
- **Undo and redo:** Available during the current editing session. The undo history is not persisted after closing the app.
- **PDF export:** Produces a raster-based PDF from the current rebuilt previews (or the original pages if a page has not been rebuilt). It does not preserve a searchable text layer, original annotations, or form fields.
- **PNG export:** Writes page images to a selected output folder.
- Export checks may report issues but do not guarantee that a page looks correct. Inspect the output yourself.

## OCR setup

Text detection uses the optional Tesseract OCR engine through `pytesseract`. Installing the Python package alone does not install the Tesseract program.

1. Install Tesseract OCR for Windows.
2. Ensure `tesseract.exe` is available on your system `PATH` (or configure Tesseract for your Python environment).
3. Restart the app and click **Detect text**.

If Tesseract is missing or fails to run, detection may return no regions. OCR works best on clear printed text and may miss or misread handwriting, equations, diagrams, faint writing, or crowded layouts. Treat every result as a suggestion; draw boxes and type text manually when needed.

## Restrictions and known limitations

- **Static font, not a handwriting model:** The generated font has one outline per captured character. It cannot learn stroke order, pressure, connected cursive joins, or the natural variations of writing by hand. The baseline-variation option only adds a small placement variation.
- **Template required:** Reliable font creation depends on completing the app's two-page character sheet, with each character in its assigned box and the registration markers visible. It cannot infer a full alphabet from arbitrary notebook pages.
- **Limited character coverage:** Only characters captured in the sheet are available. Missing or unreadable samples may produce an incomplete font. Text containing unsupported characters can be left unchanged; inspect render warnings and the result.
- **OCR is optional and imperfect:** Tesseract must be installed separately. Handwriting, symbols, equations, and diagrams often need manual transcription and region editing.
- **Manual layout work may be needed:** Text is rendered inside the selected region. It is not automatically reflowed across multiple lines or repositioned around other content. Long text may not fit and can be flagged.
- **Original-text removal is approximate:** Region cleanup uses image processing/inpainting. It may leave traces or blur/reconstruct paper texture imperfectly, especially on complex backgrounds. Compare with the original.
- **Review is essential:** Detection confidence and export checks are advisory, not proof of correctness. Exporting anyway can include unreviewed or visibly incorrect results.
- **Raster-based PDF workflow:** PDFs are rendered to images at 300 DPI on import. Exported PDFs contain page images rather than editable/searchable text, and do not retain the original PDF's interactive forms, annotations, or vector content. Original PDF page dimensions may not be preserved exactly.
- **No promise of perfect replication:** Ink color, spacing, line placement, font metrics, and cleanup will differ from the source and from actual pen writing. Results depend on scan/photo quality and the selected font.
- **Windows-focused setup:** The provided `.bat` scripts target Windows. Other operating systems may require manual environment setup and may not be tested.
- **Local-only storage:** Documents and profiles are processed on your computer by this app. The app has no cloud sync or collaboration service. Protect your project folders and generated handwriting fonts like personal files.

## Troubleshooting

- **Detect text returns nothing:** Install Tesseract separately, check that `tesseract.exe` is on `PATH`, restart the app, and try again. You can always draw boxes manually.
- **Only some lines are detected:** OCR is a suggestion. Add missed regions with **Draw line box** and correct transcriptions yourself.
- **A character looks incorrect or is missing:** Check it in the character review dialog. Refill that template cell clearly and rebuild the profile. Unsupported characters are not automatically substituted.
- **Text is clipped or flagged:** Shorten the transcription or enlarge the region with its lower-right handle. The app does not automatically flow text to another line.
- **Old preview remains visible:** Rebuild the page after changing its text or geometry. A stale preview is marked and export checks will mention it.
- **PDF output size differs from the original:** The app rasterizes at 300 DPI; original PDF page-size metadata is not guaranteed to be retained.

## Project files and privacy

Projects may contain the original assignment pages, reconstructed previews, text transcriptions, region geometry, settings, and a copy of the selected font. Keep project folders private when they contain personal or sensitive documents. Do not commit assignment scans, completed character sheets, personal fonts, generated profiles, or exported work to a public repository.

The repository's `.gitignore` excludes common local environments, logs, generated character sheets/fonts/profiles, and export folders. Review `git status` before publishing to ensure no personal documents were added.

To generate the synthetic sample project again, run:

```powershell
python create_sample.py
```

Then open `sample_project/project.json` from the app.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for the full text. Third-party dependencies remain under their respective licenses.
