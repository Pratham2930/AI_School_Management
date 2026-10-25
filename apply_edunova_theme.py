"""Add a consistent EduNova-inspired UI layer to existing Flask templates.
Run from the project root; no app.py or database changes.
"""
from pathlib import Path
from datetime import datetime
import shutil
import re

root = Path(__file__).resolve().parent
templates = root / 'templates'
static = root / 'static' / 'css'
if not (root/'app.py').is_file() or not templates.is_dir():
    raise SystemExit('Place this script next to app.py in AI_School_Management.')

css = r'''/* EduNova-inspired project-wide theme; original functionality is unchanged. */
:root{--nova-blue:#2563eb;--nova-navy:#102c5a;--nova-text:#182c4a;--nova-muted:#64748b;--nova-bg:#f6f8fc;--nova-line:#e4eaf3;--nova-shadow:0 8px 26px rgba(24,46,83,.055)}
body{background:var(--nova-bg);color:var(--nova-text);font-family:Inter,"Segoe UI",Arial,sans-serif;font-size:14px}
body .main-content,body .main,body .content-wrapper,body .dashboard-content{min-width:0}
body .main-content,body .main,body .dashboard-content{padding:clamp(16px,2.5vw,34px)}
body h1{font-size:clamp(25px,2.2vw,34px);letter-spacing:-.035em;color:var(--nova-text);font-weight:750}
body h2{letter-spacing:-.025em;color:var(--nova-text)}
body p,body .muted{line-height:1.6}
body .card,body .stat-card,body .metric-card,body .panel,body .status-card,body .summary-card,body .quick-actions,body .action-card,body .widget,body .table-container{background:#fff;border:1px solid var(--nova-line);border-radius:16px;box-shadow:var(--nova-shadow)}
body .card,body .panel,body .status-card,body .summary-card,body .widget{padding:clamp(16px,2vw,26px)}
body table{width:100%;border-collapse:separate;border-spacing:0;background:white;border:1px solid var(--nova-line);border-radius:12px;overflow:hidden}
body th{background:#f7f9fd;color:#50637e;font-size:12px;font-weight:700;text-align:left}
body td,body th{padding:12px 14px;border-bottom:1px solid #edf1f7}
body tr:last-child td{border-bottom:0}
body input:not([type=checkbox]):not([type=radio]):not([type=hidden]),body select,body textarea{max-width:100%;border:1px solid #d7e1ef;border-radius:9px;padding:10px 12px;background:#fff;color:var(--nova-text);font:inherit}
body input:focus-visible,body select:focus-visible,body textarea:focus-visible{outline:3px solid #bfdbfe;outline-offset:1px;border-color:var(--nova-blue)}
body button,body .btn,body .primary-btn,body input[type=submit]{border-radius:9px;font-weight:650}
body a{color:#1d55c5}
body a:focus-visible,body button:focus-visible{outline:3px solid #93c5fd;outline-offset:2px}
body .page-header,body .header{gap:16px;flex-wrap:wrap}
/* Keep existing EduSphere drawer; remove original permanent menus only on pages with it. */
body:has(#edu-menu-trigger) > .sidebar,body:has(#edu-menu-trigger) .layout > aside.sidebar,body:has(#edu-menu-trigger) .layout > div.sidebar{display:none!important}
body:has(#edu-menu-trigger) > .main-content,body:has(#edu-menu-trigger) .layout > main.main,body:has(#edu-menu-trigger) > .main,body:has(#edu-menu-trigger) .content-wrapper{margin-left:0!important;max-width:100%!important;width:100%!important}
/* The original dashboard often has a fixed left menu and an adjacent content wrapper. */
body:has(#edu-menu-trigger) > .sidebar ~ .main-content,body:has(#edu-menu-trigger) > .sidebar ~ .main{margin-left:0!important;width:100%!important;max-width:100%!important}
/* Compact header; no fake stats or data inserted. */
#nova-topbar{box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px clamp(16px,2.5vw,34px);background:#fff;border-bottom:1px solid var(--nova-line);font:600 14px Inter,"Segoe UI",sans-serif;color:var(--nova-text)}
#nova-topbar .nova-brand{display:flex;align-items:center;gap:10px}
#nova-topbar .nova-mark{display:grid;place-items:center;width:33px;height:33px;border-radius:10px;background:linear-gradient(135deg,#1d4ed8,#38bdf8);color:white;font-size:18px}
#nova-topbar .nova-tag{color:var(--nova-muted);font-size:12px;font-weight:400}
#nova-topbar .nova-right{display:flex;align-items:center;gap:12px}
#nova-topbar .nova-pill{background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:7px 11px;font-size:12px}
/* Keep floating controls out of each other's way. */
#edu-menu-trigger{bottom:16px!important;left:16px!important}
@media(max-width:700px){#nova-topbar{padding:12px 15px}#nova-topbar .nova-tag{display:none}body td,body th{padding:9px}body .cards{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}}
'''
static.mkdir(parents=True,exist_ok=True)
(static/'edunova_theme.css').write_text(css,encoding='utf-8')
backup=root/'ui_backups'/('edunova-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
updated=[]
for file in sorted(templates.rglob('*.html')):
    if 'components' in file.relative_to(templates).parts: continue
    raw=file.read_text(encoding='utf-8',errors='replace')
    if not re.search(r'</head\s*>',raw,re.I) or not re.search(r'<body(?:\s[^>]*)?>',raw,re.I):continue
    if 'edunova_theme.css' in raw:continue
    rel=file.relative_to(templates)
    dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    link='\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/edunova_theme.css\') }}">\n'
    raw=re.sub(r'</head\s*>',lambda m:link+m.group(),raw,count=1,flags=re.I)
    # Header only for authenticated portal pages; no duplicate global menu.
    if rel.parts[0] in {'admin','teacher','student','parent','staff','fees'} and 'login' not in rel.name and 'setup' not in rel.name and 'receipt' not in rel.name:
        bar='\n<div id="nova-topbar"><div class="nova-brand"><span class="nova-mark">✦</span><span>EduSphere AI <span class="nova-tag">School Management</span></span></div><div class="nova-right"><span class="nova-pill">School Portal</span></div></div>\n'
        raw=re.sub(r'(<body(?:\s[^>]*)?>)',lambda m:m.group()+bar,raw,count=1,flags=re.I)
    file.write_text(raw,encoding='utf-8');updated.append(str(rel))
print('EduNova-inspired theme installed on',len(updated),'templates.')
print('Backups:',backup)
print('Existing routes, app.py and database untouched.')
print('Restart Flask and press Ctrl+F5.')
