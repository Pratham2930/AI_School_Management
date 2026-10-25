from pathlib import Path
import shutil, datetime, sys
root=Path(__file__).resolve().parent
app=root/'app.py'; template=root/'templates/fees/collect.html'
if not app.exists() or not template.exists():
    sys.exit('Place this installer in your project root beside app.py, then run it.')
code=app.read_text(encoding='utf-8'); html=template.read_text(encoding='utf-8')
if 'def fees_upi_qr(' not in code:
    marker='@app.route("/fees/collect", methods=["GET", "POST"])'
    if marker not in code: sys.exit('Cannot find the expected fees route; no files changed.')
    route='''@app.route("/fees/upi-qr/<int:student_id>", methods=["GET"])
@login_required
@fees_room_required
def fees_upi_qr(student_id):
    """Display a payment request; never treat a QR scan as proof of payment."""
    import base64
    from urllib.parse import urlencode
    try:
        import qrcode
    except ImportError:
        abort(503, description="Install QR support: pip install qrcode[pil]")
    student = db.get_or_404(Student, student_id)
    if student.admission_status != "Pending":
        abort(400, description="Only pending admissions can generate payment QR codes.")
    amount = Decimal(str(student.admission_fee or 0)).quantize(Decimal("0.01"))
    if amount <= 0:
        abort(400, description="Set the admission fee before generating a QR code.")
    upi_id = os.environ.get("SCHOOL_UPI_ID", "").strip()
    payee = os.environ.get("SCHOOL_UPI_NAME", "").strip()
    if not upi_id or not payee or not re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9._-]+", upi_id):
        abort(503, description="Configure SCHOOL_UPI_ID and SCHOOL_UPI_NAME on the server.")
    note = f"Admission fee {student.admission_number}"[:80]
    payload = "upi://pay?" + urlencode({"pa": upi_id, "pn": payee, "am": format(amount, ".2f"), "cu": "INR", "tn": note})
    image = qrcode.make(payload)
    output = io.BytesIO()
    image.save(output, format="PNG")
    qr = base64.b64encode(output.getvalue()).decode("ascii")
    return render_template("fees/upi_qr.html", student=student, amount=amount, payee=payee, upi_id=upi_id, qr=qr, upi_uri=payload)


'''
    code=code.replace(marker,route+marker,1)
if 'id="upi-qr-preview"' not in html:
    # Add a second GET form rather than altering the existing payment-recording POST flow.
    insertion='''<section class="card" id="upi-qr-preview"><h2>UPI QR payment request</h2><p>Select a student and UPI as the payment method above, then click Generate QR. The QR requests the student's actual admission fee automatically. Scanning is not payment confirmation.</p><button type="button" id="show-upi-qr">Generate UPI QR</button><p id="upi-qr-error" role="alert"></p></section>
<script>
(function(){
 const student=document.querySelector('select[name="admission_number"]');
 const method=document.querySelector('select[name="payment_method"]');
 const btn=document.getElementById('show-upi-qr');
 const err=document.getElementById('upi-qr-error');
 const records=__STUDENT_IDS__;
 btn.addEventListener('click',function(){
   err.textContent='';
   if(!student || !student.value || !method || method.value!=='UPI'){
     err.textContent='Choose a student and select UPI first.';return;
   }
   const id=records[student.value];
   if(!id){err.textContent='Student not found.';return;}
   window.location.href='/fees/upi-qr/'+encodeURIComponent(id);
 });
})();
</script>'''
    insertion=insertion.replace('__STUDENT_IDS__','{{ students | tojson_student_ids }}') if False else insertion.replace('__STUDENT_IDS__','{ {% for s in students %}{{ s.admission_number|tojson }}: {{ s.id|tojson }}{% if not loop.last %},{% endif %}{% endfor %} }')
    html=html.replace('</main>',insertion+'</main>',1)
qr_template=root/'templates/fees/upi_qr.html'
qr_html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UPI Fee QR | EduNova</title><link rel="stylesheet" href="{{ url_for('static',filename='css/fees.css') }}"><style>.qr-card{text-align:center;max-width:650px;margin:3rem auto}.qr-card img{max-width:300px;width:100%;height:auto}.amount{font-size:2.2rem;font-weight:800}.warn{padding:1rem;border:1px solid #d6a347;border-radius:8px;margin:1rem 0}</style></head><body><main class="wrap"><section class="card qr-card"><h1>Scan to pay school fees</h1><p>{{ student.name }} · {{ student.admission_number }}</p><p class="amount">₹{{ '%.2f'|format(amount) }}</p><img src="data:image/png;base64,{{ qr }}" alt="UPI QR payment request for ₹{{ amount }}"><p>Payee: <strong>{{ payee }}</strong></p><p>UPI ID: <strong>{{ upi_id }}</strong></p><p>Compatible UPI apps should prefill ₹{{ amount }}. Please verify the payee and amount before authorizing.</p><p><a href="{{ upi_uri }}">Open in UPI app (on phone)</a></p><div class="warn"><strong>Payment pending verification.</strong> Scanning or opening this QR does not confirm payment. Collect a transaction reference and independently verify receipt in the school's bank or payment gateway before recording/approving fees.</div><a href="{{ url_for('fees_collect') }}">Back to Fees Room</a></section></main></body></html>'''
changes=[]
if code!=app.read_text(encoding='utf-8'): changes.append((app,code))
if html!=template.read_text(encoding='utf-8'): changes.append((template,html))
if not qr_template.exists(): changes.append((qr_template,qr_html))
for path,content in changes:
    if path.exists():
        stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(path,path.with_name(path.name+'.bak_'+stamp))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content,encoding='utf-8')
print('UPI QR installed; changed',len(changes),'files. No database changes.')
print('Set SCHOOL_UPI_ID and SCHOOL_UPI_NAME, install qrcode[pil], then restart Flask.')
