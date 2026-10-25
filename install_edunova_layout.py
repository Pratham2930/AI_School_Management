"""Apply a shared EduNova page shell to role templates; preserve all Jinja and forms."""
from pathlib import Path
from datetime import datetime
import re, shutil
ROOT=Path(__file__).resolve().parent
if not (ROOT/'app.py').exists() or not (ROOT/'templates').is_dir():
    raise SystemExit('Place installer and CSS in the project root alongside app.py.')
SRC=ROOT/'edunova_layout.css'
if not SRC.exists(): raise SystemExit('Missing edunova_layout.css next to installer.')
STAMP=datetime.now().strftime('%Y%m%d-%H%M%S')
BACKUP=ROOT/'ui_backups'/('edunova-layout-'+STAMP)
CSS=ROOT/'static'/'css'/'edunova_layout.css'
CSS.parent.mkdir(parents=True,exist_ok=True)
if CSS.exists():
    (BACKUP/'static'/'css').mkdir(parents=True,exist_ok=True)
    shutil.copy2(CSS,BACKUP/'static'/'css'/'edunova_layout.css')
shutil.copy2(SRC,CSS)
STYLE='''<link rel="stylesheet" href="{{ url_for('static', filename='css/edunova_layout.css') }}">'''
ROLES={'admin':('Administration','admin_dashboard'),'teacher':('Teacher Portal','teacher_dashboard'),'student':('Student Portal','student_dashboard'),'parent':('Parent Portal','parent_dashboard'),'staff':('Staff Portal','staff_dashboard')}
count=0
for role,(label,endpoint) in ROLES.items():
    folder=ROOT/'templates'/role
    if not folder.is_dir():continue
    for file in folder.rglob('*.html'):
        if role=='admin' and file.name=='dashboard.html':continue
        s=file.read_text(encoding='utf-8-sig')
        if '<html' not in s.lower() or '</head>' not in s.lower() or '<body' not in s.lower():continue
        if 'edunova-layout-shell' in s:continue
        original=s
        # Remove previous stylesheet entry, then load new shell CSS at the end of head.
        s=re.sub(r'<link\b[^>]*edunova_layout\.css[^>]*>', '',s,flags=re.I|re.S)
        s=re.sub(r'</head\s*>', '    '+STYLE+'\n</head>',s,count=1,flags=re.I)
        header=('''\n<!-- edunova-layout-shell: shared visual header, no backend changes -->\n'''
          f'''<header class="edunova-layout-shell" role="banner"><a class="edunova-layout-brand" href="{{{{ url_for('{endpoint}') }}}}">'''
          '''<span class="edunova-layout-logo">✦</span><span>EduNova <small>AI School</small></span></a>'''
          f'''<div class="edunova-layout-context"><span class="edunova-layout-role">{label}</span><span class="edunova-layout-dot"></span> School Management</div>'''
          f'''<a class="edunova-layout-home" href="{{{{ url_for('{endpoint}') }}}}">Dashboard</a></header>\n''')
        s=re.sub(r'(<body\b[^>]*>)',lambda m:m.group(1)+header,s,count=1,flags=re.I|re.S)
        dest=BACKUP/file.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,dest)
        file.write_text(s,encoding='utf-8')
        count+=1
print(f'EduNova shared layout added to {count} templates.')
print('Admin Dashboard preserved. Backups:',BACKUP)
print('No changes to app.py, routes, or database.')
