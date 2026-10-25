from pathlib import Path
from datetime import datetime
import shutil

root = Path(__file__).resolve().parent
project = Path.cwd()
target = project / 'templates' / 'admin' / 'fee_verify.html'
source = root / 'fee_verify.html'
if not (project / 'app.py').is_file() or not target.parent.is_dir():
    raise SystemExit('Run this installer from your AI_School_Management project folder (with app.py).')
if not source.is_file() or source.stat().st_size == 0:
    raise SystemExit('Missing restoration template. Extract all ZIP files together.')
if target.exists():
    backup = target.with_name('fee_verify.html.backup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(target, backup)
    print('Backup:', backup)
shutil.copy2(source, target)
print('Restored:', target, 'size:', target.stat().st_size, 'bytes')
