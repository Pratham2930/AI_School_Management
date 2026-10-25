from pathlib import Path
from datetime import datetime
import shutil
import re

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / 'templates'
STATIC = ROOT / 'static'
if not (ROOT / 'app.py').is_file() or not TEMPLATES.is_dir():
    raise SystemExit('ERROR: Place this script beside app.py inside AI_School_Management.')

CSS = r'''/* EduSphere professional theme - additive, existing routes and content unchanged */
:root {
  --pro-blue:#2563eb; --pro-blue-dark:#1d4ed8; --pro-navy:#0f172a;
  --pro-bg:#f5f7fb; --pro-surface:#ffffff; --pro-line:#e2e8f0;
  --pro-muted:#64748b; --pro-shadow:0 5px 24px rgba(15,23,42,.045);
}
html {scroll-behavior:smooth}
body {background-color:var(--pro-bg);color:var(--pro-navy);font-family:Inter,"Segoe UI",system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
/* Common containers: visual refinement without changing layout display modes */
main, .main, .main-content, .content-wrapper, .dashboard-content {min-width:0}
h1,h2,h3,h4,h5,h6 {letter-spacing:-.025em;color:var(--pro-navy)}
h1 {font-weight:750} h2,h3 {font-weight:700}
/* Cards and dashboard widgets */
.card, .stat-card, .stats-card, .metric-card, .dashboard-card, .summary-card,
.info-card, .report-card, .chart-card, .panel, .widget, .quick-actions {
  border-radius:16px; border-color:var(--pro-line); box-shadow:var(--pro-shadow);
}
.card, .stat-card, .stats-card, .metric-card, .dashboard-card, .summary-card,
.info-card, .report-card, .chart-card, .panel, .widget {background-color:var(--pro-surface)}
/* Inputs: don't override hidden inputs, checkbox, radio, submit, or file upload */
input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=submit]):not([type=button]):not([type=file]),
select,textarea,.form-control,.form-select {
  border:1px solid #cbd5e1; border-radius:10px; background-color:#fff;
  color:var(--pro-navy); max-width:100%; transition:border-color .15s,box-shadow .15s;
}
input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=submit]):not([type=button]):not([type=file]):focus,
select:focus,textarea:focus,.form-control:focus,.form-select:focus {
  border-color:var(--pro-blue); outline:2px solid transparent;
  box-shadow:0 0 0 3px rgba(37,99,235,.14);
}
/* Buttons: preserve existing button sizes and semantics */
button,.btn {transition:background-color .16s,box-shadow .16s,transform .16s}
button:focus-visible,.btn:focus-visible,a:focus-visible {outline:3px solid #93c5fd;outline-offset:2px}
.btn-primary,button.btn-primary,a.btn-primary {background-color:var(--pro-blue);border-color:var(--pro-blue);color:white}
.btn-primary:hover,button.btn-primary:hover,a.btn-primary:hover {background-color:var(--pro-blue-dark);border-color:var(--pro-blue-dark)}
/* Data tables: keep table structure, scroll wide tables on small screens */
table {border-collapse:separate;border-spacing:0;max-width:100%}
th {font-weight:650;letter-spacing:.01em}
thead {background-color:#f8fafc}
td,th {border-bottom-color:var(--pro-line)}
tbody tr:hover {background-color:rgba(37,99,235,.025)}
.table-responsive {overflow-x:auto}
/* Badges, alerts, links */
.badge {border-radius:7px;font-weight:650}
.alert {border-radius:12px}
a {text-underline-offset:3px}
/* Existing installed EduSphere drawer: improve styling without adding another menu */
#edu-sidebar {background:#0f172a!important}
#edu-sidebar .edu-brand {letter-spacing:-.03em}
#edu-sidebar a.edu-link {border-radius:10px}
#edu-menu-trigger {background:#2563eb!important;border-radius:12px!important}
/* Existing navigation heading readability */
#edu-sidebar .edu-heading {color:#a8b7ce}
/* Accessibility and responsive behavior */
@media(max-width:768px){
  .card,.stat-card,.stats-card,.metric-card,.dashboard-card,.summary-card,
  .info-card,.report-card,.chart-card,.panel,.widget {border-radius:12px}
  img,svg,canvas {max-width:100%}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{transition-duration:.01ms!important;animation-duration:.01ms!important}}
'''

CSS_PATH = STATIC / 'css' / 'edusphere_professional_theme.css'
CSS_PATH.parent.mkdir(parents=True,exist_ok=True)
BACKUP = ROOT / 'ui_backups' / ('professional_theme_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
TAG = '''    <!-- EduSphere professional theme -->\n    <link rel="stylesheet" href="{{ url_for('static', filename='css/edusphere_professional_theme.css') }}">\n'''
changed=[]; skipped=[]
for template in sorted(TEMPLATES.rglob('*.html')):
    if 'components' in template.relative_to(TEMPLATES).parts:
        continue
    source=template.read_text(encoding='utf-8-sig')
    if 'edusphere_professional_theme.css' in source:
        skipped.append(str(template.relative_to(TEMPLATES))+' (already installed)')
        continue
    if not re.search(r'</head\s*>',source,re.I) or not re.search(r'</body\s*>',source,re.I):
        skipped.append(str(template.relative_to(TEMPLATES))+' (partial/child template)')
        continue
    relative=template.relative_to(ROOT)
    destination=BACKUP / relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(template,destination)
    modified=re.sub(r'</head\s*>',lambda m:TAG+m.group(0),source,count=1,flags=re.I)
    template.write_text(modified,encoding='utf-8')
    changed.append(str(relative))
print('Professional theme installed.')
print('Templates updated:',len(changed))
print('Skipped:',len(skipped))
print('Backup folder:',BACKUP if changed else '(no template changes needed)')
print('Theme CSS:',CSS_PATH)
print('No app.py or database changes.')
print('Note: Pages using inherited layouts receive styling through their parent template.')
