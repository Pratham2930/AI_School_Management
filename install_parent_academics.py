from pathlib import Path
import shutil, datetime, ast, sys
base=Path(__file__).resolve().parent
app=base/'app.py'; dash=base/'templates/parent/dashboard.html'; target=base/'templates/parent/child_progress.html'
if not app.exists() or not dash.exists(): sys.exit('Place installer in the EduNova project root beside app.py')
route='''
# EDUNOVA_PARENT_ACADEMICS
@app.route('/parent/child/<int:student_id>/progress')
@login_required
def parent_child_progress(student_id):
    if current_user.role != 'parent':
        abort(403)
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent or not ParentStudent.query.filter_by(parent_id=parent.id, student_id=student_id).first():
        abort(403)
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)
    attendance = Attendance.query.filter_by(student_id=student_id).order_by(Attendance.attendance_date.desc()).all()
    present = sum(1 for a in attendance if (a.status or '').lower() in ('present','p'))
    marks = Mark.query.filter_by(student_id=student_id).order_by(Mark.id.desc()).all()
    subjects = {s.id:s.name for s in Subject.query.all()}
    exams = {e.id:e.name for e in Exam.query.all()}
    results = [{'exam':exams.get(m.exam_id,'Exam'),'subject':subjects.get(m.subject_id,'Subject'),'score':m.marks_obtained,'max':m.maximum_marks,'absent':m.absent} for m in marks]
    payments = FeePayment.query.filter_by(student_id=student_id).order_by(FeePayment.id.desc()).all()
    return render_template('parent/child_progress.html',student=student,attendance=attendance,present=present,results=results,payments=payments)
'''
html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Child Progress - EduNova</title><link rel="stylesheet" href="{{ url_for('static',filename='css/admin.css') }}"><link rel="stylesheet" href="{{ url_for('static',filename='css/portal.css') }}"><style>main{max-width:1100px;margin:30px auto;padding:20px}.panel{background:white;border-radius:12px;padding:22px;margin:20px 0;overflow:auto}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}</style></head><body><main><a href="{{ url_for('parent_dashboard') }}">← Parent Dashboard</a><h1>{{ student.name }} — School Progress</h1><div class="panel"><h2>Attendance</h2><p><strong>{{ ((present * 100 / attendance|length)|round(1)) ~ '%' if attendance else 'No attendance records' }}</strong> — {{ present }} present / {{ attendance|length }} recorded days</p></div><div class="panel"><h2>Exam Marks &amp; Performance</h2>{% if results %}<table><tr><th>Exam</th><th>Subject</th><th>Marks</th><th>Percentage</th></tr>{% for r in results %}<tr><td>{{ r.exam }}</td><td>{{ r.subject }}</td><td>{{ 'Absent' if r.absent else r.score|string ~ ' / ' ~ r.max|string }}</td><td>{{ ((100*r.score/r.max)|round(1)) ~ '%' if r.max and not r.absent else '—' }}</td></tr>{% endfor %}</table>{% else %}<p>No exam marks recorded.</p>{% endif %}</div><div class="panel"><h2>Attendance History</h2>{% if attendance %}<table><tr><th>Date</th><th>Status</th></tr>{% for a in attendance %}<tr><td>{{ a.attendance_date }}</td><td>{{ a.status }}</td></tr>{% endfor %}</table>{% else %}<p>No records.</p>{% endif %}</div><div class="panel"><h2>Fee Payment History</h2>{% if payments %}<table><tr><th>Receipt</th><th>Amount</th><th>Method</th><th>Status</th></tr>{% for p in payments %}<tr><td>{{ p.receipt_number or '—' }}</td><td>₹{{ p.amount }}</td><td>{{ p.payment_method }}</td><td>{{ p.payment_status }}</td></tr>{% endfor %}</table>{% else %}<p>No payments recorded.</p>{% endif %}</div></main></body></html>'''
code=app.read_text(encoding='utf-8'); old=dash.read_text(encoding='utf-8')
new=code if '# EDUNOVA_PARENT_ACADEMICS' in code else code+'\n'+route
ast.parse(new)
anchor='{% for item in children %}'
if anchor not in old and 'parent_child_progress' not in old: sys.exit('Dashboard template differs: no changes made')
newdash=old if 'parent_child_progress' in old else old.replace(anchor,anchor+'\n<p><a class="secondary-btn" href="{{ url_for(\'parent_child_progress\', student_id=item.student.id) }}">View Attendance, Exam Marks &amp; Fees</a></p>',1)
backup=base/('parent_academics_backup_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir()
shutil.copy2(app,backup/'app.py');shutil.copy2(dash,backup/'dashboard.html')
if target.exists():shutil.copy2(target,backup/'child_progress.html')
app.write_text(new,encoding='utf-8');dash.write_text(newdash,encoding='utf-8');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(html,encoding='utf-8')
print('Installed successfully. Backup:',backup,'\nRestart Flask, log in as parent, open Parent Dashboard.')
