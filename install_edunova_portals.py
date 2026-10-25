"""Apply EduNova styling to existing portal templates without touching app.py or database.
Run from the Flask project root: python install_edunova_portals.py
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / 'templates'
CSS_DIR = ROOT / 'static' / 'css'
SOURCE = ROOT / 'edunova_portals.css'
DEST = CSS_DIR / SOURCE.name
TAG = "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='css/edunova_portals.css') }}\">"
BACKUP = ROOT / 'ui_backups' / ('edunova-portals-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
if not TEMPLATES.is_dir() or not (ROOT / 'app.py').is_file():
    raise SystemExit('Please place both files in the project folder alongside app.py and templates/.')
if not SOURCE.is_file():
    raise SystemExit('Missing edunova_portals.css next to this installer.')
CSS_DIR.mkdir(parents=True, exist_ok=True)
if DEST.exists():
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEST, BACKUP / 'edunova_portals.css')
shutil.copy2(SOURCE, DEST)
updated = []
skipped = []
for role in ('admin', 'teacher', 'student', 'parent', 'staff'):
    folder = TEMPLATES / role
    if not folder.exists():
        continue
    for path in sorted(folder.rglob('*.html')):
        if path.name == 'dashboard.html' and role == 'admin':
            skipped.append(str(path.relative_to(ROOT)) + ' (working Admin Dashboard preserved)')
            continue
        content = path.read_text(encoding='utf-8-sig')
        if 'edunova_portals.css' in content or '</head>' not in content.lower() or '<html' not in content.lower():
            continue
        # Append after all pre-existing inline styles, before the closing head.
        idx = content.lower().rfind('</head>')
        new_content = content[:idx] + '    ' + TAG + '\n' + content[idx:]
        target = BACKUP / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        path.write_text(new_content, encoding='utf-8')
        updated.append(str(path.relative_to(ROOT)))
print(f'EduNova portal styles installed on {len(updated)} templates.')
print(f'Admin Dashboard left unchanged. Backups: {BACKUP}')
print('No Flask routes, Python modules, or database files modified.')
if not updated:
    print('No new template changes needed; styles may already be linked.')
