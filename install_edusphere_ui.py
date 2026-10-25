from pathlib import Path
import re, shutil, sys, datetime

ROOT = Path(__file__).resolve().parent
T = ROOT/'templates'; S=ROOT/'static'
if not (ROOT/'app.py').exists() or not T.exists():
    sys.exit('ERROR: Put this script in your AI_School_Management folder next to app.py')

CSS = r'''/* EduSphere AI navigation: scoped to avoid breaking existing forms/layouts */
:root { --edu-navy:#0F172A; --edu-blue:#2563EB; }
#edu-menu-trigger { position:fixed;bottom:20px;left:20px;z-index:11000;display:flex;align-items:center;gap:9px;background:var(--edu-blue);color:white;border:0;border-radius:12px;padding:13px 18px;box-shadow:0 9px 24px #0f172a3b;font:600 14px system-ui, sans-serif;cursor:pointer; }
#edu-menu-overlay {position:fixed;inset:0;z-index:11001;background:#0f172a88;display:none}
#edu-menu-overlay.edu-open {display:block}
#edu-sidebar {position:fixed;left:0;top:0;bottom:0;width:min(310px,88vw);box-sizing:border-box;background:var(--edu-navy);color:#fff;z-index:11002;transform:translateX(-105%);visibility:hidden;transition:transform .22s ease,visibility .22s;overflow-y:auto;padding:18px 13px 30px;font:14px/1.45 system-ui,sans-serif;text-align:left;box-shadow:12px 0 40px #0002}
#edu-sidebar.edu-open {transform:translateX(0);visibility:visible}
#edu-sidebar *, #edu-sidebar *::before, #edu-sidebar *::after {box-sizing:border-box}
#edu-sidebar .edu-top {display:flex;justify-content:space-between;align-items:center;padding:10px 10px 20px;border-bottom:1px solid #334155}
#edu-sidebar .edu-brand {font-weight:750;font-size:21px;color:#fff}
#edu-sidebar .edu-brand small {display:block;font-size:11px;font-weight:400;color:#94a3b8;margin-top:4px}
#edu-sidebar .edu-close {background:none;border:0;color:white;font-size:26px;cursor:pointer}
#edu-sidebar .edu-heading {margin:21px 12px 7px;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8;font-weight:700}
#edu-sidebar a.edu-link {display:block;color:#cbd5e1;text-decoration:none;border-radius:9px;padding:10px 13px;margin:2px 0;font-size:14px;font-weight:500}
#edu-sidebar a.edu-link:hover,#edu-sidebar a.edu-link.edu-active {background:#1e293b;color:white}
#edu-sidebar a.edu-link.edu-active {box-shadow:inset 3px 0 var(--edu-blue)}
#edu-sidebar a.edu-link:focus-visible,#edu-menu-trigger:focus-visible,#edu-sidebar button:focus-visible {outline:3px solid #93c5fd;outline-offset:2px}
@media(max-width:650px){#edu-menu-trigger{left:12px;bottom:12px;padding:12px 14px}}
'''
JS = r'''(function(){'use strict';
function init(){const menu=document.getElementById('edu-sidebar'),overlay=document.getElementById('edu-menu-overlay'),trigger=document.getElementById('edu-menu-trigger'),close=document.getElementById('edu-menu-close');if(!menu||!overlay||!trigger||!close)return;
let lastFocus=null;
function setOpen(open){menu.classList.toggle('edu-open',open);overlay.classList.toggle('edu-open',open);menu.setAttribute('aria-hidden',String(!open));trigger.setAttribute('aria-expanded',String(open));if(open){lastFocus=document.activeElement;close.focus()}else if(lastFocus&&lastFocus.focus){lastFocus.focus()}}
trigger.addEventListener('click',()=>setOpen(true));close.addEventListener('click',()=>setOpen(false));overlay.addEventListener('click',()=>setOpen(false));document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menu.classList.contains('edu-open'))setOpen(false);if(e.key==='Tab'&&menu.classList.contains('edu-open')){const focusable=[...menu.querySelectorAll('a[href],button:not([disabled])')];if(!focusable.length)return;const first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}});
const path=window.location.pathname;menu.querySelectorAll('a.edu-link').forEach(a=>{if(a.pathname===path){a.classList.add('edu-active');a.setAttribute('aria-current','page')}});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();})();
'''
# Only GET-safe navigation targets; all endpoints verified against uploaded app.py.
MENUS={
'admin': [('Overview',[('Dashboard','admin_dashboard')]),('Students & Admissions',[('Students','admin_students'),('New Admission','new_admission'),('Admission Records','admission_records'),('Classes & Divisions','admin_classes'),('Parents','admin_parents')]),('Teachers & Staff',[('Teachers','admin_teachers'),('Add Teacher','add_teacher'),('Subjects','admin_subjects'),('Teacher Documents','admin_teacher_documents'),('Leave Requests','admin_leave_requests'),('Staff Management','admin_staff')]),('Academics',[('Exams','admin_exams'),('New Exam','admin_exam_new'),('Timetable','admin_timetable'),('Timetable Requirements','timetable_requirements'),('Curriculum Generator','curriculum_generator')]),('Finance',[('Collect Fees','fees_collect'),('Verify Payments','admin_fee_verify')]),('AI & Automation',[('AI Training','admin_ai_training'),('AI Subject Setup','ai_subject_setup'),('AI Assistant','school_ai_assistant')]),('Communication',[('Notices','admin_notices'),('Events','admin_events')]),('Data & Reports',[('Reports','admin_reports'),('Power BI','admin_powerbi_reports'),('Google Sheets','admin_google_sheets_sync'),('Kafka Outbox','admin_kafka_outbox')]),('Account',[('Log out','admin_logout')])],
 'teacher':[('Teacher Portal',[('Dashboard','teacher_dashboard'),('My Students','teacher_students'),('Attendance','teacher_attendance'),('Marks','teacher_marks'),('Homework','teacher_assignments'),('Online Exams','teacher_online_exams'),('Documents','teacher_documents'),('Leave Requests','leave_requests'),('AI Assistant','school_ai_assistant')]),('Account',[('Change Password','teacher_change_password'),('Log out','teacher_logout')])],
 'student':[('Student Portal',[('Dashboard','student_dashboard'),('My Profile','student_profile'),('Homework','student_assignments'),('Online Exams','student_online_exams'),('AI Assistant','school_ai_assistant')]),('Account',[('Change Password','student_change_password'),('Log out','student_logout')])],
 'parent':[('Parent Portal',[('Dashboard','parent_dashboard')]),('Account',[('Log out','parent_logout')])],
 'staff':[('Staff Portal',[('Dashboard','staff_dashboard'),('Collect Fees','fees_collect')])]
}
# Session keys and role enforcement remain with existing Flask routes. Portal selected from
# rendered page group, not from URL alone. Shared assistant/leave pages get an admin menu
# only if a role is unambiguously detected; otherwise no navigation is injected.
role_by_folder={'admin':'admin','teacher':'teacher','student':'student','parent':'parent','staff':'staff','fees':'staff'}

app_py=(ROOT/'app.py').read_text(encoding='utf-8',errors='replace')
endpoints=set(re.findall(r'^def\s+(\w+)\s*\(',app_py,re.M))
for role,groups in MENUS.items():
    for heading,links in groups:
        for label,endpoint in links:
            if endpoint not in endpoints: print('WARNING: Endpoint not found in app.py:',endpoint)

T.joinpath('components').mkdir(parents=True,exist_ok=True)
S.joinpath('css').mkdir(parents=True,exist_ok=True)
S.joinpath('js').mkdir(parents=True,exist_ok=True)
(S/'css'/'edusphere_navigation.css').write_text(CSS,encoding='utf-8')
(S/'js'/'edusphere_navigation.js').write_text(JS,encoding='utf-8')

for role,groups in MENUS.items():
    chunks=['<button id="edu-menu-trigger" type="button" aria-controls="edu-sidebar" aria-expanded="false">&#9776; School Menu</button>','<div id="edu-menu-overlay"></div>','<nav id="edu-sidebar" aria-label="School navigation" aria-hidden="true">','<div class="edu-top"><div class="edu-brand">EduSphere AI<small>School Management</small></div><button id="edu-menu-close" class="edu-close" type="button" aria-label="Close menu">&times;</button></div>']
    for heading,links in groups:
        chunks.append('<div class="edu-heading">'+heading+'</div>')
        for label,endpoint in links:
            chunks.append('<a class="edu-link" href="{{ url_for(\''+endpoint+'\') }}">'+label+'</a>')
    chunks.append('</nav>')
    (T/'components'/f'edu_{role}_sidebar.html').write_text('\n'.join(chunks)+'\n',encoding='utf-8')

backup=ROOT/'ui_backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
changed=[]; skipped=[]
for f in sorted(T.rglob('*.html')):
    if 'components' in f.parts: continue
    rel=f.relative_to(T)
    role=role_by_folder.get(rel.parts[0],None)
    if rel.name in {'setup.html','one_click_setup.html','receipt.html'}:
        skipped.append(str(rel));continue
    if role is None:
        skipped.append(str(rel));continue
    original=f.read_text(encoding='utf-8',errors='replace')
    if 'edusphere_navigation.css' in original or 'edu-'+role+'-sidebar' in original:
        continue
    # Full-page templates only. Fragment templates (e.g. fees/dashboard.html) are skipped.
    if not re.search(r'</head\s*>',original,re.I) or not re.search(r'</body\s*>',original,re.I):
        skipped.append(str(rel));continue
    css='\n    <!-- EduSphere shared navigation -->\n    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/edusphere_navigation.css\') }}">\n'
    body='\n    <!-- EduSphere role navigation -->\n    {% include "components/edu_'+role+'_sidebar.html" %}\n    <script src="{{ url_for(\'static\', filename=\'js/edusphere_navigation.js\') }}"></script>\n'
    updated=re.sub(r'</head\s*>',lambda m:css+m.group(0),original,count=1,flags=re.I)
    updated=re.sub(r'</body\s*>',lambda m:body+m.group(0),updated,count=1,flags=re.I)
    dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    f.write_text(updated,encoding='utf-8')
    changed.append(str(rel))
print('EduSphere UI installation complete.')
print('Updated templates:',len(changed))
print('Original templates backed up to:',backup)
print('Skipped (fragments, login or shared pages):',len(skipped))
print('No changes to app.py or databases.')
