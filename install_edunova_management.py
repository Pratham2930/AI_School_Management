from pathlib import Path
import re, shutil, datetime
root=Path(__file__).resolve().parent
css_src=root/'edunova_management.css'
css_dst=root/'static/css/edunova_management.css'
if not (root/'app.py').exists():
    raise SystemExit('Run from project root alongside app.py and this installer.')
css_dst.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(css_src,css_dst)
backup=root/'ui_backups'/('edunova-management-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True,exist_ok=True)
for name in ('students','teachers'):
    path=root/'templates/admin'/f'{name}.html'
    if not path.exists():
        print('SKIPPED missing:',path);continue
    raw=path.read_text(encoding='utf-8')
    if 'edn-management' in raw:
        print('ALREADY UPDATED:',path);continue
    shutil.copy2(path,backup/path.name)
    # Existing CSS preserved; dedicated override loaded at end of head.
    css_tag='\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/edunova_management.css\') }}">\n'
    raw=re.sub(r'</head\s*>',css_tag+'</head>',raw,count=1,flags=re.I)
    raw=re.sub(r'<body([^>]*)>',lambda m:'<body'+m.group(1)+' class="edn-management">\n<div class="edn-shell">\n<header class="edn-mast"><div class="edn-brand"><span class="edn-logo">✦</span><span>EduNova <span style="color:#3d67d8">AI</span></span><span class="edn-crumb">/ Admin / '+name.title()+'</span></div><span class="edn-pill">School Management Portal</span></header>',raw,count=1,flags=re.I)
    if name=='students':
        stats='''<div class="edn-statrow"><div class="edn-stat"><span>Total Students</span><strong>{{ students|length }}</strong><small>Current admission records</small></div><div class="edn-stat"><span>Admission Management</span><strong>Active</strong><small>Manage students and divisions</small></div><div class="edn-stat"><span>Academic Records</span><strong>View</strong><small>Student information below</small></div></div>'''
    else:
        stats='''<div class="edn-statrow"><div class="edn-stat"><span>Total Teachers</span><strong>{{ teacher_data|length }}</strong><small>Registered teaching staff</small></div><div class="edn-stat"><span>Teacher Management</span><strong>Active</strong><small>Accounts and assignments</small></div><div class="edn-stat"><span>Faculty Records</span><strong>View</strong><small>Teacher details below</small></div></div>'''
    # Insert stat row directly before the first content panel/table, after flash messages.
    start=raw.find('<div class="main-content full-page">')
    if start!=-1:
        pos=raw.find('<div class="panel">',start)
        if pos<0:pos=raw.find('<div class="table-wrapper">',start)
        if pos!=-1:raw=raw[:pos]+stats+'\n'+raw[pos:]
    raw=re.sub(r'</body\s*>','<footer class="edn-footer">EduNova AI · School Management</footer>\n</div>\n</body>',raw,count=1,flags=re.I)
    path.write_text(raw,encoding='utf-8')
    print('REDESIGNED:',path)
print('Backups:',backup)
print('Only two HTML templates and one stylesheet changed. Database and app.py untouched.')
