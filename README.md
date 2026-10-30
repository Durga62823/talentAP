# 234 · B1: DreamGuard — Smart Data Masking System for PII Protection

> Automated PII discovery, local and cloud AI classification, and dynamic role-based data masking over financial databases without modifying stored records.

---

## What it does

### The Problem
Financial institutions store sensitive customer personally identifiable information (PII)—national identifiers (Indian PAN, Aadhaar, US SSN, UK National Insurance, Passports), payment card numbers (PCI-DSS), contact details, and account balances—across production databases. Exposing direct database access to internal teams (support agents, analysts, non-admin engineers) violates strict financial data compliance regulations (DPDP Act 2023, RBI Cyber Security Framework, GDPR, PCI-DSS v4) and creates major data leak risks. 

Traditional static data masking duplicates or permanently alters underlying tables, creating synchronization lag, storage bloat, and operational fragility. DreamGuard solves this by providing **dynamic, in-flight SQL query interception and server-side masking**: production database records remain completely untouched and immutable, while queries executed by different organizational roles receive real-time, context-aware masked views.

### Who Uses DreamGuard
DreamGuard provides four dedicated, role-based operational personas:

1. **Security & Compliance Administrators (`ADMIN`):**
   - Discovers and catalogs sensitive columns across connected relational databases.
   - Authors and manages masking policies (e.g., partial mask, HMAC-SHA-256 hash, full redaction) with a four-tier precedence engine.
   - Enforces table-level access grants and configures break-glass emergency unmasking policies.
   - Verifies unbroken cryptographic SHA-256 audit chains and table fingerprint integrity.

2. **Customer Support Agents (`SUPPORT`):**
   - Looks up customer accounts and triages customer support inquiries without seeing full customer secrets.
   - Operates with partial masking on contact details (email, phone, address) and credit cards (e.g., `4111-XXXX-XXXX-1111`) to verify customer identity.
   - High-risk financial metrics (account balances, loan amounts) are completely redacted, and unauthorized tables (e.g., credit risk scores) are strictly blocked.

3. **Data Analysts (`ANALYST`):**
   - Conducts privacy-preserving business intelligence and statistical queries.
   - PII columns are fully redacted, while relational keys are pseudonymized using deterministic HMAC-SHA-256, allowing analysts to perform valid multi-table joins across masked datasets.
   - Enforces differential privacy group-size minimums ($k \ge 5$) on aggregate queries to prevent cohort re-identification.

4. **Compliance Auditors (`COMPLIANCE`):**
   - Inspects tamper-evident SHA-256 audit trails recording every query, user session, policy evaluation, and break-glass action.
   - Runs live table integrity verifications to mathematically prove that underlying database rows have not been tampered with.

### What They See
DreamGuard is engineered as a zero-full-page-reload Single Page Application (SPA) built with React 18, React Router v6, and TanStack React Query:

- **Admin Console:** Schema discovery dashboard with entity tags and confidence scores; policy configuration matrix; table grant toggles; tamper-evident audit log ledger; and break-glass access review workflow.
- **Support Workspace:** Quick customer search bar; masked customer profile overview; and support ticket triage feed with real-time server-side partial masking.
- **Analyst Workspace:** Interactive SQL query editor with AST pre-flight validation; privacy-preserving Aggregate Explorer; cohort suppression alerts ($k < 5$ warnings); and exportable anonymized summaries.
- **Compliance Workspace:** Cryptographic SHA-256 audit log verifier with broken-link detection; source database row fingerprint comparator confirming zero data mutation.

---

## How to run

### Where to Put the Data (BFSI Track Guidelines)
In accordance with the BFSI Hackathon guidelines, database dumps and large database binaries are excluded from Git. 
- Place the hackathon's Saffron Bank dataset files into `Datasets/` in the project root:
  - `Datasets/data/` (contains CSV reference files such as `users.csv`)
  - `Datasets/sql/sqlite/saffron_bank.db` (or run the schema migrations to generate it)
- During the automated startup script or reset command (`python -m app.cli reset`), the database is verified and initialized into the local runtime target path at `data/targets/saffron_bank.db`.

### Environment Configuration
Copy the provided environment template to `.env` in the repository root:

```bash
# Linux / macOS:
cp FULL_CODE/.env.example .env

# Windows PowerShell:
Copy-Item FULL_CODE/.env.example .env
```

All environment variables in `FULL_CODE/.env.example` are pre-configured with safe local defaults. External services (MySQL, PostgreSQL, Google Gemini API) are strictly optional; DreamGuard runs 100% offline using SQLite and the bundled local ML model.

### Prerequisites
- **Python:** 3.12 or newer.
- **Node.js:** v20.x or newer (with `npm`).
- **Operating System:** Windows, Linux, or macOS.

### One-Command Startup

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

#### 1. Backend Service (FastAPI)
```bash
cd FULL_CODE/backend
python -m venv .venv

# Activate virtual environment:
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies:
pip install -r requirements.txt

# Initialize database, schema, and demo accounts:
python -m app.cli reset

# Start backend server:
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

#### 2. Frontend Application (React + Vite)
```bash
cd FULL_CODE/frontend
npm install
npm run build
npm run preview -- --port 5173
```

Open your browser at **`http://127.0.0.1:8000`** (or `http://127.0.0.1:5173`).

### Pre-Seeded Evaluation Accounts
| Role | Username | Password | Workspace |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin_anita` | `Admin@2026!` | Security & Governance Console |
| **Support** | `support_ravi` | `Support@2026!` | Customer Support Portal |
| **Analyst** | `analyst_kavya` | `Analyst@2026!` | Privacy-Preserving Analytics Workspace |
| **Compliance** | `compliance_lata` | `Compliance@2026!` | Cryptographic Audit & Integrity Workspace |

---

## How to run the tests

Execute the complete automated backend test suite with one command:

```powershell
# Windows PowerShell (from repository root):
$env:PYTHONPATH="FULL_CODE/backend"; FULL_CODE\backend\.venv\Scripts\python -m pytest FULL_CODE/backend/tests -q
```

```bash
# Linux / macOS (from repository root):
PYTHONPATH="FULL_CODE/backend" FULL_CODE/backend/.venv/bin/python -m pytest FULL_CODE/backend/tests -q
```

### Test Suite Execution Summary
- **Total Tests:** 166 automated tests.
- **Passed:** **152 passed**.
- **Skipped:** 14 skipped (optional live MySQL and PostgreSQL connection tests, automatically skipped when external database servers are not running).
- **Failed:** **0 failed**.
- **Execution Time:** ~116 seconds.
- **Coverage Areas:** SQL AST parsing, column lineage extraction, deterministic regex & checksum validators (Luhn, Verhoeff, PAN), dynamic masking transformations, HMAC pseudonymization, role-based access control, cryptographic SHA-256 audit chaining, and aggregate privacy threshold enforcement ($k \ge 5$).

### Frontend TypeScript Verification
Verify frontend TypeScript compilation with zero errors:
```bash
npm --prefix FULL_CODE/frontend run typecheck
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

### Main Components Inside `FULL_CODE/` and How They Connect

1. **`FULL_CODE/backend/app/main.py`:** Application entry point, ASGI server configuration, CORS restrictions, and route registration.
2. **`FULL_CODE/backend/app/sql_guard.py`:** Parses SQL queries into Abstract Syntax Trees using `sqlglot`. Validates query semantics, prevents SQL injection, traces column lineage through aliases and joins, and enforces safe `LIMIT` injection.
3. **`FULL_CODE/backend/app/query_engine.py`:** Single enforcement pipeline: validates table grants -> rewrites AST -> executes query within a read-only transaction -> applies server-side dynamic masking in memory -> appends to cryptographic audit chain.
4. **`FULL_CODE/backend/app/policy.py`:** Policy resolution engine implementing a 4-tier precedence cascade: `Column Policy > Category Policy > Sensitivity Level > Role Default`.
5. **`FULL_CODE/backend/app/masking.py`:** Memory-level transformation primitives:
   - `PARTIAL`: Retains non-sensitive prefix/suffix (e.g., `4111-XXXX-XXXX-1111`, `******1234`).
   - `HASH_HMAC`: Deterministic keyed HMAC-SHA-256 pseudonymization preserving relational joins across tables.
   - `REDACT`: Complete suppression (`[REDACTED]`).
   - `DROP`: Completely omits columns from response payload.
   - `ALLOW`: Passes through unmasked (Admin or authorized role only).
6. **`FULL_CODE/backend/app/connectors.py`:** Connection pool manager for SQLite, MySQL, and PostgreSQL with a thread-safe LRU result cache (`execute_cached`).
7. **`FULL_CODE/backend/app/scanner.py`:** Deterministic pattern recognition engine combining regular expressions and mathematical checksum algorithms (Luhn for Credit Cards, Verhoeff for Indian Aadhaar, format validators for PAN, SSN, IBAN, IFSC, Email, Phone).
8. **`FULL_CODE/backend/app/ml/`:** Local in-process machine learning classifier (`model.py`, `featurize.py`, `train.py`, and trained model artifact `artifacts/pii_model.joblib`).
9. **`FULL_CODE/backend/app/ai_classifier.py`:** Optional Google Gemini cloud LLM client with strict privacy guardrails and upgrade-only arbitration logic.
10. **`FULL_CODE/backend/app/audit.py`:** Cryptographic SHA-256 hash-chained immutable audit log where each event records the SHA-256 hash of the preceding entry.
11. **`FULL_CODE/backend/app/integrity.py`:** Computes cumulative row hashes across database tables to mathematically prove zero modification to source data.
12. **`FULL_CODE/frontend/src/`:** React 18 Single Page Application with dedicated role-specific operational workspaces (`/admin/*`, `/support/*`, `/analyst/*`, `/compliance/*`).

---

## AI usage

### 1. In-Application AI & Machine Learning

#### A. Local In-Process Machine Learning Classifier (`FULL_CODE/backend/app/ml/model.py`)
- **Algorithm & Architecture:** A stacked hybrid model combining:
  1. Character n-gram TF-IDF Logistic Regression on column names.
  2. `HistGradientBoostingClassifier` trained on 37 statistical value features (length distributions, character class proportions, entropy, checksum validity ratios).
  3. Probability calibration using 5-fold isotonic regression (`CalibratedClassifierCV`).
- **Execution & Privacy:** Runs 100% locally in-process via `scikit-learn` and `joblib`. Requires zero internet access, zero API keys, and achieves sub-5ms inference latency.
- **Model Artifact:** Bundled in `FULL_CODE/backend/app/ml/artifacts/pii_model.joblib` (5.7 MB) with documented hyperparameters in `model_card.json`.
- **Benchmark Performance:** **98.23% accuracy** on synthetic validation columns; **0.880 Macro F1** on the official Saffron Bank benchmark dataset.

#### B. Cloud Contextual LLM (`FULL_CODE/backend/app/ai_classifier.py`)
- **Model & Provider:** Google Gemini (`gemini-2.5-flash` / `gemini-3.8-flash`) via the official `google-genai` SDK.
- **Role:** Contextual disambiguation of cryptic, non-standard, or abbreviated column headers (e.g., `mob_no`, `cust_id_num`, `bal_amt`).
- **Privacy Enforcement (Zero Raw PII Egress):** Raw customer records are **never transmitted** across the network. Only anonymized statistical summaries (string lengths, digit ratios, regex match percentages) and column names are sent.
- **Upgrade-Only Arbitration:** LLM outputs are strictly constrained by an arbitration engine: models can only elevate sensitivity rank (e.g., `INTERNAL` -> `CONFIDENTIAL`), but are strictly barred from downgrading deterministic rule discoveries or overriding human administrator approvals.

### 2. AI Coding Assistants Used
- **Antigravity / Google DeepMind Agentic Assistant:** Used for codebase exploration, test orchestration, schema alignment, and architectural validation.
- **Claude Code (Anthropic):** Used for synthetic training corpus generation scripts (`synth.py`) and regex entity pattern verification.
- **Human Engineering & Verification:** All system architecture, SQL AST rewriting algorithms, security boundaries, cryptographic hash chains, and business logic were engineered, debugged, and verified by the development team.

---

## Pre-built and third-party code

### 1. Pre-built Libraries & Frameworks
All external dependencies are industry-standard open-source packages managed through official package manifests (`requirements.txt`, `package.json`) and locked via lockfiles:

- **FastAPI (0.115.5) & Starlette:** High-performance web framework under MIT License.
- **Uvicorn (0.32.0):** Production ASGI server under BSD 3-Clause License.
- **SQLAlchemy (2.0.36):** Database toolkit and connection pooling under MIT License.
- **sqlglot (26.2.0):** Pure Python SQL AST parser, transpiler, and lineage analyzer under MIT License.
- **scikit-learn (1.5.2+) & NumPy:** Machine learning algorithms and numerical arrays under BSD 3-Clause License.
- **joblib (1.4.2):** Model serialization under BSD 3-Clause License.
- **google-genai (0.1.1):** Google GenAI Python SDK under Apache 2.0 License.
- **bcrypt (4.2.1) & cryptography:** Password hashing and cryptographic hash primitives under Apache 2.0 / BSD License.
- **React (18.3.1), Vite (5.4.11), Tailwind CSS (3.4.15):** Modern frontend SPA foundation under MIT License.
- **TanStack React Query (5.62.0):** Asynchronous state management and caching under MIT License.
- **Lucide React (0.460.0) & Recharts (2.13.3):** Icons and data visualization under MIT License.
- **pdfplumber & python-docx:** Document text extraction utilities under MIT License.

### 2. Pre-built Code & Templates
- No application logic was imported from past hackathons or preexisting personal projects. All application code was created specifically for the TalentAP Mega Hackathon 2026.
- Standard framework templates (Vite React TypeScript template and FastAPI starter conventions) were used for project scaffolding.

### 3. Benchmark Dataset
- **Saffron Bank Ltd Benchmark Pack:** Official synthetic banking dataset provided by the TalentAP Mega Hackathon organizers (9 tables, 129,260 synthetic records). Synthetic test data under Creative Commons Attribution 4.0 International (CC BY 4.0).

---

## Limitations

1. **Optimistic Query Concurrency Scope:**
   DreamGuard implements query pre-flight AST risk analysis (`/api/query/analyze`) and thread-safe in-memory LRU result caching (`execute_cached`). However, speculative optimistic background execution and multi-version concurrency control (OCC) across concurrent transactions are not implemented.
2. **Single-Node In-Memory Cache:**
   The result cache resides inside the FastAPI process memory (`OrderedDict`). In a horizontally scaled production deployment with multiple API replicas, a distributed caching layer (e.g., Redis Cluster) with cache invalidation pub/sub would be required.
3. **Supported Database Dialects:**
   DreamGuard provides verified connectors for SQLite, MySQL 8+, and PostgreSQL. Enterprise data warehouse adapters (Snowflake, Google BigQuery, Oracle Database, Microsoft SQL Server) are planned for future releases.
4. **Cloud LLM Network Dependency:**
   While the deterministic regex scanner and local scikit-learn ML model operate 100% offline, the optional Gemini AI classification layer requires outbound HTTPS egress to Google APIs. When internet access is unavailable, DreamGuard operates on local rule and ML engines without disruption.
5. **Legacy Document File Parsing:**
   Unstructured text scanning for legacy `.doc` binary documents requires the system binary `antiword` to be installed on the host. When unavailable, legacy `.doc` files are skipped, while `.docx`, `.pdf`, `.csv`, `.tsv`, and `.txt` files are fully processed.
