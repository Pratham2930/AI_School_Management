# Private Windows deployment

This deployment guide is for a single trusted Windows server using the existing
SQLite database. It is not a recommendation to expose the app directly to the
public internet.

## Prepare the server

1. Copy the project to a persistent local disk and keep `instance\school.db`
   with the deployment. The instance directory also stores training uploads
   and model artifacts; protect it with Windows filesystem permissions and
   include required contents in backups. Include
   `instance\ml_training_state.json` in backups if you need to preserve the
   consumer's event-deduplication history and training counter.
2. Install a supported Python version, then install dependencies from the
   project directory:

   ```powershell
   py -3.12 -m venv venv
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Generate a unique signing key on the server:

   ```powershell
   .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Configure the output as the `SECRET_KEY` environment variable for the
   Windows account running the app. Do not put it in source control, a shared
   script, or a chat. Configure `APP_ENV=production` in that same process
   environment. Production startup fails if the key is missing or shorter
   than 32 characters.

## Start the services

Run the Kafka broker locally if the AI training worker is needed:

```powershell
docker compose up -d kafka
```

The broker port is bound to loopback, not exposed to the LAN. In a separate
service process, run the transactional outbox publisher:

```powershell
.\venv\Scripts\python.exe -m kafka_pipeline.outbox_worker
```

In another service process, run the school-events consumer:

```powershell
.\venv\Scripts\python.exe -m kafka_pipeline.consumer
```

Teacher-assignment changes and their outbox records are saved in the same
database transaction. The outbox worker publishes pending events and marks them
delivered only after Kafka acknowledges them. Run exactly one outbox worker
against SQLite to preserve queue order. The worker claims each row atomically
with an expiring database lease, so separate workers do not publish the same
active claim. Delivery uses at-least-once semantics: a crash after Kafka
accepts a message but before SQLite records that acknowledgement can cause a
redelivery with the same `event_id`. The school training-state handler persists
processed event IDs and skips duplicates.

The worker retries failed deliveries up to 10 attempts with exponential delay
(5 seconds doubling to a maximum of one hour). Exhausted events remain visible
at **Admin → Kafka Outbox**. An administrator can inspect the event type,
entity ID, attempts, and last error, then explicitly retry an exhausted event.
The event payload is not displayed in that page. Start Flask/Waitress first so
its additive startup migration is complete, then start the outbox worker.

This consumer processes `school.data.events`. Teacher-assignment create and
delete events are counted as timetable-training-relevant events; the current
training-state handler sets a retraining-required flag after its configured
threshold, but does not itself train a timetable model.

The student-progress training workflow uses a separate topic and consumer.
Run its worker independently when that workflow is needed:

```powershell
.\venv\Scripts\python.exe -m ai.student_training_worker
```

For administrator-approved school-record imports, configure a Google service
account with read-only Sheets access using `GOOGLE_APPLICATION_CREDENTIALS`,
then share the source sheet with that account as a Viewer. **Admin → Google
Sheets Sync** creates a private preview for admissions, teachers, and staff;
an administrator must explicitly approve each batch. Read the required sheet
headers, stable-ID matching, and teacher credential delivery behavior in
`ai/README.md` before importing. Do not place service-account keys in the
project or sheet data in Kafka.

For automatic exports after an admin or super-admin creates an admission or
teacher account, share two destination spreadsheets with the same service
account as an Editor and set `GOOGLE_SHEETS_ADMISSIONS_SPREADSHEET_ID` and
`GOOGLE_SHEETS_TEACHERS_SPREADSHEET_ID` in both the app and worker process
environments. The worker creates the `Admissions` and `Teachers` tabs and
headers on empty tabs; existing tabs must use the exact headers documented in
`ai/README.md`. Start one worker from the project directory:

```powershell
.\venv\Scripts\python.exe .\google_sheets_export_worker.py
```

The queue entry is committed with each new school record. The worker retries
Sheets outages and is idempotent by admission number or employee ID. Monitor
queue status and last errors under **Admin → Google Sheets Sync**. It exports
new admissions and teacher registrations only; it does not bulk-export
existing records or mirror later edits.

## Power BI reporting exports

An administrator or super-administrator can open **Admin Dashboard → Power BI
Reporting Datasets** (`/admin/power-bi`) and download individual CSV datasets
or the multi-sheet Excel workbook. Exports are generated as read-only
snapshots from SQLite and do not require Microsoft credentials. Protect
downloaded files and share them only through a restricted organizational
Power BI workspace. These extracts use keyed pseudonymous entity keys and
exclude direct contact details, guardian information, exam answer text, event
payloads, and raw integration errors. Keep the Flask `SECRET_KEY` stable so
pseudonymous keys remain joinable between refreshes.

The app does not configure scheduled refresh, a Power BI tenant/workspace, or
report embedding. For scheduled refresh, provision a supported secure reporting
database and ingestion path, then configure the Microsoft tenant's credentials
and gateway/refresh policy. Use a private workspace and Microsoft Entra ID
authentication for any later report-sharing or embedding feature. Never use
Power BI Publish to web for school data. See `POWER_BI_REPORTING.md` for the
dataset dictionary and Power BI Desktop relationship setup.

Start the web app using Waitress, not Flask's development server:

```powershell
.\venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8080 wsgi:app
```

`wsgi.py` runs the existing SQLite compatibility migrations and creates any
new tables, including the Kafka outbox table, before serving. The outbox worker
also initializes the schema at startup. Run one web process and one outbox
worker at a time so startup migrations and event publishing do not race. Check
`http://127.0.0.1:8080/healthz`; it returns only whether the app can query its
database.

For LAN users, put IIS or another maintained reverse proxy in front of
Waitress, configure HTTPS and access controls there, and keep Waitress bound to
loopback. Do not expose port 8080 or the unauthenticated Kafka broker port
through the Windows firewall/router. If IIS terminates TLS, ensure it forwards
only trusted traffic to Waitress.

## Backups and operations

Use a scheduled, access-restricted backup location on a different disk. SQLite
supports a consistent online backup while the app is running:

```powershell
New-Item -ItemType Directory -Force .\backups | Out-Null
.\venv\Scripts\python.exe -c "import sqlite3; source=sqlite3.connect(r'instance\school.db'); target=sqlite3.connect(r'backups\school.db'); source.backup(target); target.close(); source.close()"
```

Test restoring a backup periodically. Back up the database together with any
model metadata/artifacts needed to reproduce the running AI feature. Protect
backups as student records. Do not commit the SQLite database, `.env` files,
service-account JSON keys, training datasets, or model artifacts.

The Flask development server is disabled by default. Set `FLASK_DEBUG=1` only
for local development; never use it in production. Keep Python packages and
the Windows host patched, use a dedicated least-privilege service account, and
monitor server and worker logs.

All HTML POST forms and the app's JSON POST requests require CSRF tokens.

## Current boundaries

This setup provides a private single-server baseline, not a complete internet
facing production deployment. The app still needs an organization-specific
security review, conversion of legacy GET logout links to POST actions, tested
restore/retention procedures, and a tested TLS/reverse-proxy configuration
before it is exposed beyond a trusted private network. SQLite and the
single-node unauthenticated local Kafka broker are not suitable for
multi-server scaling or untrusted network exposure.
