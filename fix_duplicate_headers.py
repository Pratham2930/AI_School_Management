from pathlib import Path
import re
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'templates').is_dir():
    raise SystemExit('Place this script in the project root, beside app.py and templates/.')

backup_root = ROOT / 'ui_backups' / ('header-cleanup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
patterns = [
    ('old layout header', re.compile(r'\s*<!--\s*edunova-layout-shell:[^>]*-->\s*<header\b[^>]*class=["\'][^"\']*\bedunova-layout-shell\b[^"\']*["\'][^>]*>.*?</header>', re.I | re.S)),
    ('old layout header', re.compile(r'\s*<header\b[^>]*class=["\'][^"\']*\bedunova-layout-shell\b[^"\']*["\'][^>]*>.*?</header>', re.I | re.S)),
    ('old branding bar', re.compile(r'\s*<div\s+id=["\']nova-topbar["\'][^>]*>\s*<div\s+class=["\']nova-brand["\'][^>]*>.*?</span>\s*</div>\s*<div\s+class=["\']nova-right["\'][^>]*>.*?</div>\s*</div>', re.I | re.S)),
]

changed = 0
for file in sorted((ROOT / 'templates').rglob('*.html')):
    if file.as_posix().endswith('/admin/dashboard.html'):
        continue
    original = file.read_text(encoding='utf-8')
    # Only remove older headers where the new masthead already exists.
    if not re.search(r'<header\b[^>]*class=["\'][^"\']*\bedn-mast\b', original, re.I):
        continue
    updated = original
    removals = []
    for label, pattern in patterns:
        updated, count = pattern.subn('\n', updated)
        if count:
            removals.append(f'{label}: {count}')
    if updated != original:
        backup = backup_root / file.relative_to(ROOT)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, backup)
        file.write_text(updated, encoding='utf-8')
        changed += 1
        print(f'Fixed {file.relative_to(ROOT)} ({", ".join(removals)})')
print(f'Completed. Updated {changed} templates.')
print(f'Backups: {backup_root if changed else "Not needed"}')
print('Admin Dashboard, Python application, and database were not modified.')
