from __future__ import annotations


def validate_page(page: dict) -> list[str]:
    """Return actionable export warnings without guessing that a page is complete."""
    issues: list[str] = []
    original = page.get('original')
    if original is None:
        return ['Original page image is missing']
    width, height = original.size
    regions = page.get('regions', [])
    preview = page.get('preview')

    if not regions:
        issues.append('No text regions were reviewed; this page will remain unchanged')
    if preview is None:
        issues.append('Page has not been rebuilt; export will use the original page')
    elif preview.size != original.size:
        issues.append('Reconstructed page dimensions changed')
    if page.get('preview_stale'):
        issues.append('Page edits changed since the last rebuild')

    valid_boxes: list[tuple[int, tuple[int, int, int, int]]] = []
    for i, region in enumerate(regions):
        try:
            x, y, box_width, box_height = map(int, region['bbox'])
        except (KeyError, TypeError, ValueError):
            issues.append(f'Region {i + 1} has invalid geometry')
            continue
        if box_width <= 0 or box_height <= 0:
            issues.append(f'Region {i + 1} has zero or negative size')
        if x < 0 or y < 0 or x + box_width > width or y + box_height > height:
            issues.append(f'Region {i + 1} extends beyond page bounds')
        try:
            confidence=float(region.get('confidence',1))
        except (TypeError,ValueError):
            confidence=0.0
        if confidence < .5 and region.get('status') != 'manual':
            issues.append(f'Region {i + 1} has low OCR confidence')
        if not str(region.get('text') or '').strip() and not region.get('protected'):
            issues.append(f'Region {i + 1} has no transcription and will stay unchanged')
        for previous_index, earlier in valid_boxes:
            sx, sy, sw, sh = earlier
            if x < sx + sw and x + box_width > sx and y < sy + sh and y + box_height > sy:
                issues.append(f'Regions {previous_index + 1} and {i + 1} overlap')
        valid_boxes.append((i, (x, y, box_width, box_height)))

    for warning in page.get('render_warnings', []):
        region_number = int(warning.get('region', -1)) + 1
        issues.append(f'Region {region_number}: {warning.get("message", "needs review")}')
    return issues
