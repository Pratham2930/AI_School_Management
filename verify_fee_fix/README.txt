EDUNOVA VERIFY FEES BLANK PAGE RESTORE

Cause: templates/admin/fee_verify.html is 0 bytes, so Flask returns an empty 200 response.

1. Extract this ZIP to a folder, e.g. Downloads\verify_fee_fix.
2. Open CMD:
   cd /d "C:\Users\Admin1\Desktop\AI_School_Management"
   python "C:\Users\Admin1\Downloads\verify_fee_fix\install_fix.py"
   (adjust the extracted path if needed)
3. Restart Flask: python app.py
4. Visit http://127.0.0.1:5000/admin/fees/verify and press Ctrl+F5.

The installer backs up the existing template and replaces only templates/admin/fee_verify.html.
No database or payment records are changed.
The restored page searches receipts and offers existing confirmation flow when applicable.
Verify actual payments independently before confirming admission; UPI QR scans are not payment proof.
