from pathlib import Path
import re, ast, json, datetime
root=Path(__file__).resolve().parent
app=root/'app.py'
if not app.exists():
 print('ERROR: Place audit_launch.py in the same folder as app.py');raise SystemExit(1)
src=app.read_text(encoding='utf-8-sig',errors='replace')
try: tree=ast.parse(src)
except SyntaxError as e: print('app.py syntax error:',e);raise SystemExit(2)
endpoints=set();route_details=[]
for node in ast.walk(tree):
 if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
  for dec in node.decorator_list:
   if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr=='route':
    endpoints.add(node.name)
    route_details.append({'endpoint':node.name,'line':node.lineno})
problems=[];counts={'templates':0,'url_for':0,'buttons':0,'forms':0,'anchors':0}
for path in (root/'templates').rglob('*.html'):
 counts['templates']+=1; s=path.read_text(encoding='utf-8',errors='replace'); rel=str(path.relative_to(root))
 for m in re.finditer(r'''url_for\(\s*['"]([^'"]+)['"]''',s):
  counts['url_for']+=1; ep=m.group(1)
  if ep not in endpoints and ep!='static' and '.' not in ep:
   problems.append((rel,s.count('\n',0,m.start())+1,'UNRESOLVED_ENDPOINT',ep))
 for m in re.finditer(r'<a\b[^>]*>',s,re.I|re.S):
  counts['anchors']+=1; tag=m.group(0)
  if re.search(r'''href\s*=\s*['"]\s*(?:#|javascript:void\(0\)|javascript:;)\s*['"]''',tag,re.I):
   problems.append((rel,s.count('\n',0,m.start())+1,'PLACEHOLDER_LINK',tag[:130].replace('\n',' ')))
 for m in re.finditer(r'<button\b[^>]*>',s,re.I|re.S):
  counts['buttons']+=1; tag=m.group(0)
  if re.search(r'\bdisabled\b',tag,re.I):
   problems.append((rel,s.count('\n',0,m.start())+1,'DISABLED_BUTTON',tag[:130].replace('\n',' ')))
 for m in re.finditer(r'<form\b[^>]*>',s,re.I|re.S):
  counts['forms']+=1; tag=m.group(0)
  if not re.search(r'\bmethod\s*=',tag,re.I):
   problems.append((rel,s.count('\n',0,m.start())+1,'FORM_METHOD_IMPLICIT_GET',tag[:130].replace('\n',' ')))
  if re.search(r'''method\s*=\s*['"]post['"]''',tag,re.I) and not re.search(r'csrf_token|csrf',s,re.I):
   problems.append((rel,s.count('\n',0,m.start())+1,'CHECK_POST_CSRF',tag[:130].replace('\n',' ')))
if re.search(r'\bdebug\s*=\s*True\b',src): problems.append(('app.py',0,'DEBUG_ENABLED','Disable debug in production'))
if re.search(r'''SECRET_KEY\s*=\s*['"][^'"]+['"]''',src):problems.append(('app.py',0,'CHECK_SECRET_KEY','Ensure key is sourced from production environment'))
report=['EDUNOVA PRE-LAUNCH STATIC AUDIT','Generated: '+datetime.datetime.now().isoformat(timespec='seconds'),'Project: '+str(root),'',f'Routes: {len(route_details)} | Templates: {counts["templates"]} | Buttons: {counts["buttons"]} | Forms: {counts["forms"]} | Links: {counts["anchors"]}','', 'WARNING: Static checks cannot verify database operations, permissions, JavaScript behavior, payments, or runtime behavior.','']
report += [f'{typ} | {path}:{line} | {detail}' for path,line,typ,detail in problems]
report += ['','NEXT: manually test each role with a separate test account; verify CRUD, validation, permissions, uploads, payments, exports, backup/restore, error pages and HTTPS.','Do not go live until functional and security tests pass.']
out=root/'EDUNOVA_LAUNCH_AUDIT.txt';out.write_text('\n'.join(report),encoding='utf-8')
print('Audit complete:',len(problems),'items to review. Report:',out)
