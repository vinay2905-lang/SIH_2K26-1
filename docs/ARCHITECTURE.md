# PRAMAAN architecture

## Components

```
                ┌──────────────────────────────┐
 Browser ──────▶│ web (nginx + React build)    │
                └──────────────┬───────────────┘
                               │ /api, /sandbox
                ┌──────────────▼───────────────┐      ┌──────────────────────────┐
                │ api (FastAPI, N processes)   │─────▶│ Issuer APIs              │
                │  auth · RBAC · uploads       │      │ (sandbox at /sandbox, or │
                │  findings · letters · rules  │      │  real adapters)          │
                └──────┬──────────────┬────────┘      └────────────▲─────────────┘
                       │ enqueue      │ read/write                 │ verify
                ┌──────▼──────────────▼────────┐      ┌────────────┴─────────────┐
                │ PostgreSQL                   │◀────▶│ worker (python -m        │
                │  applications · documents    │ jobs │  app.worker, N copies)   │
                │  findings · audit · jobs     │      │  OCR · forensics · rules │
                └──────────────────────────────┘      └────────────┬─────────────┘
                                                                   │
                                     encrypted document store (/data volume, shared)
```

- **web**: static React app. nginx proxies `/api` and `/sandbox` to the API.
- **api**: stateless FastAPI. It handles auth, validation, permissions and reads. Anything slow (reading documents, running pre-checks, dry runs) is written to the `jobs` table instead of being done in the request.
- **worker**: polls the `jobs` table. On PostgreSQL it claims jobs with `SELECT … FOR UPDATE SKIP LOCKED`, so any number of workers can run side by side. Jobs left running by a crashed worker are re-queued after 10 minutes, and failed jobs retry up to 3 times.
- **PostgreSQL**: the single source of truth, including the job queue. There is no separate broker to run.
- **Document store**: every uploaded file is encrypted with AES-256-GCM before it touches disk. Each file is addressed by a random key and its SHA-256 is recorded.

For development the same code runs as one process on SQLite, with the worker on a background thread (`PRAMAAN_JOB_MODE=thread`).

## Document pipeline

Each upload creates a `process_document` job:

1. **Ingest**: PyMuPDF gives the text layer with word boxes. Pages without text, and images, go through Tesseract OCR (English + Hindi), keeping word confidences. Words are grouped into visual lines.
2. **Hidden text**: words drawn under an opaque white rectangle are found by comparing drawing order. This catches the classic "white box over the old date" forgery.
3. **Classify**: keyword scoring against the 10 document types in `pipeline/templates.py`.
4. **Extract**: per-type field patterns, with state-specific overrides (for example, Maharashtra NOCs say "Valid up to"). Every value keeps its page and bounding box, which becomes the evidence highlight.
5. **Signature**: pyHanko validates embedded PDF signatures against the configured trust roots. It reports intact / trusted / modified after signing.
6. **Forensics**: editing-tool metadata, modification after creation, impossible date order, photo EXIF date and GPS, error-level analysis, and a perceptual hash for duplicate detection across all institutions.
7. **QR**: OpenCV decodes QR codes. When a certificate carries one, the issuer lookup uses the reference in the QR rather than the printed number.

When a document finishes, a `run_precheck` job is queued for the application. Duplicate queued pre-checks are merged.

## Pre-check

`run_precheck` builds a flat **fact set** for the application. Examples:
- `doc.FIRE_NOC.valid_till`
- `form.intake.total`
- `record.faculty.unknown_count`
- `verify.FIRE_NOC.status`
- `application.as_of_date`

It does this from:
- the form;
- the extracted fields;
- AICTE's own records for the institution;
- issuer verification results.

Each fact remembers which document region it came from.

It then:

1. **Verifies** with the issuers. Each adapter calls the issuer API with retries and backoff. The outcome is VERIFIED, MISMATCH (field-by-field comparison, fuzzy for names), EXPIRED, SOURCE_UNAVAILABLE (after retries) or MANUAL_REVIEW.
2. **Checks the checklist**: the required documents for the application type.
3. **Evaluates the rulebook** (`pipeline/rules_engine.py`). Each rule is a decision table:

   ```json
   {
     "rule_id": "FIRE-NOC-01",
     "scope": "application",
     "applies_to": {"app_types": [], "states": []},
     "rows": [{
       "when": [{"fact": "doc.FIRE_NOC.valid_till", "op": "before", "ref": "application.as_of_date"}],
       "severity": "critical", "category": "EXPIRED_DOCUMENT",
       "title": "Fire NOC lapsed before the application date",
       "message": "The Fire NOC is valid till {doc.FIRE_NOC.valid_till}, but the application is dated {application.as_of_date}."
     }]
   }
   ```

   Conditions are data, never code. Operators: `exists`, `missing`, `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `before`, `after`, `within_days`, `in`, `not_in`, `empty`, `not_empty`, `similar_lt`, `differs`. Every row whose conditions all hold produces a finding. A rule with `"scope": "each_document"` runs once per document, with `this.*` facts.
4. **Adds** forensic and duplicate findings.
5. **Reconciles** with the previous run. Each finding has a stable key (rule, row, document). An officer's earlier accept/override carries over. Findings that no longer occur are marked RESOLVED.
6. **Scores**: risk = Σ severity weight (critical 25, high 12, warning 5), capped at 100. Overall status: NEEDS_ACTION / NEEDS_REVIEW / MINOR_ISSUES / CLEAR.
7. **Raises alerts**: for officials (new critical findings, sources down) and for the institution (what to fix).

Every finding stores its evidence:
- the document;
- the page;
- the bounding box;
- the facts used.

The workspace draws the highlight from these.

## Rulebook governance

```
DRAFT ──submit (change note)──▶ PENDING_APPROVAL ──approve (different person)──▶ PUBLISHED
  ▲                                   │                                             │
  └───────────── return with comments ┘                     previous version ──▶ RETIRED
```

- Only one draft is open at a time. Saving validates the whole rulebook and returns the list of problems.
- **Try on**: evaluate one rule against a real application's facts, without saving.
- **Dry run**: evaluate the whole draft against every application, as a background job. It shows how many findings would appear or disappear.
- Publishing re-runs the pre-check on every application that is not yet decided. Old runs keep the version label (e.g. "APH 2026-27 v2") they were checked under.

## Workflow and guard rails

- Institutions can edit only while in DRAFT, or when replying to a deficiency letter.
- Submitting needs at least one uploaded document and one programme with its intake. Missing mandatory documents become findings for the officer.
- A deficiency letter is drafted from the open findings by a scrutinizer. It needs approval from someone else (senior officer) before it is issued.
- **Override** of a finding needs a written reason (10+ characters).
- **Approval** is blocked while any critical or high finding is still open. **Not approved** needs a reason (20+ characters). Both need explicit confirmation.

## Security

- **Authentication**: JWT bearer tokens (HS256) with expiry. Passwords are hashed with PBKDF2-SHA256 (salted).
- **Access**: role-based on every endpoint, plus row-level rules. An institution can read only its own applications and documents. Officials cannot see drafts. Institutions cannot see the audit trail or verification log; CSV export of the audit trail is limited to auditors and senior officers.
- **Uploads**:
  - size limit;
  - file type checked by magic bytes, not by extension;
  - photos only in photo slots.
- **Storage**: documents are encrypted at rest. Aadhaar numbers are masked in the stored text extracted from documents.
- **Audit trail**: each event stores `hash = SHA-256(previous hash + event)`. Writes are serialised with a PostgreSQL advisory lock (or a file lock on SQLite), so the chain stays linear with many processes. `GET /api/audit/verify` walks the chain and reports the first broken link.
- **Production**: `PRAMAAN_ENV=production` refuses to start with the development secrets. The API and worker containers run as a non-root user.

## Data model (main tables)

| Table | Holds |
|---|---|
| `institutions`, `institution_records` | Institution master data and AICTE's own records (approved programmes, faculty registry) |
| `users` | Accounts with role, region, institution |
| `applications` | Form (JSON), status, risk score, overall status, assigned officer, decision |
| `documents`, `extracted_fields` | Uploaded files (encrypted key, hash, pages, quality, signature, forensics) and fields with page/bbox/confidence |
| `precheck_runs`, `findings`, `verifications` | Each pre-check run, its findings with evidence and officer decisions, and issuer call results |
| `rulebook_versions` | Versioned rulebook JSON with status, maker, checker, change note |
| `letters` | Deficiency letters with review and institution reply |
| `alerts` | Notifications for officials and institutions |
| `audit_events` | Hash-chained log of every action |
| `jobs` | Background job queue |

## Connecting real issuers

`pipeline/verify.py` holds one small adapter per issuer. Each adapter:
- builds a request from the extracted fields;
- calls `GET {PRAMAAN_ISSUER_BASE_URL}/<source>`;
- compares the returned record with the submitted values.

To use a real API (for example a state fire department, DigiLocker, or a university portal):
- point the adapter at it, or add a new one with the same return shape;
- set `PRAMAAN_MOUNT_SANDBOX=false`.

Anything an adapter cannot reach becomes SOURCE_UNAVAILABLE and is shown to the officer. The application is never blocked on it.
