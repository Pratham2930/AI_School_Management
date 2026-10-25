# AI School Management System — Project Audit

**Audit date:** 2026-10-09  
**Scope:** The initial audit was read-only across the existing Flask
application, its routes and models, SQLite schema, templates/assets, Kafka and
ML modules, Google Sheets integration, and deployment configuration.
Subsequent phased implementation changes are recorded below. This is not a
penetration test or a claim of production certification.

## Executive summary

The existing project is a functioning, feature-rich Flask monolith with
administrator, super-administrator, teacher, student, and parent workflows.
It already has admissions, staff, leave requests, attendance, exams, homework,
curriculum, AI timetable drafts, a transactional Kafka outbox, and student
progress model training. Preserve the current application and database.

The highest-priority remaining work is operational reliability rather than a
rewrite: strengthen CP-SAT constraints for rooms and blocked periods, and test
legacy route behavior in an isolated test database. Outbox concurrency/retries
and recovery visibility have been addressed. Google Sheets supports
read-only training-data import, preview/approval for school-record imports,
and a durable automatic export queue for new admissions and teacher
registrations. Live Google API access still requires credentials and IDs.

## Existing features verified

- `app.py` defines the account and school data models, role checks, and **105
  registered Flask routes** after the phased additions. The five existing
  roles are admin, super-admin, teacher, student, and parent.
- There are **56 Jinja templates** and shared administrator/portal CSS.
- Existing routes and screens cover class/division and Standards 1–12
  curriculum setup, admissions and payment confirmation, teacher assignment,
  staff management, leave requests and review, attendance, marks and exams,
  homework/submissions, notices/events, reports, and role dashboards.
- Teacher leave uses the existing `LeaveRequest` model with date ranges and
  Pending/Approved/Rejected status. Dashboards indicate approved leave during
  the affected dates. Teacher approvals now stage
  `teacher.availability.updated` in the same transaction; scheduling has not
  yet consumed these date ranges as a hard constraint, per the user's decision
  to keep timetable generation unchanged.
- Timetable generation uses OR-Tools CP-SAT and saves generated schedules as
  reviewable drafts before administrator publication. Manual create/delete,
  draft publication, and teacher assignment now write outbox events inside
  their database transactions.
- Kafka uses `school.data.events` at `127.0.0.1:9092`. The outbox publisher
  retains event IDs, waits for delivery confirmation, and leaves unacknowledged
  events pending. The training-state consumer persists processed event IDs to
  suppress replays.
- Student progress models support pass/fail classification and final-score
  regression from validated CSV data. A read-only Google Sheets range can be
  imported into this same training workflow. A separate admin-only Sheets
  workflow now previews and validates admissions, teacher, and staff rows
  before explicit approval; it records import history and queues metadata-only
  Kafka events in the same transaction as record changes.
- A private Windows deployment baseline, Waitress entry point, CSRF protection,
  production secret-key checks, health endpoint, and loopback Kafka binding are
  present.
- New manual admissions and teacher registrations queue Google Sheets exports
  in the same SQLite transaction. The separate worker upserts by stable ID,
  retries failures, and exposes queue status on the admin Sheets page. Actual
  Google delivery requires two spreadsheet IDs and service-account Editor
  access; it has not been live-tested.
- After the initial audit, the outbox was extended with atomic expiring claims,
  bounded retries, administrator recovery, and an administrator event-status
  page. See the Phase 2 update below.

## Database and safety baseline

- The pre-change audit database contained **30 tables**; it now contains **33**
  after adding Sheets batch/row history and export-queue tables. Existing
  records include students, teachers, staff, classes, assignments, leave,
  timetable periods, curriculum, exams, and training jobs. The audit did not
  read or disclose personal row contents.
- The database was backed up with SQLite's online backup API before audit work
  to `instance/backups/school-before-project-audit-20261009-104141.db`; the
  backup passed `PRAGMA quick_check`.
- `app.py` was copied to
  `instance/backups/app-before-project-audit.py` and the copy's SHA-256 was
  verified against the source.
- At initial audit time, live and backup table sets and row counts matched;
  both passed integrity checks and `PRAGMA foreign_key_check`. Subsequent
  migrations added outbox fields and two new empty Sheets tables. Comparing
  the current database with the backup confirms every original row count is
  unchanged.
- Phase 2 then added `next_attempt_at`, `claim_token`, `claim_expires_at`, and
  `failed_at` to the existing outbox table using a repeatable additive SQLite
  migration, plus an outbox dispatch index. Existing outbox rows and school
  records were preserved.
- Phase 4 added two empty Google Sheets sync-history tables through the
  existing `db.create_all()` startup path. The migration is repeatable and
  did not change any pre-existing table or row count.

## Findings and prioritized risks

### P1 — Kafka outbox reliability controls (addressed in Phase 2)

At initial audit time, outbox publication selected pending rows without a
claim, had no bounded retry/backoff, and had no administrator recovery page.
Phase 2 has since addressed these points with an atomic row update and expiring
lease, ten bounded delivery attempts with exponential retry delay, failed
event visibility/retry for administrators, and handling for a worker that
expires on its final attempt. Stable event IDs and consumer deduplication
preserve at-least-once delivery semantics.

The SQLite deployment should still run one outbox worker to preserve event
ordering. Delivery acknowledgement can be lost after Kafka accepts a message,
so stable-ID deduplication remains necessary. Processed event IDs are stored in
a JSON file and currently have no retention policy.

### P2 — Teacher leave is intentionally dashboard-only for scheduling

Leave requests can be submitted and approved, but the CP-SAT generator's
teacher candidates and constraints do not check approved leave dates. The user
confirmed that approved leave should continue to appear on teacher/admin
dashboards and should not change timetable generation. The leave-review route
queues `teacher.availability.updated` transactionally when a teacher request
is approved; student approvals and rejected requests do not generate this
event.

Recurring weekly availability is not implemented and is not part of the
confirmed scheduling behavior.

### P1 — Timetable optimization does not enforce all specified hard constraints

Verified generator constraints cover required subject-period totals, one
subject per class slot, a per-subject daily maximum, external teacher
occupancy, and a teacher not teaching two subjects in the same class slot.
School days, period times, and breaks are hard-coded. The generator does not
check room capacity/availability or configurable blocked periods/operating
hours. Approved leave is intentionally not a timetable constraint. Manual
entry now rejects overlapping use of a room name; AI publication revalidates
weekly requirements, active assigned teachers, canonical slots, teacher
conflicts, and named-room overlaps before replacing the live timetable. The
solver leaves rooms unassigned, and no room inventory or capacity model exists.

Soft optimization currently rewards morning/afternoon preferences. Workload
balance, subject spacing, teacher gaps, consecutive teaching limits, and
minimum disruption are not optimized. The quality score is a simple
completeness/preference calculation, not an ML accuracy measure.

**Priority:** Add missing hard constraints before adding soft objectives;
introduce room inventory/capacity and configurable blocked periods only if
required by school policy, and share those rules across manual schedules,
generated drafts, and publication.

### P1 — Legacy SQLite migrations and multi-process startup need discipline

`initialize_database()` runs handwritten SQLite migrations and
`db.create_all()`. There is no versioned migration framework. Some migration
functions use a fixed `instance/school.db` path. This is additive for the
fields currently handled, but future model changes need explicit repeatable
migrations and a verified backup. Do not run multiple web processes that race
startup migrations on SQLite.

**Priority:** Add migration version tracking and isolated migration tests
before changing existing columns or adding indexes/constraints.

### P2 — Google Sheets integrations require configuration and live validation

Training and approved school-record imports remain read-only and explicit.
New manual admissions and teacher registrations are queued for one-way export
to separate spreadsheets, with stable-ID upserts and automatic retries. The
export worker requires write-scoped service-account credentials, Editor
sharing, and two spreadsheet IDs. No IDs or credentials were configured during
this audit, so neither import nor export has been tested against Google.

**Priority:** Configure authorized test spreadsheets and exercise read,
write, retry, and stable-ID update paths before relying on cloud copies.

### P2 — Automated regression coverage remains incomplete

The project now has isolated SQLite tests for outbox claims, delivery, and
failure recovery, plus mocked teacher leave-event transaction tests.
Authentication, role authorization, general legacy route behavior, and
timetable rollback coverage remain incomplete. The local school database is
not a safe test database.

**Priority:** Establish an isolated SQLite test database and begin with auth,
role authorization, timetable conflict, and publish rollback tests.

### P2 — ML scope and available data are limited

The implemented supervised models predict student pass/fail and final
percentage, not teacher workload or timetable quality. Model validation uses
student-grouped holdout evaluation and versioned artifacts, but local student
history is too small for meaningful training. Empty `ml/evaluate.py`,
`ml/model_manager.py`, and `ml/train.py` files are placeholders, not working
capabilities.

**Priority:** Do not train or claim model performance until sufficient
authorized real data is available. Keep the OR-Tools solver authoritative for
hard constraints.

### P2 — Deployment and observability remain single-server/private-network

Kafka is a single local broker without authentication/TLS, SQLite is
single-host storage, and deployment guidance expects one web process and one
outbox worker. The Kafka outbox has an administrator status/retry page, but
broader health, synchronization, and model observability remain limited. HTTPS
proxy configuration, service supervision, log rotation, restore drills, and
organization-specific security review remain deployment tasks.

**Priority:** Keep this setup private. Add monitoring and service recovery
before relying on it operationally; move to managed database and secured
broker before multi-host/public deployment.

### P3 — Documentation and code organization

There is no root `README.md` or `docs/` directory. Deployment and student-model
setup guidance are in `DEPLOYMENT.md` and `ai/README.md`. The application is a
large `app.py`; the `ml/` files are currently empty. An older
`app_backup_before_outbox.py` is present at the project root and can be
mistaken for the active application.

**Priority:** Consolidate operator-facing documentation and label/archive the
old backup after confirming it is not referenced. Refactor only behind tests;
do not replace the monolith wholesale.

## Verification performed

- Created and verified the application and SQLite backups described above.
- Python compilation passed for `app.py`, `wsgi.py`, and Kafka modules during
  the current work.
- Imported the WSGI app; `/healthz` returned 200 and login rendered. Unauthenticated
  protected admin, teacher, student, parent, AI-training, and timetable
  requests redirected to login.
- Authenticated Admin → Kafka Outbox returned 200 and rendered the monitoring
  page; Admin → Google Sheets Sync also returned 200. The live database passed
  `PRAGMA integrity_check`; foreign-key check returned no violations; every
  original table row count matches the pre-audit backup.
- Re-running `initialize_database()` preserved original row counts, retained the
  outbox retry/lease columns and dispatch index, retained the sync tables, and
  passed integrity and foreign-key checks.
- Earlier isolated/mocked checks covered outbox create/delete/publish
  transaction ordering, Kafka publish success/failure handling, stable IDs,
  replay deduplication, and timetable event payloads.
- `python -m unittest discover -s tests -v` passes all 31 tests. Coverage
  includes outbox claims/delivery/recovery, teacher leave approval/rejection/
  rollback, Google Sheets validation and approval with outbox staging, CP-SAT
  timetable generation and assignment/room revalidation, and Sheets export
  queue/upsert/retry plus API update/append request construction.
- A fresh WSGI process returned HTTP 200 for `/healthz` and `/login`; an
  unauthenticated Admin Google Sheets page redirected to login (HTTP 302).
  The existing Waitress service on port 8080 remained running.
  Kafka was not live-testable in this environment: Docker Desktop's engine was
  unavailable and `127.0.0.1:9092` refused connections. Google Sheets was not
  live-testable because the two spreadsheet IDs and service-account
  credentials were not configured.
- No real teacher assignment, timetable, sheet import, or model training was
  performed as part of this audit.

## Implementation order

1. **Phase 1 — Audit and stabilization:** baseline backup, startup, schema,
   health, route smoke checks, and this report. Completed for this audit
   baseline.
2. **Phase 2 — Kafka reliability:** worker claim/lease, retries/backoff,
   exhausted-event recovery, delivery and replay tests. Completed for the
   single-host SQLite configuration.
3. **Phase 3 — Teacher availability:** approved teacher leave events commit
   transactionally with leave status; dashboard indications remain the only
   scheduling effect, as confirmed by the user. Completed for that scope.
4. **Phase 4 — Google Sheets:** admin preview/history and explicit approval
   for admissions, teachers, and staff using stable IDs, plus queued stable-ID
   exports after manual admission/teacher creation. Isolated tests passed;
   live service-account/sheet validation remains.
5. **Phase 5 — Timetable quality:** publication revalidates current weekly
   requirements, assignments, teacher status, schedule slots, teacher overlap,
   and named-room overlap; manual entry rejects room overlap. Room inventory/
   capacity and configurable constraints remain open.
6. **Phase 6 — ML:** real-data readiness, event-driven training trigger,
   evaluated model versions, rollback, and admin visibility.
7. **Phase 7 — Admin operations:** outbox monitoring and retry are complete;
   availability, synchronization, and model status visibility remain open.
8. **Phase 8 — Tests and deployment:** isolated regression suite, restore
   drills, operational logging, and deployment review.
9. **Phase 9 — Power BI exports:** administrator-only CSV/Excel star-schema
   datasets, pseudonymous identifiers, data minimization, workbook formula
   protection, Desktop relationship guidance, and deployment setup notes.
   Six reporting-specific tests and all 31 project tests pass. Scheduled
   refresh and embedding remain unconfigured pending approved Microsoft and
   reporting-database infrastructure.

No destructive database operation or table recreation is authorized by this
report.
