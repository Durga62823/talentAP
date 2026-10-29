# SentinelMask — Smart Data Masking System for PII Protection

> Discover sensitive data. Enforce access policies. Protect every query.

TalentAP Mega Hackathon 2026 · Problem Statement **B1** · built on the **official Saffron Bank Ltd dataset** (9 tables, 129,260 synthetic rows).

SentinelMask connects to SQLite, MySQL and PostgreSQL. It scans schema metadata and random row samples to tag PII (`PII_HIGH`, `PII_MEDIUM`, `FINANCIAL_CONFIDENTIAL`, …), then enforces **role-based dynamic masking on the server at query time**. The stored records are never changed.

```
<repo>/
  FULL_CODE/                  all application source code (submission)
    backend/                  FastAPI engine, importers, tests   (Python 3.12)
    frontend/                 React 18 + TypeScript + Vite + Tailwind console
    scripts/                  start.ps1 / start.sh, make_samples.py, postgres_setup.sql
  Datasets/                   official B1 pack from the organisers  (NOT committed)
  data/                       runtime state, SQLite copy, generated secrets/samples (NOT committed)
  .env.example                placeholder configuration
```

---

## 1. Dataset

| | |
|---|---|
| Source | TalentAP Mega Hackathon 2026, B1 data pack (Saffron Bank Ltd). Synthetic, CC BY 4.0 |
| Location | `Datasets/` at the repository root (override with `SENTINEL_DATASET_DIR`) |
| Tables | branches 60 · customers 5,000 · kyc_records 5,400 · international_customers 300 · accounts 8,000 · cards 6,000 · transactions 100,000 · support_tickets 3,000 · loan_applications 1,500 → **129,260** |
| Users | `Datasets/data/users.csv`: 9 official sample users (3 Admin, 3 Support, 3 Analyst) |

The dataset is **not** in this repository. SentinelMask never generates or edits records:
- **SQLite:** the official `sql/sqlite/saffron_bank.db` is copied into `data/targets/` (the shipped file is opened read-only). Row counts are verified after every copy.
- **MySQL / PostgreSQL:** the official `01_schema.sql` and `02_data.sql` scripts are executed statement by statement, and the counts are verified against the official figures.

The previous synthetic demo data (generator, demo DB, sample files) was removed. A copy is kept in the git-ignored `backups/pre_saffron_<timestamp>/`.

---

## 2. Setup and run (no Docker needed)

Prerequisites: Python 3.12+, Node 20+, the official pack in `Datasets/`. MySQL 8+/9 and PostgreSQL are optional.

```powershell
powershell -ExecutionPolicy Bypass -File FULL_CODE/scripts/start.ps1
```

```bash
./FULL_CODE/scripts/start.sh
```

These scripts create the venv, install dependencies, verify the dataset, build the console and serve everything at <http://127.0.0.1:8000>. On first start the app copies the official SQLite database, scans all 9 tables and seeds users, policies and grants.

Useful commands (run from `FULL_CODE/backend`, with the venv's Python):

```bash
python -m app.cli verify-dataset        # checks the official files + row counts (129,260)
python -m app.cli reset                 # rebuild app state on the official data (also in Settings)
python ../scripts/make_samples.py       # upload demo files built from official CSV rows -> data/samples/
python -m pytest -q                     # test suite
```

### MySQL (second backend)

1. Copy `.env.example` to `.env` (repository root) and set `SENTINEL_MYSQL_ADMIN_USER` and `SENTINEL_MYSQL_ADMIN_PASSWORD`. These are used **only** by the importer.
2. Run `python -m app.cli import-mysql`. It:
   - refuses to touch an existing `saffron_bank` holding non-dataset tables;
   - if the official tables already exist, requires `--replace` and first moves them into `saffron_bank_backup_<timestamp>` (reversible `RENAME TABLE`);
   - runs the official MySQL scripts and verifies all nine counts;
   - creates `sentinel_app@localhost` with **SELECT on `saffron_bank`** and write access **only** to a separate `saffron_imports` schema (for reviewed CSV imports). Its generated password is stored in `data/secrets/mysql_app.pw`.
3. Run `python -m app.cli reset`. This registers **Saffron Bank (MySQL)** as its own connection and scans it. If MySQL is down, the connection shows *unhealthy*; it is never silently swapped for another backend.

MySQL queries run inside `START TRANSACTION READ ONLY` with `MAX_EXECUTION_TIME`.

### PostgreSQL (optional third backend)

```bash
psql -h localhost -U postgres -v app_password="'choose-a-password'" -f FULL_CODE/scripts/postgres_setup.sql
PGPASSWORD=<owner password> python -m app.cli import-postgres --host localhost --user postgres --database saffron_bank
```

Then set `SENTINEL_DEMO_PG_*` in `.env` and reset, or add the connection in the console.

### Demo identities (local demo only)

Official users from `users.csv`, plus `compliance_lata` (our addition, since the pack defines no compliance user). `users.csv` contains no passwords, so each role has one demo password:

| Role | Users | Display Name & Email | Password | Role-Specific Experience & Access |
|---|---|---|---|---|
| Admin | `admin_anita`<br>`admin_farhan`<br>`admin_meera` | Anita Rao (`admin_anita@saffronbank.example`)<br>Farhan Qureshi (`admin_farhan@saffronbank.example`)<br>Meera Iyer (`admin_meera@saffronbank.example`) | `Admin@2026!` | **Security & Governance Workspace** (`/admin/overview`): Full governance, User Management with table grants, PII Discovery overrides, Masking Policy lifecycle, Tamper-Evident Audit Center, and Source-Data Integrity Verification. PAN/Aadhaar/SSN unmasking requires break-glass justification. (Internal SQL console available discretely). |
| Support | `support_ravi`<br>`support_neha`<br>`support_joseph` | Ravi Kumar (`support_ravi@saffronbank.example`)<br>Neha Gill (`support_neha@saffronbank.example`)<br>Joseph Pinto (`support_joseph@saffronbank.example`) | `Support@2026!` | **Customer Operations Workspace** (`/support/overview`): Customer Lookup, Customer 360 Profiles, 3,000 Support Tickets triage, and Personal Activity Log. Partial masking on cards (`4111-XXXX-XXXX-1111`), phone numbers (`********1099`), and emails. Running balances and loan applications are strictly redacted/denied. |
| Analyst | `analyst_kavya`<br>`analyst_arnab`<br>`analyst_hetal` | Kavya Hegde (`analyst_kavya@saffronbank.example`)<br>Arnab Dutta (`analyst_arnab@saffronbank.example`)<br>Hetal Shah (`analyst_hetal@saffronbank.example`) | `Analyst@2026!` | **Privacy-Preserving Analytics Workspace** (`/analyst/overview`): Visual Analytics, Monthly Transaction Trends (100k txns), Aggregate Explorer ($k \ge 5$ threshold enforced), Privacy-Screened CSV Reports, and My Activity. Names/phones redacted, cards HMAC pseudonyms (`hm_k1_...`), balances aggregate-only. |
| Compliance | `compliance_lata` | Lata Menon (`compliance_lata@saffronbank.example`) | `Compliance@2026!` | **Compliance Review Workspace** (`/admin/overview`): Reviews PII tags, audit trail hash chains, and integrity runs without raw PII exposure. Cannot alter policies, grants, or accounts. |

---

## 3. Role-Based Workspace Architecture

In accordance with Hackathon Problem Statement B1, **Live Query Playground has been removed as the primary default landing page**. Instead, Dream Guard delivers dedicated, role-specific workspaces tailored to the operational duties of each authenticated persona:

### A. Admin Dashboard (`/admin/*`)
- **Overview (`/admin/overview`):** Protected tables count, sensitive columns classified, active policies, security events timeline, database connection health, and source-data integrity status.
- **User Management (`/admin/users`):** Complete directory of all nine demo identities, role assignment editor, account active/suspend controls, and the database table grants matrix.
- **Data Discovery (`/admin/discovery`):** Scanned schemas, classified sensitive columns (`PII_HIGH`, `PII_MEDIUM`, `FINANCIAL_CONFIDENTIAL`), confidence ratings, and classification override review.
- **Masking Policies (`/admin/policies`):** Granular policy rules across categories and individual columns (`ALLOW`, `PARTIAL`, `REDACT`, `HASH`, `GENERALIZE`, `AGGREGATE_ONLY`, `BREAK_GLASS`).
- **Database & Tables (`/admin/connections`):** Multi-database connectors for SQLite, MySQL, and PostgreSQL.
- **Audit Center (`/admin/audit`):** Tamper-evident, hash-chained audit log with sequence validation (`verify-chain`).
- **Integrity Verification (`/admin/integrity`):** Cryptographic table fingerprinting to verify source data is never altered.
- **Settings (`/admin/settings`):** Global configurations and database re-seeding utilities.

### B. Customer Support Dashboard (`/support/*`)
- **Overview (`/support/overview`):** Customer service statistics, active masking policy banner, fast Customer ID lookup, and recent support cases preview.
- **Customer Lookup (`/support/lookup`):** Search by Customer ID (e.g. `CIF-00UKL72D`), Name, or Mobile Number with dynamic server-side partial masking.
- **Customer Profiles (`/support/profiles`):** Customer 360 dossier showing masked contact details, linked accounts with redacted running balances, linked payment cards (`4111-XXXX-XXXX-1111`) with permitted credit limits, and past support history. Zero raw PII exposure.
- **Support Tickets (`/support/tickets`):** Comprehensive inquiry management across 3,000 real Saffron Bank customer tickets with category, priority, and status filters.
- **Recent Activity (`/support/activity`):** Isolated audit stream of the authenticated support agent's lookups and outcomes (`GET /api/audit/self`).

### C. Data Analyst Dashboard (`/analyst/*`)
- **Overview (`/analyst/overview`):** Differential privacy metrics, k-anonymity guarantee status ($k \ge 5$), settled transaction totals, and channel distribution widgets.
- **Analytics (`/analyst/analytics`):** Interactive Recharts visualizations for payment rails volume (UPI, POS, ATM, IMPS, NEFT, etc.), success vs failure rates, and debit vs credit distribution.
- **Transaction Trends (`/analyst/trends`):** Time-series analysis across 100,000 transactions with monthly volume and transaction velocity charts.
- **Aggregate Explorer (`/analyst/explorer`):** Interactive aggregation builder. Demonstrates server-side k-anonymity enforcement ($k \ge 5$) and built-in interactive security stress tests that verify rejection of inference attacks (e.g. `CARD_NO LIKE '4111%'`).
- **Export Reports (`/analyst/reports`):** Pre-configured privacy-screened reports with verified CSV export derived strictly from server-screened aggregate data.
- **My Activity (`/analyst/activity`):** Personal audit log showing queries executed, durations, and any rejected inference attempts.

---

## 4. Masking on the official schema

The scanner combines column-name heuristics (including abbreviations), types, validated value patterns, pattern frequency over a **random** sample, and table context. The first N rows of `transactions` hide most of the PII that appears later, so random sampling matters.

| Column(s) | Detected as | How |
|---|---|---|
| `customers.mob_no`, `alt_mob`, `international_customers.us_phone` | PHONE | 10–15 digits; Indian `0`/`+91`/`91` prefixes; NANP |
| `customers.emailid` | EMAIL | format + name hint |
| `customers.addr_line1/2`, `us_addr` | POSTAL_ADDRESS | Indian forms (`H.No 20-50/12`, `Flat 408`, locality names) |
| `cust_nm`, `pita_nm`, `nominee_nm`, `NAME_ON_CARD`, `counterparty` | PERSON_NAME | abbreviation hints (`nm`), value shape; `branch_nm`/`employer_nm` excluded |
| `kyc_records.pan_no`, `aadhaar_no`, `international_customers.ssn` | NATIONAL_ID (PII_HIGH) | **shape-level** detection: the official Aadhaar numbers deliberately fail Verhoeff and SSNs use never-issued 9xx areas. For *protection* the shape is enough; real validity only raises confidence |
| `loan_applications.col_7` | NATIONAL_ID | undocumented column, detected **by value** (PAN shape) |
| `cards.CARD_NO` | CREDIT_CARD (PII_HIGH) | Luhn + issuer prefix |
| `accounts.account_no`, `cards.LINKED_ACCT` | ACCOUNT_NUMBER | name + 8–18 digits |
| `curr_bal`, `amount_inr`, `bal_after`, `CREDIT_LIMIT`, `OUTSTANDING_AMT`, `od_limit_inr`, `declared_income_inr`, `sanctioned_amt_inr`, `amt_requested_inr` | FINANCIAL_AMOUNT (FINANCIAL_CONFIDENTIAL, not personal) | a name hint is required; `int_rate_pct`/`roi_pct` stay public |
| `credit_score` | CREDIT_SCORE | banded in 50s (`700–749`) |
| `narration`, `ticket_text`, `notes`, `remarks`, `extra_info`, `kyc_meta` | FREE_TEXT_PII | **span masking**: cards, phones, UPI IDs, emails, PAN/Aadhaar/SSN shapes, JSON keys (`"uid": …`) and the payer-name segment of `UPI/CR/…/NAME/…`, `IMPS/…`, `NEFT/…` narrations. The rest stays readable |
| `transactions.ref_no` | FREE_TEXT_PII (mixed) | about 25% of values are card numbers; those are masked and `SAFFN…` references stay readable |
| `rrn`, `txn_id`, `CARD_REF`, `kyc_id` | not sensitive | reference context suppresses Aadhaar/phone look-alikes |
| `branches.branch_phone`, `branch_email` | ORG_CONTACT (internal) | organisational context: bank contacts, not personal data |

Policies are stored per role and category, with column-level overrides (e.g. Support may see `cards.CREDIT_LIMIT`). Precedence is deterministic, and every change is versioned and audited. Sensitive columns with no policy fail closed to REDACT, and tables that were never scanned cannot be queried.

The query engine accepts one read-only SELECT (sqlglot AST allow-list) and traces each output column to its source. It also blocks filtering, sorting or grouping on masked columns (inference protection) and enforces a row cap and timeout. Every query is recorded in a hash-chained, append-only audit log.

---

## 4. Verification (actually run on this machine)

| Check | Result |
|---|---|
| Nine official tables exist; counts match the README (transactions = 100,000; total 129,260) | ✅ SQLite (copy of official DB) · ✅ PostgreSQL 17 (official scripts via `import-postgres`) · ⏳ MySQL: importer and tests written, **not yet run** (waiting for admin credentials in `.env`) |
| Tables and columns appear dynamically (schema browser, query explorer, discovery) | ✅ SQLite, ✅ PostgreSQL |
| PII scan on official data | ✅ 9 tables, 120 columns, 38 sensitive; same results on 3 random samples (test) |
| Same record (`CIF-00UKL72D`) as Admin / Support / Analyst / Compliance | ✅ API tests + browser; **identical masked output on SQLite and PostgreSQL** for all four roles |
| Masking does not alter stored records | ✅ SQLite copy byte-identical after queries + attempted DML; fingerprint before/after on 13,000 rows; PG READ ONLY transaction blocks a DELETE even when the guard is bypassed |
| Backend tests | **121 passed** with PostgreSQL configured (115 passed / 13 skipped without PG and MySQL). The 7 MySQL tests skip until configured |
| Frontend | `tsc -b` clean; `vite build` succeeds |
| Legacy `.doc` | ✅ real Word-generated `.doc` (from official tickets) extracted with antiword |

Run the MySQL tests after importing:

```bash
SENTINEL_TEST_MYSQL_PASSWORD=<contents of data/secrets/mysql_app.pw> python -m pytest tests/test_mysql.py
```

---

## 5. Known limitations

- Names typed into free prose (e.g. a signature like "- Krupa" in `ticket_text`) are not detected. Only structured narration name segments are. Analyst redacts these columns entirely; Support and Compliance see span-masked text.
- Discovery is heuristic. Shape-level ID detection favours protection, so it can over-mask look-alike values. `branches.addr` is left public as a branch address.
- Bare 12-digit Aadhaar numbers outside a key (`"uid": …`) or a spaced/masked format are not flagged in free text, to avoid masking every RRN.
- The SQL subset is restricted: no sub-queries, CTEs, UNION or functions besides COUNT/SUM/AVG/MIN/MAX.
- Pseudonyms are not anonymous. HMAC values can be confirmed by anyone holding the key.
- The audit log is tamper-evident, not tamper-proof.
- Demo passwords are documented and bundled into the login page for one-click sign-in. Never deploy them.
- This is a prototype for demonstration. It is not certified for GDPR, HIPAA, PCI DSS or any other regime.

---

## 6. AI tools and pre-built code (coding-guideline disclosure)

- **AI assistance:** this project was designed and implemented with **Claude Code** (Anthropic, model Claude Opus 5.5) acting on the team's instructions: architecture, backend, frontend, tests and documentation. All code was run and tested locally; the results above are from those runs.
- **Pre-built code:** no project template was used. Third-party open-source libraries only, as listed in `FULL_CODE/backend/requirements.txt` (FastAPI, SQLAlchemy, sqlglot, Pydantic, argon2-cffi, cryptography, python-docx, PyMySQL, psycopg, pytest, uvicorn) and `FULL_CODE/frontend/package.json` (React, React Router, TanStack Query, Recharts, lucide-react, Tailwind CSS, Vite). Legacy `.doc` extraction uses the external `antiword` binary when installed.
- **Data:** only the organisers' synthetic dataset. No real personal data is used.
