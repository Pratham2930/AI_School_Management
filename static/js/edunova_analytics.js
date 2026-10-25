(function(){
'use strict';
function init(){
  const node=document.getElementById('edna-data');if(!node)return;
  let d;try{d=JSON.parse(node.textContent)}catch(e){return}
  const count=(x)=>{const n=Number(x);return Number.isFinite(n)&&n>=0?n:0};
  const percent=(x)=>{const n=Number(x);return Number.isFinite(n)?Math.max(0,Math.min(100,n)):null};
  const values=[['Students',count(d.students)],['Teachers',count(d.teachers)],['Parents',count(d.parents)],['Staff',count(d.staff)]];
  const max=Math.max(1,...values.map(x=>x[1]));
  const bars=document.getElementById('edna-bars');
  values.forEach(([label,value])=>{
    const row=document.createElement('div');row.className='edna-bar-row';
    const caption=document.createElement('div');caption.className='edna-bar-label';
    const name=document.createElement('span');name.textContent=label;
    const num=document.createElement('strong');num.textContent=value.toLocaleString();caption.append(name,num);
    const track=document.createElement('div');track.className='edna-bar-track';
    const fill=document.createElement('div');fill.className='edna-bar-fill';fill.style.width=(100*value/max)+'%';track.append(fill);row.append(caption,track);bars.append(row);
  });
  const score=percent(d.score);document.getElementById('edna-ring').style.setProperty('--score',(score??0)+'%');
  document.getElementById('edna-score').textContent=score===null?'—':String(score);
  for(const [key,id] of [['attendance','edna-attendance'],['academic','edna-academic']]){const v=percent(d[key]);document.getElementById(id).textContent=v===null?'—':v+'%'}
  document.getElementById('edna-status').textContent=d.status==null?'Not available':String(d.status);
  document.getElementById('edna-structure').textContent=count(d.classes).toLocaleString()+' classes · '+count(d.subjects).toLocaleString()+' subjects';
  document.getElementById('edna-export').addEventListener('click',()=>{
    const rows=[['Metric','Value'],...values,['Classes',count(d.classes)],['Subjects',count(d.subjects)],['School health score',score??''],['Attendance (%)',percent(d.attendance)??''],['Academic performance (%)',percent(d.academic)??''],['School health status',d.status??'']];
    const csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\r\n');
    const blob=new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='edunova-school-overview.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
