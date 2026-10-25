from pathlib import Path
from datetime import datetime
import argparse, shutil, re

ROOT=Path(__file__).resolve().parent
TARGET=Path.cwd()
parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
app=TARGET/'app.py'; report=TARGET/'templates/admin/reports.html'
if not app.exists() or not report.exists(): raise SystemExit('Run from your AI_School_Management project root (beside app.py).')
a=app.read_text(encoding='utf-8');h=report.read_text(encoding='utf-8')
if 'def admin_reports():' not in a: raise SystemExit('Could not find admin_reports; no files changed.')
if 'edunova-phase2-data' in a or 'edunova-phase2-ui' in h:
 print('Phase 2 already installed; nothing changed.');raise SystemExit(0)
# Use a precisely scoped anchor inside the existing reports view.
start=a.index('def admin_reports():'); end=a.find('\ndef ',start+5)
if end<0: raise SystemExit('Cannot locate end of admin_reports; no files changed.')
segment=a[start:end]
anchor='    return render_template(\n        "admin/reports.html",'
if anchor not in segment: raise SystemExit('Reports render anchor changed; no files changed.')
calc='''    # edunova-phase2-data: aggregate only records already authorized by report filters.
    from collections import defaultdict
    from calendar import month_abbr
    class_lookup = {c.id: c for c in report_classes}
    def class_label(class_id):
        c = class_lookup.get(class_id)
        return (f"Std {c.standard} {c.stream or ''} - {c.division}".strip()
                if c else "Unassigned")

    by_class = defaultdict(lambda: {"present": 0, "total": 0, "marks": 0.0, "max": 0.0})
    for row in attendance_rows:
        student = db.session.get(Student, row.student_id)
        label = class_label(student.class_id if student else None)
        by_class[label]["total"] += 1
        if (row.status or "").strip().lower() == "present":
            by_class[label]["present"] += 1
    for mark in graded_marks:
        student = db.session.get(Student, mark.student_id)
        label = class_label(student.class_id if student else None)
        by_class[label]["marks"] += float(mark.marks_obtained or 0)
        by_class[label]["max"] += float(mark.maximum_marks or 0)
    class_analytics = [{
        "label": label,
        "attendance": round(v["present"] * 100 / v["total"], 1) if v["total"] else None,
        "academic": round(v["marks"] * 100 / v["max"], 1) if v["max"] else None,
        "attendance_records": v["total"]
    } for label, v in sorted(by_class.items())]
    monthly_counts = defaultdict(int)
    for student in admissions:
        if student.admission_date:
            monthly_counts[student.admission_date.strftime("%Y-%m")] += 1
    monthly_analytics = [{"month": month, "count": count}
                         for month, count in sorted(monthly_counts.items())]

'''
segment=segment.replace(anchor,calc+anchor).replace('        "admin/reports.html",','        "admin/reports.html",\n        class_analytics=class_analytics,\n        monthly_analytics=monthly_analytics,',1)
a=a[:start]+segment+a[end:]
css='''<link rel="stylesheet" href="{{ url_for('static', filename='css/edunova_phase2.css') }}">'''
h=h.replace('</head>',css+'\n</head>',1)
block='''<!-- edunova-phase2-ui -->
<section class="ed2-wrap" aria-label="Advanced school analytics">
 <div class="ed2-title"><div><p class="ed2-eyebrow">EDUNOVA INTELLIGENCE</p><h2>Advanced Analytics</h2><p>Live records for the selected date range and class filter.</p></div><button type="button" id="ed2-export">Export chart data (CSV)</button></div>
 <div class="ed2-grid">
  <article class="ed2-card"><h3>Class-wise attendance</h3><p>Percentage of recorded attendance marked present</p><div id="ed2-attendance" class="ed2-bars"></div></article>
  <article class="ed2-card"><h3>Academic performance</h3><p>Marks obtained as a percentage of maximum marks</p><div id="ed2-academic" class="ed2-bars"></div></article>
  <article class="ed2-card ed2-wide"><h3>Monthly admissions</h3><p>Admissions by recorded admission month within the selected date range</p><div id="ed2-admissions" class="ed2-months"></div></article>
 </div>
 <p class="ed2-note">No data is shown as “No records” rather than zero performance. Charts reflect the current report filters.</p>
</section>
<script id="ed2-data" type="application/json">{{ {'classes': class_analytics, 'months': monthly_analytics}|tojson }}</script>
<script defer src="{{ url_for('static', filename='js/edunova_phase2.js') }}"></script>
'''
h=h.replace('</main>',block+'\n</main>',1)
files={app:a,report:h,TARGET/'static/css/edunova_phase2.css':(ROOT/'edunova_phase2.css').read_text(encoding='utf-8'),TARGET/'static/js/edunova_phase2.js':(ROOT/'edunova_phase2.js').read_text(encoding='utf-8')}
print('Files to update:');[print(' -',p.relative_to(TARGET)) for p in files]
if args.dry_run:raise SystemExit(0)
backup=TARGET/'ui_backups'/('edunova-phase2-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
for p,contents in files.items():
 if p.exists():
  dst=backup/p.relative_to(TARGET);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(contents,encoding='utf-8')
print('Installed. Backups:',backup)
