from pathlib import Path
import ast, shutil, datetime, sys
base=Path(__file__).resolve().parent
appfile=base/"app.py"
leavefile=base/"templates/leave_requests.html"
ad=base/"templates/admin/dashboard.html"
td=base/"templates/teacher/dashboard.html"
needed=[appfile,leavefile,ad,td,base/"model.txt",base/"routes.txt",base/"class_teachers.html",base/"student_leaves.html"]
if any(not p.exists() for p in needed): sys.exit("Extract ALL ZIP files into project folder alongside app.py.")
s=appfile.read_text(encoding="utf8")
if "EDUNOVA_CLASS_TEACHER_ROUTES_V1" in s: sys.exit("Already installed.")
def once(src,old,new):
    if src.count(old)!=1: sys.exit("Unexpected app.py structure at: "+old[:70]+"; no changes made.")
    return src.replace(old,new,1)
s=once(s,"class TeacherAssignment(db.Model):",(base/"model.txt").read_text(encoding="utf8")+"\nclass TeacherAssignment(db.Model):")
s=once(s,'@app.route("/admin/leave-requests")',(base/"routes.txt").read_text(encoding="utf8")+'\n@app.route("/admin/leave-requests")')
s=once(s,'LeaveRequest.query\n        .order_by(\n            db.case(','LeaveRequest.query\n        .filter(LeaveRequest.requester_type == "teacher")\n        .order_by(\n            db.case(')
s=once(s,'    if leave_request.status != "Pending":\n        flash("Only pending leave requests can be reviewed.")','    if leave_request.requester_type != "teacher":\n        abort(403)\n    if leave_request.status != "Pending":\n        flash("Only pending leave requests can be reviewed.")')
s=once(s,'        leave_request = LeaveRequest(\n            requester_type=requester_type,','        if requester_type == "student" and ClassTeacherAssignment.query.filter_by(class_id=student.class_id).first() is None:\n            flash("No class teacher is assigned. Contact the school office.")\n            return redirect(url_for("leave_requests"))\n        leave_request = LeaveRequest(\n            requester_type=requester_type,')
s=once(s,'        flash("Your leave request was submitted for administrator review.")','        flash("Your leave request was submitted to your class teacher." if requester_type == "student" else "Your leave request was submitted for administrator review.")')
ast.parse(s)
lv=leavefile.read_text(encoding="utf8").replace("Review student and teacher applications. Approved teacher leave is highlighted for the dates it covers.","Review teacher leave requests. Student leave is reviewed by assigned class teachers.").replace("Requests are sent to the administrator for review.","{% if requester_type == \"student\" %}Requests are sent to your class teacher for review.{% else %}Requests are sent to the administrator for review.{% endif %}").replace("<th>Administrator Note</th>","<th>Reviewer Note</th>")
a=ad.read_text(encoding="utf8");t=td.read_text(encoding="utf8")
if "</body>" not in a or "</body>" not in t: sys.exit("Dashboard structure unexpected; no changes made.")
if "admin_class_teachers" not in a: a=a.replace("</body>",'<p style="text-align:center"><a href="{{ url_for(\'admin_class_teachers\') }}">Assign Class Teachers</a></p></body>',1)
if "teacher_student_leaves" not in t: t=t.replace("</body>",'<p style="text-align:center"><a href="{{ url_for(\'teacher_student_leaves\') }}">Review Student Leave Requests</a></p></body>',1)
stamp=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup=base/("backup_leave_routing_"+stamp);backup.mkdir()
for p in [appfile,leavefile,ad,td]:
    dest=backup/p.relative_to(base);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
appfile.write_text(s,encoding="utf8");leavefile.write_text(lv,encoding="utf8");ad.write_text(a,encoding="utf8");td.write_text(t,encoding="utf8")
for src,dest in [(base/"class_teachers.html",base/"templates/admin/class_teachers.html"),(base/"student_leaves.html",base/"templates/teacher/student_leaves.html")]:
    if dest.exists(): shutil.copy2(dest,backup/dest.name)
    shutil.copy2(src,dest)
print("SUCCESS. Backup:",backup)
print("Restart Flask. Admin: /admin/class-teachers  Teacher: /teacher/student-leaves")
