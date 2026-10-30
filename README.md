# 234 · B1: DreamGuard — Smart Data Masking System for PII Protection

> Automated PII discovery, local and cloud AI classification, and dynamic role-based data masking over financial databases without modifying stored records.

## What it does

### The Problem
Financial institutions store sensitive customer data—credit card numbers, national identity identifiers (PAN, Aadhaar, SSN), and account balances—across relational databases. Exposing direct database access to internal teams risks severe regulatory non-compliance (DPDP Act 2023, GDPR, PCI-DSS v4) and insider data leakage. Traditional static masking permanently alters or duplicates data, creating synchronization drift and storage overhead.

### Who Uses DreamGuard
- **Security & Compliance Administrators:** Configure database connections, inspect discovered PII, author masking policies, manage table grants, review cryptographic audit logs, and execute break-glass unmasking with audit justification.
- **Customer Support Agents:** Access customer records with partial masking (e.g., card numbers show only first 4 and last 4 digits; phone numbers show only the last 4 digits) to verify customer identities without exposing full secrets.
- **Data Analysts:** Query transaction trends and financial metrics with full name/phone redaction, deterministic HMAC-SHA-256 pseudonymization (preserving relational joins across tables), and enforced aggregate cohort minimums ($k \ge 5$).
- **Compliance Auditors:** Inspect unbroken cryptographic SHA-256 audit chains and run table fingerprint verifications with zero exposure to raw customer records.

### How Sensitive Information is Discovered
DreamGuard scans connected database schemas and samples up to 100 random rows per table directly into memory:
1. **Deterministic Rule Scanner:** Uses regular expressions and mathematical checksum algorithms (Luhn for Credit Cards, Verhoeff for Aadhaar, regex patterns for Indian PAN, US SSN, Passports, IBAN, IFSC, Emails, and Phone Numbers).
2. **Local Machine Learning Classifier:** An in-process stacked classifier (TF-IDF character n-grams + HistGradientBoosting) trained on 4,700 synthetic columns that classifies columns based on header semantics and sanitized value statistics.
3. **Optional Cloud LLM (Gemini):** Disambiguates cryptic headers and atypical data patterns using sanitized statistics only (zero raw PII crosses the network boundary).
4. **Upgrade-Only Arbitration:** An arbitration engine that allows AI/ML to elevate sensitivity ranks (e.g., from `INTERNAL` to `CONFIDENTIAL`), but strictly prevents automated models from downgrading deterministic rule discoveries or overriding prior human reviews.

### How Dynamic Masking Works
At query runtime, DreamGuard intercepts SQL queries through an Abstract Syntax Tree (AST) engine (`sqlglot`), validates table grants, resolves the caller's role-specific masking policies per column, executes the query against the target database inside a strictly read-only transaction, applies masking transformations in memory, logs the event to a tamper-evident SHA-256 audit chain, and returns the sanitized result set. Stored records are never modified.

### Optimistic Query Optimization Implementation
DreamGuard implements pre-flight query risk analysis and caching:
- **Query Risk Analyzer (`/api/query/analyze`):** Validates SQL grammar, resolves AST lineage, and checks column policies without executing against target databases.
- **In-Memory LRU Result Cache (`execute_cached`):** Caches raw database result tuples. On cache hits, results are dynamically passed through the caller's specific `MaskingEngine`, ensuring sub-2ms response times while preventing cross-role data leaks.
- *Limitation Disclosure:* Speculative execution and optimistic concurrency control are not implemented; optimization relies on AST pruning, connection pooling, and in-memory LRU caching.

### Zero-Full-Page-Reload User Experience
DreamGuard is engineered as a pure Single Page Application (SPA) using React 18, React Router v6, and TanStack React Query v5:
- **Client-Side Routing:** Navigating between operational workspaces (`/admin/*`, `/support/*`, `/analyst/*`) executes without browser reloads.
- **Reactive Cache Synchronization:** State changes (e.g. updating a policy, reviewing a classification) automatically invalidate corresponding TanStack Query keys, refreshing UI panels asynchronously without full-page reloads.

---

## How to run

### Prerequisites
- **Python:** 3.12 or newer.
- **Node.js:** v20.x or newer (with npm).
- **Evaluation Dataset:** Saffron Bank Ltd pack in `Datasets/` (or copied automatically by startup script).
- **Operating System:** Windows, Linux, or macOS.

### Environment Configuration
Copy the provided `.env.example` file to `.env` in the repository root:
```bash
cp .env.example .env
```
*(On Windows PowerShell: `Copy-Item .env.example .env`)*

All settings have safe defaults. External services (MySQL, PostgreSQL, Gemini) are strictly optional; DreamGuard runs fully offline using SQLite and the local ML model.

### Unified One-Click Startup

#### Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File FULL_CODE/scripts/start.ps1
```

#### Linux / macOS:
```bash
chmod +x FULL_CODE/scripts/start.sh
./FULL_CODE/scripts/start.sh
```

### Manual Step-by-Step Startup

#### 1. Backend Service
```bash
cd FULL_CODE/backend
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli reset         # Copies Saffron Bank DB, initializes tables, seeds demo users
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

#### 2. Frontend Console
```bash
cd FULL_CODE/frontend
npm install
npm run build
npm run preview -- --port 5173
```

Open your browser at **`http://127.0.0.1:8000`** (or `http://127.0.0.1:5173`).

### Pre-Seeded Evaluation Accounts
- **Admin:** `admin_anita` / `Admin@2026!` (Security & Governance Workspace)
- **Support:** `support_ravi` / `Support@2026!` (Customer Operations Workspace)
- **Analyst:** `analyst_kavya` / `Analyst@2026!` (Privacy-Preserving Analytics Workspace)
- **Compliance:** `compliance_lata` / `Compliance@2026!` (Audit & Verification Workspace)

---

## How to run the tests

Execute the complete automated test suite with Python using `pytest`:

```powershell
# Windows PowerShell (from repository root)
$env:PYTHONPATH="FULL_CODE/backend"
FULL_CODE\backend\.venv\Scripts\python -m pytest FULL_CODE/backend/tests -q
```

```bash
# Linux / macOS (from repository root)
PYTHONPATH="FULL_CODE/backend" FULL_CODE/backend/.venv/bin/python -m pytest FULL_CODE/backend/tests -q
```

### Verified Test Suite Results
- **Total Tests Executed:** 166 tests.
- **Passing Tests:** **152 passed**.
- **Skipped Tests:** 14 skipped (live MySQL and PostgreSQL server integration tests, safely skipped when optional database server passwords are not configured in `.env`).
- **Failures:** **0 failed**.
- **Execution Time:** ~116 seconds.

### Frontend TypeScript Verification
```bash
npm --prefix FULL_CODE/frontend run typecheck
# Result: 0 errors
```

---

## Architecture

```
+─────────────────────────────────────────────────────────────────────────────+
|                         DREAMGUARD SYSTEM ARCHITECTURE                      |
+─────────────────────────────────────────────────────────────────────────────+
| [Client Browser]  React 18 + Vite + Tailwind CSS (Zero-Reload SPA)         |
+──────────────────────────────────────┬──────────────────────────────────────+
                                       │ HTTPS /api/*
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
| [FastAPI Enforcement Gateway]  (Python 3.12 / Uvicorn)                      |
| ├── Auth & RBAC: Principal resolution, session token hashing (app/security) |
| ├── SQL Guard: AST grammar, lineage tracing, LIMIT rewrite (app/sql_guard)  |
| ├── Policy Engine: 4-level precedence rule resolver (app/policy.py)         |
| ├── Result Cache: Thread-safe LRU + TTL query cache (app/connectors.py)     |
| ├── Dynamic Masking Engine: HMAC-SHA256, Partial, Redact (app/masking.py)   |
| ├── Audit System: SHA-256 hash-chained immutable log (app/audit.py)         |
| └── Metadata DB: SQLite sentinel_meta.db (WAL mode, triggers)               |
+───────────────────────┬──────────────────────────────┬──────────────────────+
                        │                              │
          Sanitized Stats Only (No Raw PII)            │ Strict Read-Only Queries
                        ▼                              ▼
+────────────────────────────────+   +────────────────────────────────────────+
| [PII Intelligence Pipeline]    |   | [Target Database Tier]                 |
| ├── Rule Scanner (app/scanner) |   | ├── SQLite Saffron Bank (129,260 rows) |
| ├── Local ML (app/ml/model)    |   | ├── MySQL 8+ (START TRANSACTION RO)    |
| ├── Gemini API (sanitized JSON)|   | └── PostgreSQL (Read-Only User)        |
| └── Upgrade Arbitration Engine |   +────────────────────────────────────────+
+────────────────────────────────+
```

### Main Modules and Directories
- `FULL_CODE/backend/app/main.py`: Application entry point, middleware, CORS, and route registration.
- `FULL_CODE/backend/app/security.py`: Authentication, bcrypt password hashing, and role permissions.
- `FULL_CODE/backend/app/sql_guard.py`: `sqlglot` AST parsing, SQL injection protection, column lineage resolution, and automatic `LIMIT` injection.
- `FULL_CODE/backend/app/query_engine.py`: Single enforcement path: authorization -> AST rewrite -> cache -> read-only execution -> masking -> audit.
- `FULL_CODE/backend/app/policy.py`: Policy precedence cascade (Column -> Category -> Sensitivity -> Role Default).
- `FULL_CODE/backend/app/masking.py`: Server-side transformation routines (`PARTIAL`, `HASH_HMAC`, `REDACT`, `DROP`, `ALLOW`).
- `FULL_CODE/backend/app/connectors.py`: Multi-backend read-only connection pooling and LRU result cache.
- `FULL_CODE/backend/app/scanner.py`: Deterministic regex and checksum validators (Luhn, Verhoeff, PAN).
- `FULL_CODE/backend/app/ml/`: Local in-process machine learning pipeline (`model.py`, `train.py`, `featurize.py`, `artifacts/pii_model.joblib`).
- `FULL_CODE/backend/app/ai_classifier.py`: Google Gemini API client and upgrade-only arbitration engine.
- `FULL_CODE/backend/app/audit.py`: Cryptographic SHA-256 tamper-evident event chaining.
- `FULL_CODE/backend/app/integrity.py`: Cumulative table row fingerprinting verifying source immutability.
- `FULL_CODE/frontend/src/`: React 18 Single Page Application with dedicated role-specific operational workspaces.

---

## AI usage

### 1. In-Application AI & Machine Learning

#### A. Local In-Process Machine Learning Classifier (`app/ml/model.py`)
- **Algorithm:** Stacked model: TF-IDF character n-gram Logistic Regression on column names combined with HistGradientBoostingClassifier on 37 sanitized value statistics, calibrated via 5-fold isotonic calibration (`CalibratedClassifierCV`).
- **Execution:** Runs 100% in-process via `scikit-learn` and `joblib`. Requires zero internet access, zero API keys, and has sub-5ms inference latency.
- **Model Artifact:** Bundled in repository at `FULL_CODE/backend/app/ml/artifacts/pii_model.joblib` (5.7 MB) with metadata in `model_card.json`.
- **Performance:** **98.23% accuracy** on synthetic held-out column names; **0.880 Macro F1** on official Saffron Bank benchmark columns.

#### B. Cloud Contextual LLM (`app/ai_classifier.py`)
- **Model & Provider:** Google Gemini (`gemini-2.5-flash` / `gemini-3.8-flash`) via `google-genai` SDK.
- **Role:** Contextual disambiguation of abbreviated or non-standard column headers (e.g. `mob_no`, `cust_nm`).
- **Privacy Enforcement (Zero Raw PII Egress):** The Gemini API **never receives raw customer rows**. Only statistical metadata (character ratios, string lengths, regex match proportions) is transmitted.
- **Upgrade-Only Arbitration:** Models can only elevate sensitivity rank; they can never downgrade deterministic rule discoveries or override prior human administrator reviews.

### 2. AI-Assisted Development Tools
- **Antigravity / Google DeepMind Agentic Assistant:** Used for codebase exploration, test orchestration, schema alignment, and architectural validation.
- **Claude Code (Anthropic):** Used for initial synthetic corpus generation scripts (`synth.py`) and regex entity verification.
- **Human Engineering & Ownership:** All core architecture, AST lineage algorithms, SQL security controls, cryptographic hash chains, and business logic were engineered, debugged, and verified by the development team.

---

## Pre-built and third-party code

### 1. Pre-built Libraries & Frameworks (Installed via Manifests)
- **FastAPI (0.115.5) & Starlette:** Web framework and routing under MIT License.
- **Uvicorn (0.32.0):** ASGI server under BSD 3-Clause License.
- **SQLAlchemy (2.0.36):** Database toolkit and connection pooling under MIT License.
- **sqlglot (26.2.0):** SQL AST parser, transpiler, and lineage analyzer under MIT License.
- **scikit-learn (1.5.2+) & NumPy:** Machine learning algorithms and numerical arrays under BSD 3-Clause License.
- **joblib (1.4.2):** Python object serialization under BSD 3-Clause License.
- **google-genai (0.1.1):** Google GenAI SDK under Apache 2.0 License.
- **bcrypt (4.2.1) & cryptography:** Password hashing and cryptographic primitives under Apache 2.0 / BSD License.
- **React (18.3.1), Vite (5.4.11), Tailwind CSS (3.4.15):** Frontend UI library, bundler, and CSS framework under MIT License.
- **TanStack React Query (5.62.0):** Asynchronous state management under MIT License.
- **Recharts (2.13.3) & Lucide React (0.460.0):** Charting components and icons under MIT License.
- **pdfplumber & python-docx:** Document text extraction under MIT License.

### 2. Benchmark Dataset
- **Saffron Bank Ltd Dataset:** Official benchmark data pack provided by the hackathon organizers (9 tables, 129,260 synthetic records). Synthetic test data under Creative Commons Attribution 4.0 International (CC BY 4.0).

---

## Limitations

### 1. Unimplemented Speculative Concurrency
While DreamGuard implements query risk pre-flight analysis (`/api/query/analyze`) and in-memory LRU result caching (`execute_cached`), it does not implement speculative optimistic execution or multi-version optimistic concurrency control (OCC).

### 2. Single-Instance Cache Architecture
The result cache is an in-memory LRU structure (`OrderedDict`) residing in the FastAPI process memory. In a multi-replica distributed deployment, an external distributed cache (such as Redis) would be required to share cached queries across horizontal backend instances.

### 3. Unsupported Database Dialects
DreamGuard provides verified adapters for SQLite, MySQL, and PostgreSQL. Enterprise data warehouses (e.g. Snowflake, Google BigQuery, Oracle Database, Microsoft SQL Server) are currently planned for future roadmap releases.

### 4. Cloud LLM Network Dependency
While local ML and rule-based detection run 100% offline, the optional Gemini AI classification layer requires external internet egress to Google APIs. When internet is unavailable, DreamGuard operates on rule and local ML models without disruption.

### 5. Document Parser Limitations
Unstructured document scanning for legacy `.doc` files relies on external `antiword` binary availability; without it, legacy `.doc` parsing is skipped while `.docx`, `.pdf`, `.csv`, and `.txt` parsing remain fully supported.
