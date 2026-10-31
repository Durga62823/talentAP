# 234 · B1: DreamGuard — Smart Data Masking System for PII Protection

> Automated PII discovery, local and cloud AI classification, and dynamic role-based data masking over financial databases without modifying stored records.

---

## What it does

### The Problem
Financial institutions store sensitive customer personally identifiable information (PII)—national identifiers (Indian PAN, Aadhaar, US SSN, UK National Insurance, Passports), payment card numbers (PCI-DSS), contact details, and account balances—across production databases. Exposing direct database access to internal teams (support agents, analysts, non-admin engineers) violates strict financial data compliance regulations (DPDP Act 2023, RBI Cyber Security Framework, GDPR, PCI-DSS v4) and creates major data leak risks. 

Traditional static data masking duplicates or permanently alters underlying tables, creating synchronization lag, storage bloat, and operational fragility. DreamGuard solves this by providing **dynamic, in-flight SQL query interception and server-side masking**: production database records remain completely untouched and immutable, while queries executed by different organizational roles receive real-time, context-aware masked views.

---

### Key Capabilities & Functionality Overview

```
+─────────────────────────────────────────────────────────────────────────────+
|                         DREAMGUARD CORE CAPABILITIES                        |
+─────────────────────────────────────────────────────────────────────────────+
| 1. Dynamic In-Flight SQL Interception  │ 7. File Upload & Document Import   |
| 2. 4-Tier Policy Precedence Engine     │ 8. Cryptographic SHA-256 Audit Log |
| 3. Multi-Engine PII Discovery Pipeline │ 9. Database Integrity Fingerprint  |
| 4. 16+ Algorithmic Entity Detectors    │ 10. Multi-Database Connectors      |
| 5. ABAC Purpose Binding & Break-Glass  │ 11. Multi-Role Query Playground    |
| 6. Differential Privacy (k ≥ 5 Groups) │ 12. 4 Role-Based Workspaces        |
+─────────────────────────────────────────────────────────────────────────────+
```

#### 1. Dynamic In-Flight SQL Query Interception & Lineage Tracing
- Intercepts all read-only SQL queries at the API gateway before they touch target databases.
- Deconstructs queries into Abstract Syntax Trees (AST) using `sqlglot`.
- Traces column lineage across table aliases, inner/left/cross joins, nested subqueries, CTEs, and projections.
- Injects safety constraints automatically, including enforced `LIMIT` clauses to prevent resource exhaustion.
- Enforces strict read-only execution modes (`START TRANSACTION READ ONLY` on MySQL/Postgres; read-only URI flags on SQLite) and rejects all DDL/DML mutation attempts (`DROP`, `ALTER`, `INSERT`, `UPDATE`, `DELETE`).

#### 2. Four-Tier Policy Precedence Cascade
When resolving which masking transformation to apply to a column, DreamGuard's policy engine (`app/policy.py`) evaluates a strict four-level precedence hierarchy:
1. **Explicit Column Override:** Precise rule assigned to `schema.table.column` for a specific role.
2. **Category-Level Policy:** Rule assigned to the column's detected PII category (e.g., all `CREDIT_CARD` columns).
3. **Sensitivity-Level Fallback:** Rule assigned to the data sensitivity tier (`PII_HIGH`, `PII_MEDIUM`, `FINANCIAL_CONFIDENTIAL`, `INTERNAL`, `PUBLIC`).
4. **Role Baseline Default:** The foundational security posture of the requesting user's role.

#### 3. Six Cryptographic & Privacy Transformation Primitives
- **`ALLOW`:** Raw, unmasked data access granted strictly to authorized roles (e.g., Admin).
- **`PARTIAL`:** Context-preserving partial masking that retains non-sensitive identifiers for customer verification:
  - Credit Cards: `4111-XXXX-XXXX-1111`
  - Indian Phone Numbers: `+91 ******1234`
  - Email Addresses: `r***@saffronbank.com`
  - Bank Accounts: `******4821`
  - Aadhaar: `XXXXXXXX1234`
- **`HASH_HMAC`:** Deterministic, keyed HMAC-SHA-256 pseudonymization. Anonymizes identifiers while preserving relational consistency, enabling data analysts to perform multi-table `JOIN` queries across pseudonymized keys without exposing real customer identity.
- **`REDACT`:** Complete replacement with uniform sentinel values (`[REDACTED]`).
- **`GENERALIZE`:** Reductive bucketing (e.g., timestamps truncated to dates; dates of birth generalized to age brackets or birth years).
- **`DROP`:** Complete column omission from the outgoing result set.
- **`BREAK_GLASS`:** Emergency unmasking workflow for high-risk fields (e.g., National IDs). Requests are blocked by default and require a mandatory, audited business justification and incident ticket reference to temporarily release raw data.

#### 4. Multi-Engine PII Discovery Pipeline
DreamGuard combines three complementary intelligence layers to detect sensitive data:
- **Layer 1: Deterministic Pattern & Checksum Engine (`app/scanner.py`):** Runs high-throughput regex scanners combined with mathematical checksum validators (Luhn algorithm for credit cards, Verhoeff algorithm for Indian Aadhaar, format validators for PAN, SSN, IBAN, IFSC, UPI, and email).
- **Layer 2: Local In-Process Machine Learning Classifier (`app/ml/`):** 100% offline, privacy-preserving hybrid ML model. Combines TF-IDF character n-gram Logistic Regression on column names with `HistGradientBoostingClassifier` trained on 37 statistical value features, calibrated via 5-fold isotonic regression (`CalibratedClassifierCV`). Inference runs in <5ms with zero external calls.
- **Layer 3: Cloud Contextual LLM (`app/ai_classifier.py`):** Optional Google Gemini integration for disambiguating cryptic, abbreviated column headers (e.g., `mob_no`, `cust_id_num`, `bal_amt`). Enforces **Zero Raw PII Egress**: only anonymized statistical summaries (character class distributions, digit ratios, length percentiles) are sent to the cloud.
- **Upgrade-Only Arbitration Engine:** Security guardrail ensuring that machine learning models and cloud AI can only elevate protection rank (e.g., `INTERNAL` → `CONFIDENTIAL`), never downgrade protection below deterministic rules or override human administrator reviews.

#### 5. Supported Financial & Identity PII Entity Catalog
| Entity Category | Detection Methodology | Typical Transformation |
| :--- | :--- | :--- |
| **Credit Card Number** | Regex + Luhn Checksum Algorithm (Visa, Mastercard, Amex, RuPay) | `PARTIAL` (`4111-XXXX-XXXX-1111`) |
| **Indian Aadhaar Number** | 12-digit format + Verhoeff Dihedral Checksum | `PARTIAL` / `BREAK_GLASS` |
| **Indian PAN** | 10-char regex pattern `[A-Z]{5}[0-9]{4}[A-Z]` | `BREAK_GLASS` / `REDACT` |
| **US Social Security Number** | 9-digit SSN format regex + area number validation | `REDACT` / `PARTIAL` |
| **Passport Number** | Standard international 8/9 alphanumeric format | `BREAK_GLASS` / `REDACT` |
| **Email Address** | RFC 5322 standard email address format | `PARTIAL` (`a***@domain.com`) |
| **Phone Number** | E.164 international format & Indian 10-digit mobile `[6-9]\d{9}` | `PARTIAL` (`+91 ******1234`) |
| **Bank Account Number** | 9-18 digit account number regex & column semantics | `PARTIAL` (`******4821`) |
| **IFSC Code** | Indian Financial System Code format `^[A-Z]{4}0[A-Z0-9]{6}$` | `ALLOW` / `INTERNAL` |
| **UPI ID / VPA** | Virtual Payment Address pattern `[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}` | `PARTIAL` (`u***@oksbi`) |
| **Customer ID** | Customer identifier patterns & relational key semantics | `HASH_HMAC` (Pseudonymized Key) |
| **Financial Amount / Balance** | Currency and numeric balance values | `REDACT` (for Support) / Aggregated |
| **Credit Risk Score** | CIBIL/FICO credit score ranges (300-900) | `REDACT` (Blocked for non-admins) |
| **Date of Birth** | ISO-8601 & standard calendar date formats | `GENERALIZE` (Age bracket / Year) |
| **Postal / Street Address** | Multi-token street, city, pin code address patterns | `PARTIAL` (City/PIN preserved) |
| **Person Name** | Name token distributions & column header heuristics | `PARTIAL` (`Asha V****`) |

#### 6. File Uploads, Document Scanning & Relational Data Import
- **Multi-Format Support:** Ingests structured datasets (`.csv`, `.tsv`) and unstructured documents (`.txt`, `.docx`, and legacy `.doc` via antiword).
- **Security Validation:** Enforces strict upload limits, MIME type verification, ZIP-bomb protection, and macro rejection.
- **Sensitive Entity Extraction:** Unstructured documents are scanned for sensitive entities with character offset locations and masked previews; raw files are purged immediately from disk.
- **Relational Table Generation:** Structured CSV datasets can be reviewed, edited for column classifications, and imported with bound-parameter inserts into connected databases as isolated tables (e.g., `imp_dataset`), immediately covered by the active masking policy engine.

#### 7. Differential Privacy & Aggregate Suppression ($k \ge 5$)
- Protects analytical aggregate queries (`COUNT`, `SUM`, `AVG`, `GROUP BY`) from microdata extraction attacks.
- Enforces an automated group-size threshold ($k \ge 5$): any aggregate cohort with fewer than 5 matching records is suppressed or flagged, preventing re-identification of individual banking customers through unique combinations of attributes.

#### 8. Attribute-Based Access Control (ABAC) & Purpose Binding
- Every query can be bound to an explicit business purpose via request headers (`X-DreamGuard-Purpose`, `X-DreamGuard-Ticket-ID`).
- Supported purposes: `CUSTOMER_SUPPORT`, `FRAUD_INVESTIGATION`, `DISPUTE_RESOLUTION`, `ANALYTICS_REPORTING`, `SECURITY_AUDIT`.
- Queries lacking a valid purpose default strictly to baseline masking policies; purpose elevation is validated against ticket identifiers (`_TICKET_RE = ^[A-Z][A-Z0-9]{1,15}-\d{1,12}$`).

#### 9. Cryptographic Tamper-Evident SHA-256 Audit Ledger
- Immutable security audit log (`app/audit.py`) tracking every user login, query execution, denied access attempt, policy modification, break-glass invocation, and data import.
- **Blockchain-Style Hash Chaining:** Every log entry cryptographically seals the SHA-256 hash of the preceding entry:
  $$\text{Record Hash}_i = \text{SHA256}(\text{Record Hash}_{i-1} \parallel \text{Timestamp} \parallel \text{Actor} \parallel \text{Action} \parallel \text{Details})$$
- Automated audit integrity verifier (`/api/audit/verify`) detects broken links, missing entries, or post-hoc record tampering.

#### 10. Source Database Row Hash Integrity Fingerprinting
- Mathematical proof of non-destructive masking (`app/integrity.py`).
- Computes deterministic, cumulative SHA-256 row fingerprints across target database tables.
- Compliance officers can run live integrity audits comparing initial database fingerprints with current table states to guarantee that dynamic masking interceptors have not altered underlying stored records.

#### 11. Multi-Database Connectors & Network Isolation
- Built-in connection pool manager (`app/connectors.py`) supporting SQLite, MySQL 8+, and PostgreSQL.
- Server-side host allow-list (`SENTINEL_ALLOWED_DB_HOSTS`) protects against Server-Side Request Forgery (SSRF).
- Dynamic schema introspection, table cataloging, and health monitoring.

#### 12. Interactive Multi-Role Query Playground
- Built-in simulation console allowing administrators and compliance reviewers to execute arbitrary SQL queries and view real-time side-by-side execution outputs across all 4 roles (`Admin`, `Support`, `Analyst`, `Compliance`).
- AST query analyzer displaying parsed syntax trees, identified sensitive columns, and execution metrics.

---

### Who Uses DreamGuard (Operational Personas)

1. **Security & Compliance Administrators (`ADMIN`):**
   - Discovers and catalogs sensitive columns across connected relational databases.
   - Authors and manages masking policies with the four-tier precedence engine.
   - Enforces table-level access grants and configures break-glass emergency unmasking policies.
   - Manages database connections, user provisioning, and file uploads.
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
   - Reviews PII discovery findings, AI classification logs, and compliance dossiers.

---

### What They See (Workspace Walkthrough)

DreamGuard is engineered as a zero-full-page-reload Single Page Application (SPA) built with React 18, React Router v6, Tailwind CSS, and TanStack React Query:

- **Admin Workspace (`/admin/*`):**
  - **Overview (`/admin/overview`):** Security dashboard displaying active connections, tables scanned, sensitive columns detected, active policies, query volume, exposure risk scores, and quick action links.
  - **User Management (`/admin/users`):** Manage accounts, assign roles, view table-level access grants, and configure SCIM/IdP tokens.
  - **Data Discovery (`/admin/discovery`):** Run automated schema scans, toggle ML/Gemini AI classifications, filter columns by sensitivity, and approve/override classifications.
  - **File Uploads (`/admin/uploads`):** Drag-and-drop file ingestion, document scanning, structured CSV review, and one-click import into connected databases.
  - **ML Model Studio (`/admin/ml-model`):** Model explainability dashboard, feature importance charts, training dataset metrics, and live inference playground.
  - **Masking Policies (`/admin/policies`):** Precedence matrix editor for column-level, category-level, and role-baseline policies.
  - **Database & Tables (`/admin/connections`):** Register new SQLite/PostgreSQL/MySQL databases, run health tests, and browse introspected schemas.
  - **Audit Center (`/admin/audit`):** Cryptographic audit log ledger with SHA-256 hash-chain verification tool.
  - **Integrity Verification (`/admin/integrity`):** Table row fingerprint verification guaranteeing 0% source data mutation.
  - **Query Playground (`/admin/playground`):** Interactive SQL console with multi-role output simulation and AST pre-flight analysis.
  - **Settings (`/admin/settings`):** System configuration, upload limits, cache parameters, and session controls.

- **Support Workspace (`/support/*`):**
  - **Support Overview (`/support/overview`):** Support queue metrics, active tickets, and recent customer interactions.
  - **Customer Lookup (`/support/lookup`):** Fast customer search by name, partial phone, or account number with server-side partial masking.
  - **Customer Profiles (`/support/profiles`):** Customer overview card displaying partially masked phone, email, address, and cards, with sensitive balances redacted.
  - **Support Tickets (`/support/tickets`):** Customer service ticket queue with linked masked customer identities.
  - **Recent Activity (`/support/activity`):** Support agent's personal query history and audit trail.

- **Analyst Workspace (`/analyst/*`):**
  - **Analyst Overview (`/analyst/overview`):** High-level summary of transaction patterns and aggregate metrics.
  - **Analytics Console (`/analyst/analytics`):** Interactive SQL querying with AST pre-flight analysis and HMAC-pseudonymized keys.
  - **Transaction Trends (`/analyst/trends`):** Time-series visualizations of deposit, withdrawal, and transfer volumes.
  - **Aggregate Explorer (`/analyst/explorer`):** Privacy-preserving cohort explorer with automated $k \ge 5$ threshold enforcement.
  - **Reports Center (`/analyst/reports`):** Exportable compliance-safe aggregate reports.
  - **My Activity (`/analyst/activity`):** Analyst's personal query execution logs.

- **Compliance Workspace (`/compliance/*` / `/admin/*` in Compliance Mode):**
  - Focused audit view covering **Overview**, **Data Discovery**, **ML Model Review**, **Masking Policies**, **Audit Center**, and **Integrity Verification**, strictly isolated from raw customer records.

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
| **Admin** | `admin_anita` | `Admin@2026!` | Security & Governance Console (`/admin/overview`) |
| **Support** | `support_ravi` | `Support@2026!` | Customer Support Portal (`/support/overview`) |
| **Analyst** | `analyst_kavya` | `Analyst@2026!` | Privacy-Preserving Analytics Workspace (`/analyst/overview`) |
| **Compliance** | `compliance_lata` | `Compliance@2026!` | Cryptographic Audit & Integrity Workspace (`/admin/overview`) |

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
npm --prefix FULL_CODE/frontend run build
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
| ├── File Ingestion & Doc Scanner: CSV/TXT/DOCX (app/uploads.py)             |
| ├── Audit System: SHA-256 hash-chained immutable log (app/audit.py)         |
| ├── Integrity Engine: Deterministic row fingerprinting (app/integrity.py)  |
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

1. **`FULL_CODE/backend/app/main.py`:** Application entry point, ASGI server configuration, CORS restrictions, and route registration across all 11 API routers.
2. **`FULL_CODE/backend/app/sql_guard.py`:** Parses SQL queries into Abstract Syntax Trees using `sqlglot`. Validates query semantics, prevents SQL injection, traces column lineage through aliases and joins, and enforces safe `LIMIT` injection.
3. **`FULL_CODE/backend/app/query_engine.py`:** Single enforcement pipeline: validates table grants -> rewrites AST -> executes query within a read-only transaction -> applies server-side dynamic masking in memory -> appends to cryptographic audit chain.
4. **`FULL_CODE/backend/app/policy.py`:** Policy resolution engine implementing a 4-tier precedence cascade: `Column Policy > Category Policy > Sensitivity Level > Role Default`.
5. **`FULL_CODE/backend/app/masking.py`:** Memory-level transformation primitives (`ALLOW`, `PARTIAL`, `HASH_HMAC`, `REDACT`, `DROP`, `GENERALIZE`, `BREAK_GLASS`).
6. **`FULL_CODE/backend/app/uploads.py`:** Secure file ingestion engine handling CSV, TSV, TXT, DOCX, and DOC uploads, entity scanning, and database import table generation.
7. **`FULL_CODE/backend/app/connectors.py`:** Connection pool manager for SQLite, MySQL, and PostgreSQL with a thread-safe LRU result cache (`execute_cached`).
8. **`FULL_CODE/backend/app/scanner.py`:** Deterministic pattern recognition engine combining regular expressions and mathematical checksum algorithms (Luhn for Credit Cards, Verhoeff for Indian Aadhaar, format validators for PAN, SSN, IBAN, IFSC, Email, Phone).
9. **`FULL_CODE/backend/app/ml/`:** Local in-process machine learning classifier (`model.py`, `featurize.py`, `train.py`, and trained model artifact `artifacts/pii_model.joblib`).
10. **`FULL_CODE/backend/app/ai_classifier.py`:** Optional Google Gemini cloud LLM client with strict privacy guardrails and upgrade-only arbitration logic.
11. **`FULL_CODE/backend/app/audit.py`:** Cryptographic SHA-256 hash-chained immutable audit log where each event records the SHA-256 hash of the preceding entry.
12. **`FULL_CODE/backend/app/integrity.py`:** Computes cumulative row hashes across database tables to mathematically prove zero modification to source data.
13. **`FULL_CODE/frontend/src/`:** React 18 Single Page Application with dedicated role-specific operational workspaces (`/admin/*`, `/support/*`, `/analyst/*`, `/compliance/*`).

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
- **bcrypt (4.2.1), argon2-cffi & cryptography:** Password hashing and cryptographic hash primitives under Apache 2.0 / BSD License.
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
