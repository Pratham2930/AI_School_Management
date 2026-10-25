from pathlib import Path
import shutil, datetime
p=Path(__file__).resolve().parent
root=Path.cwd(); app=root/'app.py'; html=root/'templates/fees/collect.html'
if not app.exists() or not html.exists():
    raise SystemExit('Run this installer from the AI_School_Management project folder.')
a=app.read_text(encoding='utf-8'); t=html.read_text(encoding='utf-8')
if 'EDUNOVA_AUTO_REFERENCE_V1' in a:
    print('Already installed.'); raise SystemExit(0)
needle='''        if method != "Cash" and not reference:
            flash(
                "Transaction reference is required "
                "for non-cash payments."
            )
            return redirect(url_for("fees_collect"))

        if len(reference) > 100:
            flash("Transaction reference is too long.")
            return redirect(url_for("fees_collect"))'''
if needle not in a or 'payments=payments\n    )' not in a or 'id="transaction_reference"' not in t:
    raise SystemExit('Project code differs from expected version; no files changed. Share app.py fees_collect route for a tailored patch.')
new='''        # EDUNOVA_AUTO_REFERENCE_V1: internal reference, not a bank UTR.
        import secrets
        prefix = {"Cash": "CASH", "UPI": "UPI", "Card": "CARD", "Bank Transfer": "BANK"}[method]
        # Always create the final reference on the server; never trust browser input.
        reference = f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(10).upper()}"
'''
# datetime may be imported as module or class; use local alias instead.
new=new.replace('import secrets','import secrets\n        from datetime import datetime as _ref_datetime').replace('datetime.now()', '_ref_datetime.now()')
a=a.replace(needle,new,1)
a=a.replace('''        payments=payments
    )''','''        payments=payments
    )''',1)
# Server generates final reference, browser displays a descriptive placeholder until submission.
old='''                   maxlength="100"
                   placeholder="Required for non-cash payments">'''
if old not in t: raise SystemExit('Template differs; no changes made.')
t=t.replace(old,'''                   maxlength="100"
                   readonly
                   value="Generated automatically when payment is saved"
                   aria-describedby="ref_help">
            <small id="ref_help">EduNova generates a unique internal reference for every payment method. For UPI, card, or bank transfer, separately verify the actual bank transaction before marking the payment verified.</small>''',1)
backup=root/('edunova_auto_reference_backup_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(); shutil.copy2(app,backup/'app.py'); shutil.copy2(html,backup/'collect.html')
app.write_text(a,encoding='utf-8'); html.write_text(t,encoding='utf-8')
print('Installed. Backups:',backup)
print('Restart Flask, then submit a test payment. The saved receipt has the actual generated reference.')
