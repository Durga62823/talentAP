# DreamGuard — Features & Implementation Guide

> **Document Version:** 1.0.0  
> **Target Evaluation Environment:** Hackathon AI Evaluation & Technical Verification  
> **Source Directory Base:** `FULL_CODE/backend/app`, `FULL_CODE/frontend/src`  

---

## Overview

This document provides a comprehensive technical breakdown of every major feature implemented in **DreamGuard**. For each capability, it details the engineering design, source file locations, key functions, cryptographic algorithms, edge cases handled, and automated test verification.

---

## 1. Authentication & Role-Based Access Control (RBAC)

### Technical Description
DreamGuard implements a secure, token-based authentication system supporting dual transport: HTTP-only session cookies and `Authorization: Bearer <token>` headers. Roles are strictly enforced on the server for every endpoint.

### Primary Source Files
- Backend: `FULL_CODE/backend/app/security.py`, `FULL_CODE/backend/app/api/auth.py`
- Frontend: `FULL_CODE/frontend/src/lib/auth.ts`, `FULL_CODE/frontend/src/pages/Login.tsx`
- ORM Tables: `users`, `roles`, `sessions` in `FULL_CODE/backend/app/metadb.py`

### Implementation Highlights
- **Password Security:** Passwords verified via `bcrypt.checkpw(password.encode(), user.password_hash.encode())`.
- **Session Tokens:** Generated via `secrets.token_hex(32)`. Only the SHA-256 digest (`token_hash`) is stored in the `sessions` table. A database leak reveals no usable session tokens.
- **Role Permissions:** Stored as JSON arrays in `roles.permissions`:
  - `admin`: Full access (`query:execute`, `audit:read`, `scan:run`, `classification:review`, `integrity:run`, `raw:break_glass`, `policy:write`, `conn:write`)
  - `support`: Customer operations (`query:execute`)
  - `analyst`: Privacy-screened analytics (`query:execute`)
  - `compliance`: Audit and verification (`audit:read`, `integrity:run`, `classification:review`)
- **Table Grants:** Fine-grained table-level authorization per connection stored in `table_grants`. A user cannot query a table unless their role has an explicit grant on that connection.

### Verified Test Evidence
- `FULL_CODE/backend/tests/test_authz.py`: Tests login, logout, invalid credentials, token revocation, expired sessions, and role privilege boundaries. (100% passing).

---

## 2. Multi-Backend Database Connectivity

### Technical Description
DreamGuard connects to multiple database engines using SQLAlchemy connection pooling and dialect-specific read-only query wrappers.

### Primary Source Files
- `FULL_CODE/backend/app/connectors.py`
- `FULL_CODE/backend/app/saffron.py`
- `FULL_CODE/backend/app/api/databases.py`

### Implementation Details
- **SQLite Adapter (`SqliteAdapter`):**
  - Manages target SQLite databases (e.g. Saffron Bank 129,260 rows).
  - Enforces `PRAGMA query_only = ON` on connection checkout.
  - Automatically handles connection pooling via `QueuePool` (avoiding `SingletonThreadPool` connection closures during concurrent queries).
- **MySQL Adapter (`MySQLAdapter`):**
  - Connects to MySQL 8+ / 9 using `PyMySQL`.
  - Executes queries inside `START TRANSACTION READ ONLY`.
  - Enforces hard server-side timeouts via `SET SESSION MAX_EXECUTION_TIME = <ms>`.
  - Enforces connection-level isolation: application user `sentinel_app` has `SELECT` privileges only on `saffron_bank` and isolated staging privileges on `saffron_imports`.
- **PostgreSQL Adapter (`PostgreSQLAdapter`):**
  - Connects via `psycopg2`.
  - Queries execute under a dedicated least-privilege `sentinel_app` user.
- **Connection Health Checks:** Endpoint `POST /api/databases/{id}/test` tests live socket connectivity and measures latency without executing data reads.

### Verified Test Evidence
- `FULL_CODE/backend/tests/test_performance.py`: Verifies concurrent multi-threaded query execution across connection pools without race conditions.
- `FULL_CODE/backend/tests/test_mysql.py`, `tests/test_postgres.py`: Verify integration against live database servers when configured.

---

## 3. Schema Discovery & In-Memory Sampling

### Technical Description
DreamGuard inspects connected database schemas, enumerates tables and columns, and samples data to detect PII.

### Primary Source Files
- `FULL_CODE/backend/app/discovery.py`
- `FULL_CODE/backend/app/connectors.py` (`sample()`)
- `FULL_CODE/frontend/src/pages/Discovery.tsx`

### Implementation Details
- **In-Memory Sampling:** `adapter.sample(schema, table, columns, sample_size=100)` retrieves up to 100 random rows per table using database-specific random ordering (`RANDOM()` in SQLite/PostgreSQL, `RAND()` in MySQL).
- **Zero Raw Data Retention:**
  ```python
  # discovery.py lines 101-112
  feats = extract_features(table, col.name, col.type, col.nullable, col.primary_key, samples[col.name], r)
  ...
  del samples  # raw sample values are never retained
  ```
  Raw row values are explicitly deleted in memory immediately after feature extraction. They are never written to disk, never persisted in metadata tables, and never transmitted across network boundaries.

### Verified Test Evidence
- `FULL_CODE/backend/tests/test_scanner.py`: Verifies table discovery and column sampling across all 9 Saffron Bank tables.

---

## 4. Deterministic Rule Scanner

### Technical Description
A high-throughput, rule-based PII detector combining regular expressions, structural checksum algorithms, and SQL metadata heuristics.

### Primary Source Files
- `FULL_CODE/backend/app/scanner.py`
- `FULL_CODE/backend/app/entities.py`

### Supported PII Categories & Validation Algorithms
1. **Credit Cards (`CREDIT_CARD`):** Regex pattern matching Major Card Brands (Visa, MasterCard, Amex, Discover, RuPay) verified with the **Luhn Algorithm** (`luhn_checksum`). Sensitivity: `RESTRICTED`.
2. **Aadhaar Numbers (`NATIONAL_ID`):** 12-digit Indian national identity numbers validated with the **Verhoeff Checksum Algorithm** (`verhoeff_checksum`). Sensitivity: `RESTRICTED`.
3. **Permanent Account Number (`NATIONAL_ID`):** Indian PAN pattern `[A-Z]{5}[0-9]{4}[A-Z]`. Sensitivity: `RESTRICTED`.
4. **Social Security Number (`NATIONAL_ID`):** US SSN format `\d{3}-\d{2}-\d{4}` with area/group number validation rules. Sensitivity: `RESTRICTED`.
5. **Passports (`NATIONAL_ID`):** Indian passport format (`[A-Z][0-9]{7}`) and US passport formats. Sensitivity: `RESTRICTED`.
6. **Bank Account Numbers (`BANK_ACCOUNT`):** 9 to 18-digit account strings combined with account-related column naming heuristics. Sensitivity: `CONFIDENTIAL`.
7. **International Bank Account Number (`BANK_ACCOUNT`):** IBAN format validated via modulo 97 checksum. Sensitivity: `CONFIDENTIAL`.
8. **Indian Financial System Code (`ORG_CONTACT`):** IFSC format `^[A-Z]{4}0[A-Z0-9]{6}$`. Sensitivity: `INTERNAL`.
9. **UPI Identifiers (`UPI_ID`):** Virtual Payment Addresses matching `[\w.-]+@[\w.-]+`. Sensitivity: `CONFIDENTIAL`.
10. **Email Addresses (`EMAIL`):** Standard RFC 5322 regex. Sensitivity: `CONFIDENTIAL`.
11. **Phone Numbers (`PHONE`):** E.164 and localized Indian/US phone formats with digit count validation. Sensitivity: `CONFIDENTIAL`.
12. **Person Names (`PERSON_NAME`):** Multi-token alphabetic shapes with honorific/title heuristics. Sensitivity: `CONFIDENTIAL`.
13. **Postal Addresses (`POSTAL_ADDRESS`):** Street and location keyword patterns with zip/pincode structures. Sensitivity: `CONFIDENTIAL`.
14. **Dates of Birth (`DATE_OF_BIRTH`):** Date columns where distribution analysis indicates adult birth years (18–100 years prior to current year). Sensitivity: `CONFIDENTIAL`.
15. **Credit Scores (`CREDIT_SCORE`):** Integer distributions bounded within the 300–900 FICO/CIBIL range. Sensitivity: `CONFIDENTIAL`.

### Verified Test Evidence
- `FULL_CODE/backend/tests/test_scanner.py`: Full test coverage verifying detection accuracy, checksum rejection of invalid card/Aadhaar numbers, and false positive mitigation.

---

## 5. Local Stacking Machine Learning Classifier

### Technical Description
An in-process, dual-model machine learning classifier trained to identify column PII categories without external network dependencies.

### Primary Source Files
- `FULL_CODE/backend/app/ml/model.py`
- `FULL_CODE/backend/app/ml/featurize.py`
- `FULL_CODE/backend/app/ml/synth.py`
- `FULL_CODE/backend/app/ml/train.py`
- Artifacts: `FULL_CODE/backend/app/ml/artifacts/pii_model.joblib`, `model_card.json`

### Model Architecture
- **Name Model:** `TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))` feeding a `LogisticRegression` classifier on `"table column"` strings. Produces an out-of-fold probability distribution over all 16 target classes.
- **Value Model:** `HistGradientBoostingClassifier` trained on 37 sanitized statistical features concatenated with the name model's predicted class probabilities (Stacked Ensemble).
- **Probability Calibration:** Wrapped in `CalibratedClassifierCV(method="isotonic", cv=5)` to produce well-calibrated confidence scores.
- **Inference Speed:** Average latency < 5ms per column. Runs fully inside the Python process using `scikit-learn` and `joblib`.
- **Explainability:** Generates top-3 class probabilities and feature importance contribution vectors for every prediction.

### Training & Evaluation Metrics
- **Training Data:** 4,700 synthetic columns generated via `synth.py` using `Faker` (locales `en_IN` and `en_US`). Zero real customer data used. Column names in the evaluation set were strictly excluded from training.
- **Held-Out Synthetic Test Split:** Accuracy: **98.23%**, Macro F1: **0.9193**.
- **Official Saffron Bank Benchmark:** Evaluated on all 70 columns against hand-labelled ground truth (`app/ml/eval/saffron_labels.csv`). Macro F1: **0.880**.

### Verified Test Evidence
- `FULL_CODE/backend/tests/test_ml_model.py`: Verifies model loading, inference correctness, confidence thresholds, and explainability payloads. (100% passing).

---

## 6. LLM-Based Contextual Detection (Google Gemini API)

### Technical Description
An optional cloud AI classification layer using Google Gemini Flash models to disambiguate cryptic column names and complex data distributions.

### Primary Source Files
- `FULL_CODE/backend/app/ai_classifier.py`
- `FULL_CODE/backend/app/ai_features.py`
- `FULL_CODE/backend/tests/test_ai_classification.py`

### Zero Raw PII Egress Guarantee
The external Gemini API **never receives raw database rows**. Instead, `app/ai_features.py` extracts a strictly sanitized statistical descriptor:
- Column name and SQL data type.
- Null ratio and uniqueness ratio.
- String length distribution (min, max, mean, median).
- Character class ratios (alpha, numeric, whitespace, symbol).
- Pattern match ratios (regex match frequency).
- Numeric magnitude statistics (log mean, integer ratio).

### API Integration Specifications
- **Provider & SDK:** Google GenAI (`google.genai` SDK).
- **Models:** Default `gemini-2.5-flash` (configurable to `gemini-3.8-flash` via `GEMINI_MODEL`).
- **Structured Response:** Constrained by `GenerateContentConfig(response_mime_type="application/json", response_json_schema=response_schema(), temperature=0.0)`.
- **Resilience:** Exponential backoff with jitter (up to 2 retries). On rate limits (HTTP 429), timeouts, or missing API keys, raises `AIUnavailable` gracefully, allowing the scan to complete cleanly using the deterministic rule baseline.

### Verified Test Evidence
- `FULL_CODE/backend/tests/test_ai_classification.py`: Tests sanitized feature extraction, JSON parsing, prompt validation, and offline fallbacks using mock clients.

---

## 7. Upgrade-Only Arbitration Engine

### Technical Description
An arbitration mechanism that reconciles outputs from the deterministic rule scanner, the local ML model, and the external Gemini LLM.

### Primary Source Files
- `FULL_CODE/backend/app/ai_classifier.py` (`upgrade_decision`)
- `FULL_CODE/backend/app/discovery.py`

### Decision Matrix & Rules
The engine enforces a strict mathematical hierarchy:
1. **Consensus (`AGREES`):** Model agrees with current category. No change required.
2. **Human Immunity (`HUMAN_REVIEWED`):** If a human administrator previously approved or edited the column, the automated model is ignored.
3. **Downgrade Prevention (`KEPT_RULE`):** If the model suggests a sensitivity rank equal to or lower than the rule scanner, the rule is retained. An AI model can never silently downgrade a column from `RESTRICTED` to `PUBLIC`.
4. **Confidence Gating (`LOW_CONFIDENCE`):** If model confidence is below `min_confidence` (default 0.75) or flagged with `needs_review`, the upgrade is paused and sent to the human review queue.
5. **Strict Upgrade (`APPLIED`):** Only when the model proposes a strictly higher sensitivity rank with confidence $\ge 0.75$, the classification is updated and flagged as `+ ml` or `+ gemini`.

---

## 8. Dynamic Role-Based Data Masking Engine

### Technical Description
A server-side data transformation engine that applies masking policies to SQL query result rows before JSON serialization.

### Primary Source Files
- `FULL_CODE/backend/app/masking.py`
- `FULL_CODE/backend/app/policy.py`
- `FULL_CODE/backend/tests/test_masking.py`

### Supported Masking Transformations
- **`PARTIAL` (Structural Masking):**
  - Credit Cards: Preserves first 4 and last 4 digits: `4111-XXXX-XXXX-1111`
  - Phone Numbers: Masks all but last 4 digits: `********1099`
  - Email Addresses: Masks mailbox prefix: `a****@example.com`
  - Names: Masks surname: `Anita R***`
  - Aadhaar: Preserves last 4 digits: `XXXXXXXX1234`
  - PAN: Preserves first 2 and last 2 characters: `ABXXXXXX1Z`
- **`HASH_HMAC` (Cryptographic Pseudonymization):**
  - Applies HMAC-SHA-256 using a server-side secret key rotated from `data/secrets/`.
  - Format: `hm_<key_id>_<hex_digest[:16]>`.
  - **Relational Preservation:** Deterministic hashing preserves foreign key equality across queries. Analysts can join `customers.id` to `transactions.customer_id` without discovering the actual customer ID.
- **`REDACT`:** Completely replaces value with `[REDACTED]`.
- **`DROP`:** Replaces value with `None` or `0.0`.
- **`ALLOW`:** Returns raw value for authorized roles.

---

## 9. SQL Guard AST Parser & Query Rewriter

### Technical Description
An Abstract Syntax Tree (AST) query inspection and rewriting engine powered by `sqlglot`.

### Primary Source Files
- `FULL_CODE/backend/app/sql_guard.py`
- `FULL_CODE/backend/app/query_engine.py`
- `FULL_CODE/backend/tests/test_query_security.py`

### Key Security Enforcements
1. **Grammar Restriction:** Rejects multiple statements (semicolon chaining), non-SELECT DDL/DML, and procedural SQL.
2. **Lineage Tracing:** Maps every projected column in complex queries (joins, subqueries, aliases, CTEs) back to its physical source table and column to apply the correct masking policy.
3. **Automatic Row Caps:** Injects `LIMIT 500` if absent or clamps requested limits to `max_result_rows`.
4. **Predicate Protection:** Prohibits unauthorized users from filtering (`WHERE`, `HAVING`) on masked columns to prevent side-channel inference attacks (e.g. `WHERE salary > 100000`).
5. **Differential Privacy Aggregation ($k \ge 5$):** Enforces minimum group size on `GROUP BY` queries to prevent single-row microdata isolation.

---

## 10. Result Cache & Query Optimization

### Technical Description
An in-memory LRU + TTL query caching system that accelerates repeated queries without compromising data masking.

### Primary Source Files
- `FULL_CODE/backend/app/connectors.py` (`execute_cached`)
- `FULL_CODE/backend/app/query_engine.py`
- `FULL_CODE/backend/tests/test_performance.py`

### Implementation Details
- Caches raw query result tuples in a thread-safe LRU cache (TTL: 60s, max 128 entries).
- **Multi-Tenant Security Guarantee:** The cache stores raw tuples. On a cache hit, the query engine extracts the cached raw rows and **dynamically runs them through the caller's role-specific Masking Engine**. A cache hit by a Support user will receive partial masking even if the cache was warmed by an Admin user.
- **Auditing Integrity:** Cache hits generate unique audit log entries with `cache_hit: true`. No query bypasses audit logging.

---

## 11. Zero-Full-Page-Reload User Interface

### Technical Description
A high-performance Single Page Application (SPA) built with React 18, Vite, and TanStack Query v5.

### Primary Source Files
- `FULL_CODE/frontend/src/main.tsx`
- `FULL_CODE/frontend/src/lib/api.ts`
- `FULL_CODE/frontend/src/pages/`

### Implementation Details
- **Client-Side Routing:** Managed via `react-router-dom` v6 without triggering browser page reloads.
- **Reactive Cache Synchronization:** TanStack Query (`useQuery`, `useMutation`) manages API state. Mutating policies, grants, or classifications automatically invalidates corresponding query keys (`queryClient.invalidateQueries`), instantly updating the UI.
- **Role-Based Navigational Routing:** Unauthenticated users are redirected to `/login`. Upon authentication, users are automatically routed to their dedicated workspace (`/admin/*`, `/support/*`, `/analyst/*`).

---

## 12. Cryptographic Tamper-Evident Audit Trail

### Technical Description
An immutable, cryptographically chained audit log tracking every security-relevant event.

### Primary Source Files
- `FULL_CODE/backend/app/audit.py`
- `FULL_CODE/backend/app/metadb.py` (`AuditEvent`)
- `FULL_CODE/backend/app/seed.py`
- `FULL_CODE/backend/tests/test_integrity_audit.py`

### Cryptographic Structure
- Every event records `prev_hash` pointing to the immediately preceding event's `entry_hash`.
- `entry_hash` is computed as:
  $$\text{entry\_hash} = \text{SHA256}(\text{prev\_hash} \,||\, \text{ts} \,||\, \text{actor\_id} \,||\, \text{role} \,||\, \text{action} \,||\, \text{outcome} \,||\, \text{details})$$
- **Database Trigger Enforcement:** SQLite database triggers (`audit_no_update`, `audit_no_delete`) abort any SQL `UPDATE` or `DELETE` on the `audit_events` table with `ABORT: audit_events rows cannot be modified`.
- **Verification Endpoint:** Endpoint `GET /api/audit/verify` iterates through all events from genesis, recomputes hashes, and mathematically proves the log's unbroken integrity.

---

## 13. Source Database Cryptographic Fingerprinting

### Technical Description
An automated integrity verification mechanism proving that DreamGuard's query execution engine never modifies target database records.

### Primary Source Files
- `FULL_CODE/backend/app/integrity.py`
- `FULL_CODE/backend/app/saffron.py`
- `FULL_CODE/frontend/src/pages/Integrity.tsx`

### Implementation Details
- Iterates over all tables in the target database.
- For each table, streams all rows ordered deterministically by primary key / columns and computes a cumulative SHA-256 fingerprint:
  $$\text{table\_fingerprint} = \text{SHA256}\left(\sum_{\text{rows}} \text{SHA256}(\text{row\_tuple})\right)$$
- An overall database fingerprint is derived from sorted table fingerprints.
- When an integrity run is executed (`/api/integrity/run`), the pre-query fingerprint is verified against the post-query fingerprint to mathematically certify that the database remains 100% unchanged.

---

## 14. Unstructured Document PII Scanner & CSV Import

### Technical Description
An ingestion pipeline that scans uploaded documents (PDF, DOCX, TXT, CSV) for PII and stages sanitized data.

### Primary Source Files
- `FULL_CODE/backend/app/uploads.py`
- `FULL_CODE/backend/app/api/uploads.py`
- `FULL_CODE/backend/tests/test_uploads.py`
- `FULL_CODE/frontend/src/pages/Uploads.tsx`

### Capabilities
- **Multi-Format Text Extraction:** Uses `pdfplumber` for PDF, `python-docx` for Word DOCX, and `antiword` for legacy DOC files.
- **In-Memory PII Scanning:** Passes extracted text through the deterministic rule scanner to highlight exposed names, emails, phone numbers, and cards.
- **Redaction Preview:** Generates a redacted text preview with sensitive entities replaced by bracketed placeholders.
- **Controlled CSV Import:** Validates CSV schema and imports records into an isolated staging schema (`saffron_imports`), preventing untrusted data from contaminating production tables.

