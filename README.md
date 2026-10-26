# PRAMAAN — AI-assisted pre-scrutiny for AICTE approvals

PRAMAAN reads every document an institution uploads with its AICTE approval application. It checks the documents against the Approval Process Handbook rules and against the issuing authorities' records. It then gives the scrutiny officer a list of findings, each linked to the exact spot in the document that caused it.

It is **decision support only**. The system never approves or rejects anything. Every finding is accepted or overridden by an official, every deficiency letter goes through maker-checker approval, and every action is written to a tamper-evident audit trail.

> All institutions, people, certificates and issuer records in this repository are **synthetic**. The "issuing authorities" are a local sandbox. No real AICTE, government or institution data is used.

## What it does

| Area | What happens |
|---|---|
| **Document reading** | PDF text layer with word positions; Tesseract OCR (English + Hindi) for scanned pages; classifies the document type; extracts fields such as certificate number, validity, area and intake, with the box on the page each value came from. |
| **Forgery and quality checks** | Hidden text under white boxes; PDF digital signatures (PKI) checked for validity, trust and changes after signing; editing-tool metadata; impossible date order; photo EXIF date and GPS; error-level analysis; duplicate photos across institutions (perceptual hash); unreadable scans. |
| **Issuer verification** | Fire NOC, land registry, university affiliation, NBA accreditation and fee payment checked against the issuer's API (sandbox), with retries. Results: Verified / Mismatch / Expired / Source unavailable / Manual review. |
| **Rules** | A versioned rulebook of decision tables in JSON (no code, no `eval`). Rule admins edit it in the UI, try a rule on a real application, dry-run the whole draft over every application, then a second person approves it before it goes live. |
| **Findings** | Severity (critical / high / warning / info), category, the rule and handbook clause, plain-language message, and evidence chips (E1, E2…) that jump to the highlighted region of the page. Decisions carry over when the pre-check re-runs. |
| **Workflow** | Institution uploads and gets instant feedback → submits → scrutinizer reviews findings → deficiency letter (draft → senior approval → issued) → institution replies → re-check → senior officer records the decision. |
| **Oversight** | Dashboard (queue, pre-check times, outcomes, risk), verification log, alerts, and an audit trail where each event is hash-chained to the previous one, with an integrity check and CSV export. |
| **Access** | Role-based: institution, scrutinizer, senior officer, rule admin, auditor. Institutions see only their own applications; officials never see drafts. |
| **Languages** | English and Hindi interface. |

## Quick start (local development)

Requirements: Python 3.11+ (from python.org), Node 20+, Git, and optionally Tesseract with Hindi language data. Without Tesseract, everything works except OCR of scanned pages: those are sent to manual review instead.

Get the code first. The application is on the `claude/stoic-mayer-utvdia` branch:

```bash
git clone -b claude/stoic-mayer-utvdia https://github.com/vinay2905-lang/sih_2k26-1.git
cd sih_2k26-1
```

### Windows (Command Prompt)

```bat
:: Backend: first window, from the sih_2k26-1 folder
cd backend
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app.seed
uvicorn app.main:app

:: Frontend: second window, from the sih_2k26-1 folder
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173.

- If `py` is not found, create the virtual environment with the full path to python.org's Python instead, e.g. `"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m venv .venv`.
- Don't use the MSYS2/MinGW Python (`C:\msys64\...`): PyMuPDF, OpenCV and NumPy have no packages for it.
- After `activate`, the prompt starts with `(.venv)`. Run `.venv\Scripts\activate` again in every new window you use for the backend.
- In PowerShell, activate with `.venv\Scripts\Activate.ps1`. If scripts are blocked, first run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- To install Tesseract, use the installer from https://github.com/UB-Mannheim/tesseract/wiki and tick **Hindi** under "Additional language data". PRAMAAN finds `C:\Program Files\Tesseract-OCR` by itself. For another folder, set `PRAMAAN_TESSERACT_CMD` to the path of `tesseract.exe`.

### Linux / macOS

Tesseract: `apt install tesseract-ocr tesseract-ocr-hin` or `brew install tesseract tesseract-lang`.

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.seed                      # synthetic demo data (wipes backend/data)
uvicorn app.main:app --reload           # http://127.0.0.1:8000  (API docs at /docs)

# Frontend (second terminal)
cd frontend
npm ci
npm run dev                             # http://127.0.0.1:5173  (proxies /api to :8000)
```

Or run `npm run build` once: the API then serves the built frontend itself at http://127.0.0.1:8000.

Development defaults: SQLite at `backend/data/pramaan.db`, and background jobs on a thread inside the API process (`PRAMAAN_JOB_MODE=thread`).

## Demo accounts

Every account uses the password **`Pramaan@2026`**. The login page also lists them.

| Username | Role | What to try |
|---|---|---|
| `a.kulkarni` | Scrutinizer (Western) | Open the queue, work through findings, accept/override, draft a deficiency letter |
| `r.iyer` | Scrutinizer (South-Western) | Same, for the southern applications |
| `r.menon` | Senior officer | Approve letters, publish rulebook changes, record final decisions |
| `s.rao` | Rule admin | Edit a rule, try it on an application, dry-run, submit for approval |
| `auditor` | Auditor | Audit trail, integrity check, CSV export, verification log |
| `vce.pune`, `git.jaipur`, `nvp.indore`, `ksm.kochi`, `sie.lucknow`, `wgp.nagpur`, `tce.hubballi`, `sit.dehradun` | Institution | Your own application: upload, fix, reply to letters |

### Planted cases in the demo data

| Application | Institution | What the pre-check should find |
|---|---|---|
| APP-2026-00045 | Vidyaprakash College of Engineering, Pune | Expired Fire NOC; form says 180 seats but affiliation allows 120; structural certificate missing; unknown faculty IDs; a lab photo copied from another institution |
| APP-2026-00150 | Gulmohar Institute of Technology, Jaipur | Fire NOC with the old date hidden under a white box (tampered); new programme |
| APP-2026-00203 | Kayal School of Management, Kochi | NBA accreditation expired; lab photos taken far from campus; unsigned building certificate; land area mismatch; deficiency letter already issued |
| APP-2026-00231 | Sahyog Institute of Engineering, Lucknow | Fee payment failed; building certificate changed after it was digitally signed; too few computers |
| APP-2026-00112 | Narmada Valley Institute of Pharmacy, Indore | University API down (source unavailable after retries); scanned affidavit read by OCR |
| APP-2026-00264 | Tungabhadra College of Engineering, Hubballi | Fire NOC expires within 60 days |
| APP-2026-00087 | Wainganga Polytechnic, Nagpur | Clean application, already approved |
| APP-2026-00301 | Shivalik Institute of Technology, Dehradun | Draft with only some documents uploaded. Log in as `sit.dehradun` and use **Use sample** to finish it. |

## Hosting it on the web

**[docs/DEPLOY.md](docs/DEPLOY.md)** gives step-by-step instructions for putting PRAMAAN online with HTTPS on a cloud VM, for example with Azure for Students' free credit. On the server it comes down to:

```bash
git clone -b claude/stoic-mayer-utvdia https://github.com/vinay2905-lang/SIH_2K26-1.git pramaan && cd pramaan
sudo bash deploy/setup.sh --domain <your-hostname> --demo
```

For a quick free demo link, the root `Dockerfile` runs everything in one container on Render's free plan. The demo resets on every restart; see *Option D* in the deploy guide.

The React frontend can also be hosted on Vercel. Set the root directory to `frontend` and set `VITE_API_BASE` to the server's `https://` address. The backend still runs on the server: it needs Tesseract, persistent storage and a background worker, which Vercel functions don't provide. See *Option C* in the deploy guide.

## Production deployment (Docker)

`docker-compose.yml` runs PostgreSQL, the API (2 processes), a separate background worker, and nginx serving the React build. With `COMPOSE_PROFILES=https` and `PRAMAAN_DOMAIN` set, it also runs Caddy, which serves the site over HTTPS with an automatic certificate. `deploy/setup.sh` writes all of this for you.

```bash
cp .env.example .env        # then fill in POSTGRES_PASSWORD, PRAMAAN_STORAGE_KEY, PRAMAAN_JWT_SECRET
docker compose up -d --build
bash deploy/reset-demo.sh   # optional: load the synthetic demo data (wipes everything)
```

Open http://localhost:8080.

With `PRAMAAN_ENV=production` (set by the compose file), the API and worker refuse to start on the built-in development secrets.

### Configuration

All settings are environment variables with the prefix `PRAMAAN_` (see `backend/app/config.py`).

| Variable | Default | Meaning |
|---|---|---|
| `PRAMAAN_ENV` | `development` | `production` enforces real secrets |
| `PRAMAAN_DATABASE_URL` | SQLite file | e.g. `postgresql+psycopg://user:pass@host:5432/pramaan` |
| `PRAMAAN_DATA_DIR` | `backend/data` | Encrypted document store, trust roots, sandbox registry |
| `PRAMAAN_STORAGE_KEY` | dev key | 32-byte urlsafe-base64 key; documents are AES-256-GCM encrypted at rest |
| `PRAMAAN_JWT_SECRET` | dev secret | Token signing secret (32+ characters in production) |
| `PRAMAAN_JOB_MODE` | `thread` | `worker` = separate `python -m app.worker` process(es); `thread` = inside the API; `sync` = inline (tests) |
| `PRAMAAN_ISSUER_BASE_URL` | `http://127.0.0.1:8000/sandbox` | Base URL of the issuer verification APIs |
| `PRAMAAN_MOUNT_SANDBOX` | `true` | Serve the mock issuer APIs at `/sandbox` |
| `PRAMAAN_MAX_UPLOAD_MB` | `10` | Upload size limit |
| `PRAMAAN_OCR_LANGUAGES` | `eng+hin` | Tesseract languages (any that are not installed are skipped with a warning) |
| `PRAMAAN_TESSERACT_CMD` | auto | Path to `tesseract`/`tesseract.exe` if it is not on PATH |
| `PRAMAAN_CURRENT_CYCLE` | `2026-27` | Approval cycle whose rulebook is used |
| `PRAMAAN_CORS_ORIGINS` | Vite dev origins | Comma-separated origins allowed to call the API from another site (e.g. a Vercel frontend) |
| `PRAMAAN_CORS_ORIGIN_REGEX` | none | Same, as a regular expression (e.g. Vercel preview URLs) |
| `PRAMAAN_SHOW_DEMO_LOGINS` | `true` (`false` in docker-compose) | List the demo accounts on the sign-in page |

## Tests

```bash
cd backend
python -m pytest -q                                   # SQLite
PRAMAAN_TEST_DATABASE_URL=postgresql+psycopg://user@host/db python -m pytest -q   # PostgreSQL

cd ../frontend && npm run typecheck && npm run build

# Browser walkthrough of every role (needs freshly seeded data and a running server)
cd ../e2e && npm install && npx playwright install chromium
node walkthrough.cjs http://127.0.0.1:8000          # screenshots go to e2e/screenshots
```

The backend tests seed the full demo data set and check the following:
- every planted problem is found, and the clean application comes out clear;
- role-based access rules;
- maker-checker on letters and the rulebook;
- the decision guard rails;
- audit-chain tamper detection;
- that several processes can start on an empty database at the same time.

The walkthrough drives every role through the UI in Chromium via Playwright.

## Repository layout

```
backend/
  app/
    api/            REST endpoints (auth, applications, documents, findings, letters, rulebook, dashboard, audit)
    pipeline/       ingest/OCR, classify, extract, signatures, forensics, QR, facts, rules engine, verification, orchestrator
    rulebook/       default_rulebook.json — the published rules for the cycle
    sandbox/        mock issuing-authority APIs (fire, land, university, NBA, payments)
    seed/           synthetic institutions, documents, PKI and the demo data loader
    audit.py        hash-chained audit log
    jobs.py         database-backed job queue
    storage.py      AES-256-GCM encrypted document store
    worker.py       background worker entry point
  tests/
frontend/           React + TypeScript (Vite)
e2e/                Playwright walkthrough
Dockerfile          single-container image (Render and similar hosts)
deploy/             setup.sh (server install), reset-demo.sh, Caddyfile (HTTPS), start-single.sh
docs/               ARCHITECTURE.md, DEPLOY.md
docker-compose.yml
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.
