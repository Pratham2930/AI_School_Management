EduNova Automatic Internal Transaction Reference

1. Extract ZIP.
2. Copy install.py into C:\Users\Admin1\Desktop\AI_School_Management
3. In CMD:
   cd /d "C:\Users\Admin1\Desktop\AI_School_Management"
   python install.py
4. Restart Flask with python app.py

The server creates a random, method-prefixed reference for every saved payment.
The reference field displays 'Generated automatically when payment is saved'.
This is NOT a bank UTR, payment gateway confirmation, or proof of payment.
UPI, card, and bank transfers still require external verification.
The installer backs up app.py and collect.html and aborts if the expected code is absent.
