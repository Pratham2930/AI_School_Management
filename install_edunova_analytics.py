from pathlib import Path
from datetime import datetime
import argparse, shutil, re

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT
if not (PROJECT / 'app.py').exists():
    raise SystemExit('Place this installer and the assets folder in the project root, alongside app.py.')
TEMPLATE = PROJECT / 'templates/admin/dashboard.html'
if not TEMPLATE.exists():
    raise SystemExit('Missing templates/admin/dashboard.html')
parser = argparse.ArgumentParser()
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
html = TEMPLATE.read_text(encoding='utf-8')
MARK = '<!-- EDUNOVA_ANALYTICS_V1 -->'
if MARK in html:
    print('Analytics already installed. No changes made.')
    raise SystemExit(0)
if 'total_students' not in html or 'school_health' not in html:
    raise SystemExit('Dashboard template does not contain the expected totals and school_health variables; no changes made.')
if '</head>' not in html.lower() or '</body>' not in html.lower():
    raise SystemExit('Dashboard missing head/body closing tags; no changes made.')
if args.dry_run:
    print('Ready to add analytics to Admin Dashboard and install 2 static assets. No changes made.')
    raise SystemExit(0)
backup = PROJECT / 'ui_backups' / ('analytics-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, backup / 'dashboard.html')
for name in ['edunova_analytics.css','edunova_analytics.js']:
    dest = PROJECT / 'static' / ('css' if name.endswith('.css') else 'js') / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.copy2(dest, backup / name)
    shutil.copy2(ROOT / 'analytics_assets' / name, dest)

panel = '''
<!-- EDUNOVA_ANALYTICS_V1 -->
<section class="edna-section" aria-label="School analytics">
  <div class="edna-heading"><div><h2>Analytics & Insights</h2><p>Current school totals and health indicators from your dashboard data</p></div><button type="button" class="edna-export" id="edna-export">Export overview CSV</button></div>
  <div class="edna-layout">
    <article class="edna-card"><div class="edna-card-heading"><h3>School community</h3><span>Current totals</span></div><div id="edna-bars" class="edna-bars" role="img" aria-label="Bar chart of students, teachers, parents and staff"></div><p class="edna-note">Values are current totals, not historical trends.</p></article>
    <article class="edna-card"><div class="edna-card-heading"><h3>School health</h3><span>Current indicators</span></div><div class="edna-health"><div class="edna-ring" id="edna-ring"><div><strong id="edna-score">—</strong><small>out of 100</small></div></div><div class="edna-health-details"><div><span>Attendance</span><strong id="edna-attendance">—</strong></div><div><span>Academic performance</span><strong id="edna-academic">—</strong></div><div><span>Status</span><strong id="edna-status">—</strong></div></div></div><p class="edna-note">Health metrics reflect the latest values supplied by the application.</p></article>
  </div>
  <div class="edna-bottom"><div><strong>School structure</strong><span id="edna-structure">Loading school totals…</span></div><a href="{{ url_for('admin_reports') }}">Open detailed reports →</a></div>
</section>
<script id="edna-data" type="application/json">{{ {'students': total_students, 'teachers': total_teachers, 'parents': total_parents, 'staff': total_staff, 'classes': total_classes, 'subjects': total_subjects, 'score': school_health.score, 'attendance': school_health.attendance, 'academic': school_health.academic, 'status': school_health.status}|tojson }}</script>
<!-- /EDUNOVA_ANALYTICS_V1 -->
'''
# Insert after stats grid when identifiable, otherwise before Quick Actions panel.
marker = '<!-- =================================================\n\n         QUICK ACTIONS'
idx = html.find(marker)
if idx < 0:
    idx = html.find('<!-- QUICK ACTIONS')
if idx < 0:
    raise SystemExit('Could not locate Quick Actions section; assets copied but dashboard unchanged. Restore any assets from backup if needed.')
html = html[:idx] + panel + '\n' + html[idx:]
html = re.sub(r'</head\s*>', '''<link rel="stylesheet" href="{{ url_for('static', filename='css/edunova_analytics.css') }}">\n</head>''', html, count=1, flags=re.I)
html = re.sub(r'</body\s*>', '''<script defer src="{{ url_for('static', filename='js/edunova_analytics.js') }}"></script>\n</body>''', html, count=1, flags=re.I)
TEMPLATE.write_text(html, encoding='utf-8')
print('EduNova Analytics installed on Admin Dashboard. No app.py or database changes.')
print('Backup:', backup)
print('Restart Flask and press Ctrl+F5.')
