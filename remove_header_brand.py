from pathlib import Path
import re, shutil, datetime

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / 'templates'
if not TEMPLATES.is_dir():
    raise SystemExit('ERROR: Put this script beside app.py in your EduNova project folder.')

# Only change HTML header/navigation branding, never ordinary page content.
brand = re.compile(r'(?i)edu\s*nova\s*(?:<b\b[^>]*>\s*AI\s*</b>|<strong\b[^>]*>\s*AI\s*</strong>|\s+AI)?')
header_block = re.compile(r'(?is)<header\b[^>]*>.*?</header>')
brand_span = re.compile(r'(?is)<span\b[^>]*>\s*EduNova\s*(?:<b\b[^>]*>\s*AI\s*</b>|<strong\b[^>]*>\s*AI\s*</strong>|AI)?\s*</span>')
brand_div = re.compile(r'(?is)<(?:div|a)\b[^>]*class=["\'][^"\']*(?:global-brand|brand-name|site-brand|logo-text)[^"\']*["\'][^>]*>\s*EduNova\s*(?:<b\b[^>]*>\s*AI\s*</b>|AI)?\s*</(?:div|a)>')

def transform_header(h):
    old=h
    h=brand_span.sub('',h)
    h=brand_div.sub('',h)
    # Remove the separator if the header's brand label was removed.
    if h!=old:
        h=re.sub(r'(?is)<span\b[^>]*class=["\'][^"\']*(?:global-divider|brand-divider)[^"\']*["\'][^>]*>\s*/\s*</span>','',h)
        h=re.sub(r'(?is)<span\b[^>]*class=["\'][^"\']*(?:global-icon|brand-icon)[^"\']*["\'][^>]*>.*?</span>','',h)
    return h

changes=[]
for file in TEMPLATES.rglob('*.html'):
    s=file.read_text(encoding='utf-8-sig')
    changed=header_block.sub(lambda m: transform_header(m.group(0)),s)
    if changed!=s:
        changes.append((file,s,changed))
if not changes:
    print('No matching EduNova AI header labels found. No files changed.')
    print('If branding is still visible, it may be inserted by CSS or JavaScript.')
    raise SystemExit(0)
backup=ROOT/('header_brand_backup_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
for file,old,new in changes:
    dest=backup/file.relative_to(ROOT)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(file,dest)
    file.write_text(new,encoding='utf-8')
    print('Updated:',file.relative_to(ROOT))
print('Total templates:',len(changes))
print('Backups:',backup)
print('Restart Flask, then refresh with Ctrl+F5.')
