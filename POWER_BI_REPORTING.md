# Power BI reporting exports

## Current implementation

Administrators and super-administrators can open **Admin Dashboard → Power BI
Reporting Datasets** at `/admin/power-bi`. Downloads are generated from the
current SQLite data without writing to or migrating the school's records:

- `Download Excel workbook` creates one worksheet per dataset.
- Each dataset also has an individual CSV download.
- Requests require the existing administrator authentication and authorization
  decorators. Responses are marked confidential, `private`, and `no-store`.
- Direct student/teacher identifiers are replaced with keyed pseudonymous
  keys. Student names, admission and employee IDs, contact information,
  guardian fields, leave reasons, student exam answers, Kafka payloads and
  entity IDs, spreadsheet identifiers, and raw integration errors are not
  included.
- Spreadsheet-formula-like strings are escaped in CSV and Excel output.
- Exports are point-in-time snapshots. Downloading again refreshes the data.

Pseudonymous keys are HMACs using Flask's `SECRET_KEY`. Keep that key stable
across app restarts and deployments; rotating it changes the pseudonymous
keys, so existing Power BI relationships across refreshes will no longer
match. Production startup already requires a configured secret key.

## Star-schema model

Load all workbook sheets, or select the CSV datasets required for a report.
Use the indicated dimension keys to establish one-to-many relationships;
keep dimensions on the one side and facts on the many side. `date_key` is an
integer `YYYYMMDD` and joins to `dim_date.date_key`.

| Dataset | Grain / purpose | Relationship keys |
|---|---|---|
| `dim_date` | One row per date present in dated facts | `date_key` |
| `dim_class` | One row per school class/division, with active enrollment count | `class_key` |
| `dim_subject` | One row per subject | `subject_key` |
| `dim_student` | One row per student; keyed pseudonym only | `student_key`, `class_key` |
| `dim_teacher` | One row per teacher; keyed pseudonym only | `teacher_key` |
| `dim_staff` | One row per staff member; keyed pseudonym only | `staff_key` |
| `fact_admissions` | One row per student admission record | `student_key`, `class_key`, `date_key` |
| `fact_attendance` | One row per attendance mark | `student_key`, `class_key`, `teacher_key`, `date_key` |
| `fact_exam_results` | One row per traditional mark or online exam attempt | `student_key`, `class_key`, `subject_key`, `teacher_key`, `date_key` |
| `fact_teacher_assignments` | One row per teacher/class/subject assignment | `teacher_key`, `class_key`, `subject_key` |
| `fact_teacher_availability` | One row per approved teacher leave range | `teacher_key` |
| `fact_teacher_workload` | One row per teacher and Live/Draft state | `teacher_key` |
| `fact_timetable` | One row per live or current draft period | `class_key`, `teacher_key`, `subject_key` |
| `fact_timetable_conflicts` | One row per detected overlapping teacher/room pair | class and teacher keys for both sides |
| `fact_timetable_quality` | One row per current draft with solver completeness/preference scores | `draft_key`, `class_key` |
| `agg_google_sheets_sync` | Aggregated import counts by record type and batch status | none |
| `agg_google_sheets_exports` | Aggregated export-queue counts by record type and status | none |
| `agg_kafka_processing` | Aggregated outbox counts by event type and status | none |
| `fact_ml_training` | One row per training job, with allow-listed metrics | `training_job_key` |

Column lists and dataset descriptions are also shown on the protected
`/admin/power-bi` page. Traditional exam marks have no assumed pass threshold;
`passed` is populated only for submitted online exams with a configured
passing percentage. Timetable conflicts are calculated from overlapping time
ranges across different classes; same-class pairs are ignored. Teacher
workload exports assignment counts and period counts separately for the
published live timetable and reviewable drafts.

## Connect with Power BI Desktop

1. Sign in to Power BI Desktop with an authorized Microsoft organizational
   account if you intend to publish reports to a private Power BI workspace.
   No tenant, workspace, or report identifiers are configured by this app.
2. While signed into the school app as an administrator, download the Excel
   workbook from `/admin/power-bi`. Store it in a protected location.
3. In Power BI Desktop select **Get data → Excel workbook**, choose the file,
   and select the dimension/fact worksheets you need. Alternatively use
   **Get data → Text/CSV** for individual extracts.
4. In Model view, create one-to-many relationships using the keys documented
   above. Connect each fact date key to `dim_date`; use single-direction
   filtering from dimensions to facts unless a report specifically requires a
   different model.
5. Build visuals and validate totals against the existing admin reports before
   sharing. Do not treat model quality scores as ML accuracy or draw
   high-stakes conclusions from aggregated metrics alone.
6. If publishing, use an access-controlled private workspace with least
   privilege, appropriate retention, and the organization's student-data
   governance. Do **not** use Power BI **Publish to web** for these private
   school records.

The workbook contains a snapshot at download time. To refresh manually,
download it again and replace the Power BI Desktop source file at the same
protected path, then refresh the model.

## Scheduled refresh, links, and embedding

Scheduled refresh and report embedding are not enabled by this Phase 1 export
layer. A local SQLite file is not configured as a cloud Power BI refresh
source. For scheduled refresh, first provision an organization-approved
reporting database (for example, SQL Server or Azure SQL) and a supported,
secured ingestion process for these minimized datasets; then configure Power
BI credentials and gateway/refresh policy in the tenant. Protect the reporting
copy and document its retention and update cadence.

The app provides the protected datasets page, not a fabricated report URL or
an embedded report. If a future deployment adds embedding, use Microsoft's
supported Power BI Embedded/JavaScript or secure organizational embed flow
with Microsoft Entra ID authentication, server-side authorization, and
short-lived embed tokens. Never place client secrets or embed tokens in source
code or use public embedding for student data.

## Tests and boundaries

Reporting exports are tested using isolated SQLite databases. Tests cover
dataset grains/relationships, pseudonymous IDs, sensitive-field minimization,
attendance and exam values, timetable conflict detection, operations
aggregation, CSV formula escaping, workbook generation, and admin-only access.
They do not write to the production school database or contact Microsoft
services.

This implementation does not create a Power BI report, workspace, scheduled
refresh, gateway, or embedded report. Microsoft tenant/account configuration
is needed only to publish and share a report privately; local CSV/Excel
downloads require only an authorized school administrator account.
