# DreamGuard — Project Overview

> **Team ID:** 234  
> **Problem Statement ID:** B1  
> **Problem Statement Title:** Smart Data Masking System for PII Protection  
> **Project Name:** DreamGuard  
> **Target Evaluation Dataset:** Saffron Bank Ltd (9 tables, 129,260 synthetic records)  
> **Repository Baseline:** FastAPI 0.115+ (Python 3.12) · React 18 + Vite + Tailwind CSS · SQLite / MySQL / PostgreSQL  

---

## 1. Executive Summary

**DreamGuard** is an enterprise-grade, privacy-preserving **Smart Data Masking System** architected specifically to solve the data privacy dilemma in modern banking and financial enterprises: enabling legitimate operational and analytics workflows while mathematically and deterministically protecting Personally Identifiable Information (PII) and financial secrets.

Built on the official **Saffron Bank Ltd** benchmark dataset (129,260 records across 9 relational tables), DreamGuard establishes a zero-trust enforcement proxy between untrusted querying clients and underlying relational data stores.

Unlike traditional static masking solutions that permanently alter or duplicate databases—introducing synchronization drift, storage bloat, and operational fragility—DreamGuard enforces **dynamic, server-side, role-based masking at query execution time**. Stored records remain cryptographically unmodified and read-only, while results are transformed on the fly according to the authenticated caller's organizational role, regulatory jurisdiction, and purpose.

```
+---------------------------------------------------------------------------------------------------------+
|                                        DREAMGUARD AT A GLANCE                                           |
+------------------------------------+------------------------------------+-------------------------------+
| AUTOMATED PII DISCOVERY            | DYNAMIC ROLE-BASED MASKING         | CRYPTOGRAPHIC GOVERNANCE      |
| • Deterministic Regex + Checksums  | • Admin: Full access / Break-Glass | • SHA-256 Audit Hash Chain    |
| • Local Stacking ML (In-Process)   | • Support: Partial Masking (Cards) | • Table Integrity Fingerprint |
| • Sanitized Gemini AI (Zero-Egress)| • Analyst: HMAC Keys / Aggregates  | • AST Enforcement (sqlglot)   |
| • Upgrade-Only Arbitration Engine  | • Compliance: Audit & Verification | • Multi-DB RO Adapters        |
+------------------------------------+------------------------------------+-------------------------------+
```

---

## 2. Problem Statement & Real-World Motivation

Financial institutions, healthcare providers, and e-commerce platforms routinely store sensitive customer records:
- **Direct PII:** Customer Names, Phone Numbers, Physical Addresses, Email Addresses, Dates of Birth.
- **National Identifiers:** Permanent Account Numbers (PAN), Aadhaar Numbers, Social Security Numbers (SSN), Passport Numbers.
- **Financial Secrets:** Credit Card Numbers (PAN), Bank Account Numbers, Account Balances, Loan Records, UPI IDs.

### Industry Challenges
1. **Regulatory Mandates:** Legal frameworks such as India's **Digital Personal Data Protection (DPDP) Act 2023**, the **EU General Data Protection Regulation (GDPR)**, **PCI-DSS v4.0**, and Reserve Bank of India (RBI) data localization guidelines impose severe financial penalties for unauthorized PII exposure.
2. **Insider Threat & Privilege Creep:** Customer support agents, dispute resolvers, and external contractors frequently require access to specific rows to debug issues, but granting unrestricted `SELECT *` access leaks full credit card numbers, national IDs, and account balances.
3. **Data Science & Analytics Exposure:** Business intelligence teams require aggregate distributions and relational joins across customer transactions without viewing individual identities.
4. **Third-Party AI Cloud Privacy Risks:** Sending raw customer databases to external Large Language Models (LLMs) creates severe compliance violations and data exfiltration vulnerabilities.

---

## 3. Persona-Based Solution Model

DreamGuard abandons the insecure paradigm of exposing a raw SQL console to all users. Instead, it partitions application functionality into **four dedicated, role-specific operational workspaces**:

```
                                  +----------------------+
                                  |   Web Browser UI     |
                                  +----------+-----------+
                                             |
                              +--------------+--------------+
                              | Authenticated Principal RBAC |
                              +--------------+--------------+
                                             |
         +---------------------+-------------+-------------+---------------------+
         |                     |                           |                     |
         v                     v                           v                     v
   [ROLE: ADMIN]        [ROLE: SUPPORT]            [ROLE: ANALYST]       [ROLE: COMPLIANCE]
   Security & Gov.      Customer Operations        Privacy Analytics     Audit Verification
   - Full unmasked*     - Partial masking          - Full redaction      - Zero PII view
   - Policy lifecycle   - Phone suffix only        - Keyed HMAC joins    - SHA-256 chain log
   - PII scan overrides - Card last-4 only         - Aggregates (k >= 5) - Source fingerprint
   - Break-glass PAN    - Balance denied           - No raw balances     - Export verification
   (*with justification)
```

### 1. Security & Compliance Administrator (`admin_*`)
- **Landing:** `/admin/overview`
- **Capabilities:** Database connection management, manual PII discovery triggering, classification reviews and overrides, masking policy authoring, table grants management, tamper-evident audit inspection, and cryptographic source verification.
- **Access Level:** Direct database access with required break-glass justification logging for raw national IDs (`raw:break_glass`).

### 2. Customer Support Agent (`support_*`)
- **Landing:** `/support/overview`
- **Capabilities:** Customer Lookup (`/support/lookup`), Customer 360 Profiles (`/support/profiles`), 3,000 Support Tickets triage (`/support/tickets`), and Personal Activity Log (`/support/activity`).
- **Access Level:** Partial masking enforced at query runtime:
  - Credit Cards: `4111-XXXX-XXXX-1111`
  - Phone Numbers: `********1099`
  - Email Addresses: `a****@example.com`
  - Financial balances and loan applications are strictly redacted or denied.

### 3. Data Analyst (`analyst_*`)
- **Landing:** `/analyst/overview`
- **Capabilities:** Visual Analytics (`/analyst/analytics`), Monthly Transaction Trends over 100,000 transactions (`/analyst/trends`), Privacy-Preserving Aggregate Explorer (`/analyst/aggregates`), Privacy-Screened CSV Reports (`/analyst/reports`), and My Activity (`/analyst/activity`).
- **Access Level:** Names and phone numbers redacted (`[REDACTED]`); card numbers replaced with deterministic HMAC-SHA-256 pseudonyms (`hm_k1_...`) enabling relational joins; balance queries enforced with minimum group-by aggregation thresholds ($k \ge 5$).

### 4. Compliance Auditor (`compliance_lata`)
- **Landing:** `/admin/overview` (Read-Only)
- **Capabilities:** Reviews discovered PII tags, inspects unbroken SHA-256 audit hash chains, and executes independent cryptographic source data fingerprint verifications. Cannot alter security policies, modify table grants, or access unmasked data.

---

## 4. Feature Implementation Inventory

The table below outlines the comprehensive implementation status of all major features across the DreamGuard repository. Statuses are assigned based on strict code inspection and test suite execution:

| Feature / Subsystem | Primary Source Files | Status | Verifiable Evidence |
|---|---|---|---|
| **User Authentication & Session Management** | `app/security.py`<br>`app/api/auth.py`<br>`frontend/src/lib/auth.ts` | `IMPLEMENTED_AND_VERIFIED` | SHA-256 session token hashing, cookie/bearer authentication, bcrypt password validation. Verified in `tests/test_authz.py`. |
| **Role-Based Access Control (RBAC)** | `app/security.py`<br>`app/metadb.py`<br>`app/seed.py`<br>`frontend/src/components/Layout.tsx` | `IMPLEMENTED_AND_VERIFIED` | 4 roles seeded, granular permissions (`query:execute`, `audit:read`, etc.), table-level grants per connection. Tested in `tests/test_authz.py`. |
| **Multi-Database Read-Only Adapters** | `app/connectors.py`<br>`app/saffron.py`<br>`app/api/databases.py` | `IMPLEMENTED_AND_VERIFIED` | SQLAlchemy connection pooling for SQLite (`query_only = ON`), MySQL (`START TRANSACTION READ ONLY`), and PostgreSQL. Verified in `tests/test_mysql.py`, `tests/test_postgres.py`. |
| **Schema Discovery & In-Memory Sampling** | `app/discovery.py`<br>`app/connectors.py` | `IMPLEMENTED_AND_VERIFIED` | Random row sampling in RAM (`sample_size=100`), immediate memory freeing via `del samples`. Tested in `tests/test_scanner.py`. |
| **Deterministic Rule Scanner** | `app/scanner.py`<br>`app/entities.py` | `IMPLEMENTED_AND_VERIFIED` | Regex + checksum validation (Luhn for Credit Cards, Verhoeff for Aadhaar, Indian PAN, US SSN, IBAN, IFSC). Verified in `tests/test_scanner.py` (100% pass). |
| **Local Stacking ML Classifier** | `app/ml/model.py`<br>`app/ml/featurize.py`<br>`app/ml/synth.py`<br>`app/ml/train.py` | `IMPLEMENTED_AND_VERIFIED` | In-process TF-IDF char n-gram Logistic Regression + HistGradientBoostingClassifier, isotonic calibration. Verified in `tests/test_ml_model.py`. Artifact `pii_model.joblib` exists (5.7MB). |
| **LLM Contextual Detection (Gemini)** | `app/ai_classifier.py`<br>`app/ai_features.py` | `IMPLEMENTED_AND_VERIFIED` | Google GenAI SDK integration with Gemini 2.5/3.8 Flash. Zero raw PII egress (sanitized statistics only). Verified in `tests/test_ai_classification.py`. |
| **Upgrade-Only Arbitration Engine** | `app/ai_classifier.py`<br>`app/discovery.py` | `IMPLEMENTED_AND_VERIFIED` | Strict mathematical hierarchy: AI/ML can only elevate sensitivity rank, never downgrade rule results. Tested in `tests/test_ai_classification.py`. |
| **Human Review Governance & Overrides** | `app/api/admin.py`<br>`app/discovery.py`<br>`frontend/src/pages/Discovery.tsx` | `IMPLEMENTED_AND_VERIFIED` | Admin status reviews (`approved`, `rejected`, `overridden`). Manual decisions survive automated rescans. Verified in `tests/test_ai_classification.py`. |
| **Dynamic Role-Based Masking Engine** | `app/masking.py`<br>`app/policy.py` | `IMPLEMENTED_AND_VERIFIED` | `PARTIAL`, `HASH_HMAC`, `REDACT`, `DROP`, `ALLOW` actions applied at query runtime. Keyed HMAC-SHA-256 preserved. Verified in `tests/test_masking.py`. |
| **SQL Guard AST Validator & Rewriter** | `app/sql_guard.py`<br>`app/query_engine.py` | `IMPLEMENTED_AND_VERIFIED` | `sqlglot` parser blocks DDL/DML, system catalogs, SQL injection, rewrites `LIMIT` and expands column lineage. Verified in `tests/test_query_security.py`. |
| **Result Cache & Latency Optimization** | `app/connectors.py`<br>`app/query_engine.py` | `IMPLEMENTED_AND_VERIFIED` | In-memory LRU + TTL result cache (`execute_cached`). Re-applies masking per caller role on cache hits. Verified in `tests/test_performance.py`. |
| **Optimistic Query Optimization** | `app/connectors.py`<br>`app/sql_guard.py` | `PARTIALLY_IMPLEMENTED` | Query risk pre-flight analyzer (`/api/query/analyze`) and AST planning with LRU caching implemented. Speculative execution / optimistic concurrency control is planned. |
| **Zero-Full-Page-Reload User Experience** | `frontend/src/main.tsx`<br>`frontend/src/pages/` | `IMPLEMENTED_AND_VERIFIED` | React 18 Single Page Application with `react-router-dom` v6 and TanStack Query v5. Real-time dynamic updates without browser reloads. |
| **Cryptographic Tamper-Evident Audit Log** | `app/audit.py`<br>`app/metadb.py`<br>`app/seed.py` | `IMPLEMENTED_AND_VERIFIED` | SHA-256 hash-chained entries (`prev_hash` -> `entry_hash`). SQLite DB triggers block UPDATE and DELETE. Tested in `tests/test_integrity_audit.py`. |
| **Source Data Cryptographic Fingerprinting** | `app/integrity.py`<br>`app/saffron.py`<br>`frontend/src/pages/Integrity.tsx` | `IMPLEMENTED_AND_VERIFIED` | SHA-256 fingerprint computed across sorted table rows before and after query sessions to mathematically prove zero mutation. Tested in `tests/test_integrity_audit.py`. |
| **Unstructured Document PII Scanner** | `app/uploads.py`<br>`app/api/uploads.py`<br>`frontend/src/pages/Uploads.tsx` | `IMPLEMENTED_AND_VERIFIED` | In-memory text extraction from PDF, DOCX, TXT, CSV; redaction and staging to isolated `saffron_imports` schema. Tested in `tests/test_uploads.py`. |

---

## 5. Technical Stack Summary

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Backend Framework** | FastAPI | 0.115.5 | High-performance asynchronous REST API server |
| **Backend Runtime** | Python | 3.12+ | Core application logic and execution engine |
| **SQL Parser & AST Planner** | sqlglot | 26.2.0 | AST query inspection, dialect translation, and lineage validation |
| **ORM & Database Tooling** | SQLAlchemy | 2.0.36 | Database abstraction, connection pooling, and metadata persistence |
| **Machine Learning** | scikit-learn | 1.5.2 / 1.6+ | In-process stacked classifier (LogisticRegression + HistGradientBoosting) |
| **Model Serialization** | joblib | 1.4.2 | Local model artifact persistence and loading |
| **Cloud AI Integration** | google-genai | 0.1.1 | Official Google GenAI SDK for Gemini 2.5/3.8 Flash |
| **Frontend Framework** | React | 18.3.1 | Component-based reactive user interface |
| **Build Tool & Bundler** | Vite | 5.4.11 | Fast ES module development server and production bundler |
| **State Management** | TanStack Query | 5.62.0 | Client-side async caching, mutation, and cache invalidation |
| **Routing** | React Router | 6.28.0 | Zero-reload client-side routing and deep linking |
| **Styling** | Tailwind CSS | 3.4.15 | Utility-first responsive design system |
| **Charts & Visualizations** | Recharts | 2.13.3 | Privacy-screened analytics charting |
| **Icons** | Lucide React | 0.460.0 | Consistent iconography |
| **Testing Framework** | pytest | 8.3.3 | Automated backend testing suite (152 passing tests) |

