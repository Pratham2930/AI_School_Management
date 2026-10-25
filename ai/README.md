# Kafka-triggered student model training

The local school app trains two supervised models from administrator-approved
historical data uploaded as a CSV or read from a Google Sheet:

- pass/fail classification
- final-percentage regression

The model is not trained from fabricated, synthetic, or live student records. A
validated upload creates a training job in the school database and publishes a
small Kafka event containing the job ID and SHA-256 digest. The CSV itself is
stored under `instance/student_training_data` and is never sent to Kafka or an
external AI service. On successful training the worker removes that raw CSV.
Failed jobs retain the private CSV so an administrator can retry them.

## CSV contract

Download the blank header template from **Admin → Student Model Training**.
Use one student-term record per row and include:

- `student_id`: a stable, preferably pseudonymous ID; used only to keep a
  student's terms together in the holdout split, never as a model feature
- `attendance_percentage`: 0–100
- `average_marks`: 0–100, available before the outcome being predicted
- `final_percentage`: the labeled outcome, 0–100
- `pass_fail`: the labeled outcome, `pass`/`passed` or `fail`/`failed`

Optional numeric input features are `previous_average_marks`,
`assignment_completion_percentage`, `standard` (1–12), and `term_number`.
Percent features must be from 0–100; standard and term number must be whole
numbers in range. Leave unavailable optional features blank. Do not upload
names, contact details, or other unnecessary personal information.

Uploads require at least 50 labeled student-term records from 30 distinct
students and at least five distinct students for each pass/fail class. Training
and evaluation split on `student_id`, so records from one student do not appear
in both sets. Models are evaluated on a held-out set; the reported metrics are
not a guarantee of future accuracy and must not be the sole basis of a
high-stakes decision.

## Local setup (Windows PowerShell)

Install the project requirements after activating the virtual environment:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

With Docker Compose installed, start the single-node local Kafka broker from the
project root:

```powershell
docker compose up -d kafka
```

In another PowerShell window, run the Kafka training consumer from the project
root:

```powershell
.\venv\Scripts\python.exe -m ai.student_training_worker
```

Start the Flask app normally, then sign in as an administrator and open
`/admin/ai-training`. Upload an authorized CSV. The worker consumes the Kafka
event and publishes versioned model artifacts and the current model to
`instance/ai_models/`. Refresh the page to see job status and held-out metrics.
If Kafka was unavailable during an upload, start the broker and use **Retry**.

The defaults are `KAFKA_BOOTSTRAP_SERVERS=localhost:9092`,
`KAFKA_STUDENT_TRAINING_TOPIC=school.ml.student-progress.train`, and consumer
group `school-student-model-trainer`. Set environment variables before starting
both the Flask app and the worker when using different Kafka settings.

## Read-only Google Sheets import

The admin training page can import a specific sheet range into the same
validation and Kafka workflow as a CSV upload. This is a one-time, read-only
import; it does not synchronize changes back to Google Sheets or periodically
poll the sheet. The resulting validated CSV stays in the local private training
directory and the Kafka event contains only job metadata and the dataset hash.

1. In Google Cloud Console, select or create a project, enable the **Google
   Sheets API**, and create a service account.
2. Create a JSON key for that service account and store it outside the project
   directory with access restricted to the account running Flask. Never commit
   the key or paste it into the admin form.
3. In PowerShell, set the credential path in every shell used to start Flask:

   ```powershell
   $env:GOOGLE_APPLICATION_CREDENTIALS = "C:\secure\school-sheets-reader.json"
   ```

   Install the requirements in the project virtual environment if needed:

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Share the spreadsheet with the service account's `client_email` as a
   **Viewer**. The app requests only the read-only Sheets scope.
5. On **Admin → Student Model Training**, enter the spreadsheet ID (the part
   between `/d/` and `/edit` in its URL) and a bounded range such as
   `TrainingData!A1:I5000`. The first row must use the CSV contract's column
   names. The admin must confirm authorization; the same row-count and value
   checks as CSV uploads apply.

Google Sheets credentials, service-account key files, and sheet row contents
must not be placed in Kafka messages. The sheet is read server-side and
validated before a local training job is created. A working Google Cloud
service account, enabled API, network access, and a running Kafka broker and
worker are required for a complete import-and-train run.

## Approved school-record imports

Administrators can open **Admin → Google Sheets Sync** to preview and approve
read-only imports for admissions, teachers, and non-teaching staff. This is a
separate workflow from model-training uploads. It uses the same
`GOOGLE_APPLICATION_CREDENTIALS` service account with the read-only Sheets
scope described above; Viewer access is sufficient for import-only use. When
using that account for automatic exports too, give it Editor access to the
export destination spreadsheets.

Each sheet range must include a header row, use a stable `admission_number` or
`employee_id`, and contain only the columns documented on the import page.
Admissions also require `current_standard`, `division`, `academic_year`,
`previous_percentage`, `guardian_name`, and `guardian_relationship`; for
Standards 11–12, include `stream`. The class/division must already exist and
have room. Teacher rows require `employee_id`, `name`, `email`, and `phone`;
new teacher accounts receive generated temporary credentials through the
configured school email/SMS services. Staff rows require `employee_id`,
`name`, and `position`. Previews are limited to 2,000 rows.

The preview validates stable-ID duplicates, record fields, and matching school
classes. Nothing changes until an administrator explicitly confirms approval.
Approval revalidates the rows and commits the complete batch, its import
history, and Kafka outbox events in one database transaction. Existing records
are matched only by their stable IDs; omitted optional values do not erase
existing data, payment/admission status is not overwritten, and records
missing from a sheet are never deleted. Preview values and batch history are
stored in the private school database, so protect and back it up as student and
staff data. Correct invalid rows in the source sheet and create a fresh preview
before approval.

Configure the same Sheets read-only credentials and network access as for the
training import. A running Kafka broker is not required to approve a school
record batch: the outbox retains its metadata-only change events until the
publisher is available. Never put service-account keys or sensitive row
contents in Kafka messages.

## Automatic export of admin-entered admissions and teachers

When an administrator or super-administrator creates an admission or registers
a teacher in the app, the school record and a private export-queue entry are
committed together. A separate worker writes the row to Google Sheets and
updates an existing row with the same stable ID instead of duplicating it.
The export contains school/admission or teacher profile fields, but never
account passwords or login credentials. Failed writes stay in the local queue
and retry with backoff; check **Admin → Google Sheets Sync** for export status.
Existing records are not bulk-uploaded, and later edits to existing records
are not mirrored by this create-time export.

Configure two Google spreadsheets using the app's service account:

1. Enable the Google Sheets API and use the service-account JSON already
   configured with `GOOGLE_APPLICATION_CREDENTIALS`. Keep that file outside
   the project and restrict access to the app's Windows service account.
2. Share the admissions spreadsheet and the teachers spreadsheet with the
   service account's `client_email` as an **Editor**.
3. Set both spreadsheet IDs in the environment of the app and worker:

   ```powershell
   $env:GOOGLE_SHEETS_ADMISSIONS_SPREADSHEET_ID = "admissions-spreadsheet-id"
   $env:GOOGLE_SHEETS_TEACHERS_SPREADSHEET_ID = "teachers-spreadsheet-id"
   ```

   Use the ID from each spreadsheet URL (between `/d/` and `/edit`). The worker
   creates `Admissions` and `Teachers` tabs if they are missing and writes the
   exact header row on an empty tab. If a tab already has data, its first row
   must match the appropriate header row exactly and in the same order:

   - Admissions: `admission_number, name, current_standard, division, academic_year, previous_percentage, guardian_name, guardian_relationship, stream, date_of_birth, gender, phone, email, address, previous_school, previous_standard, admission_fee, guardian_phone, guardian_email`
   - Teachers: `employee_id, name, email, phone, qualification`

4. Start the Flask app once to create the export queue table, then start one
   export worker from the project directory:

   ```powershell
   .\venv\Scripts\python.exe .\google_sheets_export_worker.py
   ```

The worker uses the full Sheets API scope to read stable IDs and update or
append rows. Keep the service-account key private and protect the destination
spreadsheets because they contain personal student, guardian, and staff data.
The read-only training/import flows remain separate from this export queue.

## Power BI privacy

The Admin-only Power BI extracts include selected model evaluation metrics and
a keyed pseudonymous training-job key. They exclude training source filenames,
uploader IDs, dataset hashes, and job messages.
