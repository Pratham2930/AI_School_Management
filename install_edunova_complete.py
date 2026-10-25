"""EduNova unified UI upgrade for the existing Flask project.
Preview: python install_edunova_complete.py --dry-run
Apply:   python install_edunova_complete.py
Backs up modified templates. Never modifies app.py or database files.
"""
from pathlib import Path
from datetime import datetime
import argparse
import re
import shutil

ROOT = Path(__file__).resolve().parent
CSS_NAME = 'edunova_unified.css'
CSS_TAG = "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='css/edunova_unified.css') }}\">"
ROLES = {'admin':'Administration','teacher':'Teacher Portal','student':'Student Portal','parent':'Parent Portal','staff':'Staff Portal','fees':'Fee Management'}
OLD_BARS = [
    re.compile(r'^\s*<header\b[^>]*class=["\'][^"\']*\bedn-mast\b[^"\']*["\'][^>]*>.*?</header>\s*', re.I | re.M),
    re.compile(r'^\s*<header\b[^>]*class=["\'][^"\']*\bedunova-layout-shell\b[^"\']*["\'][^>]*>.*?</header>\s*', re.I | re.M),
    re.compile(r'^\s*<div\b[^>]*id=["\']nova-topbar["\'][^>]*>[^\r\n]*</div>\s*', re.I | re.M),
]

def update(source, rel):
    if re.search(r'\bedn-unified\b', source):
        return source
    if not re.search(r'<html\b', source, re.I) or not re.search(r'<body\b', source, re.I):
        return source
    # Preserve the working dashboard and authentication/setup pages.
    if rel.as_posix() in ('admin/dashboard.html','admin/setup.html') or rel.name == 'login.html':
        return source
    role = rel.parts[0] if len(rel.parts)>1 else 'school'
    title = re.sub(r'[_-]+',' ',rel.stem).title()
    # Remove only installer-added branding bars, never page-specific headers.
    for pat in OLD_BARS:
        source = pat.sub('\n', source)
    source = re.sub(r'^\s*<!-- edunova-layout-shell:.*?-->\s*', '\n', source, flags=re.M)
    # Remove only a known broken stylesheet link; preserve functional styles.
    source = re.sub(r'<link\b(?=[^>]*edusphere_professional_theme\.css)[^>]*>\s*', '', source, flags=re.I|re.S)
    # If the older management installer left a wrapper, keep it for compatibility.
    # Add our own class without replacing existing body attributes.
    def add_body(m):
        attrs=m.group(1)
        cm=re.search(r'\bclass\s*=\s*(["\'])(.*?)\1',attrs,re.I|re.S)
        if cm:
            attrs=attrs[:cm.start(2)]+cm.group(2)+' edn-unified'+attrs[cm.end(2):]
        else:
            attrs += ' class="edn-unified"'
        return '<body'+attrs+'>'
    source=re.sub(r'<body\b([^>]*)>',add_body,source,count=1,flags=re.I)
    # Put the final override last in HEAD, regardless of earlier installers.
    source=re.sub(r'</head\s*>','\n'+CSS_TAG+'\n</head>',source,count=1,flags=re.I)
    if CSS_TAG not in source:
        return source
    # Existing mast header from old installer was removed; replace with one shared branded header.
    header=(f'\n<!-- EduNova unified header -->\n<header class="edn-global-header" role="banner">'
            f'<div class="edn-global-brand"><span class="edn-global-icon">✦</span>'
            f'<span>EduNova <b>AI</b></span><span class="edn-global-divider">/</span>'
            f'<span class="edn-global-context">{ROLES.get(role,"School Portal")}</span></div>'
            f'<span class="edn-global-page">{title}</span></header>\n')
    source=re.sub(r'<body\b[^>]*>',lambda m:m.group(0)+header,source,count=1,flags=re.I)
    return source

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if not (ROOT/'app.py').is_file() or not (ROOT/'templates').is_dir():
        raise SystemExit('Place the installer and CSS beside app.py in your existing project.')
    files=sorted((ROOT/'templates').rglob('*.html'))
    changes=[]
    for path in files:
        try:
            before=path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            print('SKIP encoding:',path);continue
        after=update(before,path.relative_to(ROOT/'templates'))
        if after!=before: changes.append((path,before,after))
    print(f'Found {len(files)} templates; {len(changes)} pages to upgrade.')
    for path,_,_ in changes:
        print(('PREVIEW' if args.dry_run else 'UPDATED'),path.relative_to(ROOT))
    if args.dry_run:
        print('Dry run: no files changed.');return
    backup=ROOT/'ui_backups'/('edunova-unified-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    for path,before,after in changes:
        dst=backup/path.relative_to(ROOT)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dst)
        path.write_text(after,encoding='utf-8')
    css_dst=ROOT/'static/css'/CSS_NAME
    css_dst.parent.mkdir(parents=True,exist_ok=True)
    if css_dst.exists():
        dst=backup/'static/css'/CSS_NAME
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(css_dst,dst)
    shutil.copy2(ROOT/CSS_NAME,css_dst)
    print('Done. Backup:',backup)
    print('No application Python code or database files were modified.')

if __name__=='__main__': main()
