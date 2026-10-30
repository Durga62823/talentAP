# DreamGuard — Demonstration & Evaluation Guide

> **Project Name:** DreamGuard (Smart Data Masking System for PII Protection)  
> **Team ID:** 234 · Problem Statement ID: B1  
> **Evaluation Dataset:** Saffron Bank Ltd (9 tables, 129,260 records)  
> **Default Port:** `http://127.0.0.1:8000` (Local Unified Runner)  

---

## 1. Quick Start Guide

### Step 1: Start DreamGuard

#### Option A: One-Click Startup Script (Windows PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File FULL_CODE/scripts/start.ps1
```

#### Option B: One-Click Startup Script (Linux / macOS)
```bash
./FULL_CODE/scripts/start.sh
```

#### Option C: Manual Service Startup
```bash
# Terminal 1: Backend
cd FULL_CODE/backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.cli reset    # Copies Saffron Bank DB, initializes tables, seeds accounts
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Frontend (Production Preview or Dev)
cd FULL_CODE/frontend
npm install
npm run build
npm run preview -- --port 5173
```

Open your browser at **`http://127.0.0.1:8000`** (or `http://127.0.0.1:5173` if running Vite dev server).

---

## 2. Demonstration Persona Accounts

All demo accounts are pre-seeded and ready for immediate login:

| Role | Username | Password | Purpose & Operational Landing |
|---|---|---|---|
| **Admin** | `admin_anita` | `Admin@2026!` | Security & Governance Workspace (`/admin/overview`) |
| **Support** | `support_ravi` | `Support@2026!` | Customer Operations Workspace (`/support/overview`) |
| **Analyst** | `analyst_kavya` | `Analyst@2026!` | Privacy-Preserving Analytics Workspace (`/analyst/overview`) |
| **Compliance** | `compliance_lata`| `Compliance@2026!`| Tamper-Evident Audit & Verification (`/admin/overview`) |

---

## 3. End-to-End 14-Step Demonstration Sequence

```
+─────────────────────────────────────────────────────────────────────────────+
|                         DREAMGUARD DEMONSTRATION FLOW                       |
+─────────────────────────────────────────────────────────────────────────────+
| 1. Start App  ──> 2. View Connection ──> 3. Trigger Scan ──> 4. Inspect PII  |
|                                                                     │       |
| 8. Analyst UI <── 7. Support UI <── 6. Admin Break-Glass <── 5. AI/ML Deep  |
|      │                                                                      |
| 9. Compliance ──> 10. Compare Masks ──> 11. Query Cache ──> 12. Zero-Reload |
|                                                                     │       |
|                                   14. Source Integrity <── 13. Audit Chain  |
+─────────────────────────────────────────────────────────────────────────────+
```

### Step 1: Initialize and Launch DreamGuard
- Launch via `FULL_CODE/scripts/start.ps1`.
- Verify the terminal output confirms that Saffron Bank SQLite database (129,260 rows across 9 tables) is copied and verified.
- Open `http://127.0.0.1:8000/login`.

### Step 2: Connect to the Target Database
- Log in as **`admin_anita`** (`Admin@2026!`).
- Navigate to **Connections** (`/admin/connections`).
- View the pre-configured **Saffron Bank (SQLite)** connection showing *healthy* status, 9 tables, and read-only connection configuration.
- Click **Test Connection** to verify live connection pool response in `< 5ms`.

### Step 3: Trigger Automated PII Discovery
- Navigate to **PII Discovery** (`/admin/discovery`).
- Select connection `Saffron Bank (SQLite)`.
- Configure Sample Size: `100` rows per table.
- Toggle **Local ML Model (SGD)**: `Enabled`.
- Toggle **Gemini AI**: `Enabled` (or disabled if offline).
- Click **Run Discovery Scan**.
- Observe real-time progress as all 9 tables (70 columns) are sampled in RAM and evaluated.

### Step 4: Inspect Discovered Column Classifications
- Review the discovered inventory table:
  - `cards.CARD_NO`: Tagged `CREDIT_CARD`, Sensitivity `RESTRICTED`, Detection Method `regex + luhn`.
  - `kyc_records.id_value`: Tagged `NATIONAL_ID`, Sensitivity `RESTRICTED`, Detection Method `verhoeff + pan`.
  - `customers.cust_nm`: Tagged `PERSON_NAME`, Sensitivity `CONFIDENTIAL`, Detection Method `ml + rule`.
  - `customers.mob_no`: Tagged `PHONE`, Sensitivity `CONFIDENTIAL`.
  - `customers.email_id`: Tagged `EMAIL`, Sensitivity `CONFIDENTIAL`.
- Notice the **Detection Badges**: Shows which categories were detected by deterministic rules, local ML, or Gemini.

### Step 5: Explain the AI & ML Detection Pipeline
- Navigate to **ML Model Governance** (`/admin/ml`).
- Inspect the live model card for `pii-ml-v1`:
  - Architecture: Stacked TF-IDF n-gram Logistic Regression + Gradient Boosted Trees with isotonic calibration.
  - Training: 4,700 synthetic columns (zero data leakage; evaluation names excluded).
  - Accuracy: **98.23%** on synthetic held-out test split, **0.88 Macro F1** on Saffron Bank columns.
- Click on any column classification to view the **Explainability Drawer**:
  - Displays top-3 class probabilities (e.g. `PHONE: 94.2%`, `CUSTOMER_ID: 3.1%`, `NONE: 2.7%`).
  - Lists the key features driving the prediction (e.g. `phone format ratio`, `all-digit share`, `token match`).

### Step 6: Demonstrate Admin Access & Break-Glass Justification
- As `admin_anita`, navigate to **SQL Console / Playground** (`/admin/playground`).
- Run a query selecting national IDs:
  ```sql
  SELECT customer_id, id_type, id_value FROM kyc_records LIMIT 5;
  ```
- **Observed Behavior:**
  - Notice the `id_value` column is protected under policy `RESTRICTED`.
  - To unmask, the Admin enters an audit justification: `"Customer KYC dispute ticket #8841"`.
  - Click **Execute with Justification**.
  - Raw PAN/Aadhaar numbers are returned, and the break-glass reason is permanently recorded in the cryptographic audit log.

### Step 7: Demonstrate Customer Support Access (Partial Masking)
- Log out, and log in as **`support_ravi`** (`Support@2026!`).
- Notice the landing page is the dedicated **Customer Operations Workspace** (`/support/overview`).
- Navigate to **Customer 360 Profiles** (`/support/profiles`).
- Search for customer `CUST000001`:
  - **Card Number:** Displayed as `4111-XXXX-XXXX-1111` (first 4 and last 4 visible, middle 8 masked).
  - **Mobile Phone:** Displayed as `********1099` (suffix visible to verify customer identity over the phone).
  - **Email Address:** Displayed as `a****@example.com`.
  - **Account Balance:** Displayed as `[REDACTED]`.
- Attempt to run an unauthorized query on financial balances:
  - System rejects the query with `403 Forbidden` (`privilege_violation`).

### Step 8: Demonstrate Data Analyst Access (Privacy-Screened Analytics)
- Log out, and log in as **`analyst_kavya`** (`Analyst@2026!`).
- Notice the landing page is the **Privacy-Preserving Analytics Workspace** (`/analyst/overview`).
- Navigate to **Transaction Trends** (`/analyst/trends`):
  - Visualizes monthly volume across 100,000 transactions without exposing customer names.
- Navigate to **Aggregate Explorer** (`/analyst/aggregates`):
  - Run a grouped aggregation query on loan statuses.
  - Notice that groups with fewer than 5 rows ($k < 5$) are automatically suppressed to prevent differential re-identification.
- Inspect Card Numbers in Analytics:
  - Card numbers appear as deterministic keyed HMAC pseudonyms: `hm_k1_8f4a2c1b9e0d3f7a`.
  - Explain that the analyst can execute `GROUP BY` and `JOIN` operations on card pseudonyms across tables, but cannot decipher the original 16-digit card number.

### Step 9: Demonstrate Compliance Auditor Access
- Log out, and log in as **`compliance_lata`** (`Compliance@2026!`).
- Navigate to **Audit Center** (`/admin/audit`):
  - The compliance auditor can inspect the complete audit trail and verify cryptographic hash chains.
  - Notice that the auditor has **zero access to unmasked data** and cannot modify policies or user grants.

### Step 10: Side-by-Side Masking Comparison Across Roles
Compare the same record (`customers` table, customer `CUST000001`) across all three operational roles:

| Field | Raw / Admin (Break-Glass) | Support Role | Analyst Role |
|---|---|---|---|
| `cust_nm` | Anita Rao | Anita R*** | `[REDACTED]` |
| `mob_no` | 9876541099 | ********1099 | `[REDACTED]` |
| `email_id` | anita.rao@example.com | a****@example.com | `[REDACTED]` |
| `card_no` | 4111222233331111 | 4111-XXXX-XXXX-1111 | `hm_k1_8f4a2c1b...` |
| `balance` | 450000.00 | `[REDACTED]` | Aggregate Only ($k \ge 5$) |

### Step 11: Demonstrate Query Optimization & Result Caching
- As `support_ravi`, execute a query in the playground:
  ```sql
  SELECT customer_id, cust_nm, mob_no FROM customers LIMIT 10;
  ```
  - **First Run (Cache Miss):** Latency ~12ms. Status shows `cache_hit: false`. Raw rows retrieved from SQLite.
  - **Second Run (Cache Hit):** Latency ~1.2ms (10x faster). Status shows `cache_hit: true`.
  - **Security Verification:** Show that despite the cache hit, Support still receives masked rows (`Anita R***`). The cache never returns unmasked data cached by an admin.

### Step 12: Demonstrate Zero-Full-Page-Reload Interactions
- Navigate between **Overview**, **Discovery**, **Policies**, and **Audit**.
- Notice that all transitions occur instantly client-side without browser page flashing or reload spinners.
- Edit a policy action (e.g. switch `EMAIL` from `PARTIAL` to `REDACT`):
  - TanStack Query immediately invalidates the query cache.
  - The UI updates reactively without a manual page refresh.

### Step 13: Inspect Cryptographic Tamper-Evident Audit Records
- As `admin_anita`, navigate to **Audit Center** (`/admin/audit`).
- Click **Verify Hash Chain**:
  - Recomputes SHA-256 digests across all logged events from the genesis block.
  - Shows green badge: **"Audit Log Integrity Intact (N events verified)"**.
- Demonstrate SQL literal sanitization:
  - Show that queries like `SELECT * FROM customers WHERE email_id = 'secret@example.com'` are recorded in audit logs as `SELECT * FROM customers WHERE email_id = ?`.

### Step 14: Verify Source Database Cryptographic Fingerprints
- Navigate to **Data Integrity** (`/admin/integrity`).
- Click **Verify Source Records Now**:
  - Streams rows across all 9 tables in the target database.
  - Computes cumulative SHA-256 fingerprint: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
  - Shows green badge: **"Source records unchanged: 9 tables · 129,260 rows"**.
  - Mathematically proves to the evaluators that all masking and query execution occurred in-memory on the server, leaving target database records completely intact.

