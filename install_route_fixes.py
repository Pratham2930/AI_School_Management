from pathlib import Path
from datetime import datetime
import shutil
import re
import sys

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'app.py').is_file() or not (ROOT / 'templates').is_dir():
    print('ERROR: Copy this installer into the folder containing app.py and templates.'); sys.exit(1)

changes = {
    'templates/ai_assistant.html': [('ai_assistant_chat', 'school_ai_chat')],
    'templates/components/school_sidebar.html': [('admin_admission_records', 'admission_records'), ('admin_fees_verify', 'admin_fee_verify')],
}

# Replace a broken POST to an unregistered endpoint with a safe navigation
# to the existing curriculum generator. No curriculum is modified automatically.
path = ROOT / 'templates/admin/ai_subject_setup.html'
if path.exists():
    src = path.read_text(encoding='utf-8')
    pattern = r'<form\b[^>]*\baction="\{\{\s*url_for\(\s*[\'\"]auto_load_curriculum[\'\"][\s\S]*?\}\}"[^>]*>[\s\S]*?</form>'
    match = re.search(pattern, src, re.I)
    if match:
        replacement = '''<a class="auto-button" href="{{ url_for('curriculum_generator') }}" title="Open the curriculum generator to review and apply changes">Open Curriculum Generator</a>'''
        changes['templates/admin/ai_subject_setup.html'] = [(match.group(0), replacement)]
    elif 'auto_load_curriculum' in src:
        print('WARNING: Curriculum form structure differs from known snapshot; leaving it unchanged for manual review.')

pending = []
for relative, edits in changes.items():
    target = ROOT / relative
    if not target.exists():
        print('SKIP missing:', relative); continue
    old = target.read_text(encoding='utf-8')
    new = old
    for before, after in edits:
        new = new.replace(before, after)
    if new != old:
        pending.append((target, old, new))
        print('UPDATE:', relative)
    else:
        print('UNCHANGED:', relative)

if '--dry-run' in sys.argv:
    print('Dry run only. Files to update:', len(pending)); sys.exit(0)
if not pending:
    print('No changes needed.'); sys.exit(0)
backup = ROOT / ('edunova_route_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
for target, old, new in pending:
    saved = backup / target.relative_to(ROOT)
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, saved)
    target.write_text(new, encoding='utf-8')
print('Updated', len(pending), 'files. Backups:', backup)
print('Restart Flask and test the AI chat, admissions/fees navigation, and curriculum generator.')
