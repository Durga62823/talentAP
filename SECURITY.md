# DreamGuard — Security & Privacy Architecture

> **Security Policy Version:** 1.0.0  
> **Evaluation Classification:** Enterprise Financial Privacy System  
> **Target Dataset:** Saffron Bank Ltd (Synthetic benchmark dataset)  

---

## 1. Security Philosophy & Principles

DreamGuard is architected under the principle of **Zero-Trust Data Protection**:
1. **Never Trust the Client:** Authorization, SQL validation, and data masking are strictly executed on the server. The client interface never receives unmasked rows or raw secrets.
2. **Read-Only Data Stores:** Stored database records are treated as immutable sources of truth. All queries execute inside read-only database transactions.
3. **Defense in Depth:** Security is enforced at multiple independent layers: AST grammar whitelisting, database connection user privileges, server-side masking, and database update-blocking triggers.
4. **Zero Raw PII Egress:** External AI cloud services (e.g. Google Gemini) are strictly prohibited from receiving raw customer rows.

---

## 2. Threat Model & Mitigation Matrix

| Threat / Attack Vector | Risk | Architectural Mitigation in DreamGuard | Source Code Location |
|---|---|---|---|
| **SQL Injection (SQLi)** | Critical | Queries parsed into Abstract Syntax Trees using `sqlglot`. Disallows multi-statement chaining, non-SELECT statements, and system catalog access. Literals parameterized. | `app/sql_guard.py:60-125` |
| **Privilege Escalation** | High | Roles enforced server-side via `Principal` dependency injection. Table-level grants enforced per database connection. | `app/security.py:85-140`<br>`app/query_engine.py:61-65` |
| **Side-Channel PII Inference** | High | Prohibits unprivileged users from filtering (`WHERE`, `HAVING`) on masked columns (e.g. `WHERE salary > 100000`). | `app/sql_guard.py:175-195` |
| **Differential Privacy Re-Identification** | Medium | Enforces minimum group size ($k \ge 5$) on `GROUP BY` aggregations. Small cohorts (<5) are suppressed. | `app/sql_guard.py:200-220` |
| **PII Exfiltration via Cloud AI** | Critical | Raw sample values are deleted in RAM (`del samples`). External Gemini API receives **only** sanitized statistical distributions. | `app/ai_features.py:15-75`<br>`app/discovery.py:112` |
| **Audit Log Tampering / Erasure** | High | Every audit entry linked in a SHA-256 hash chain (`prev_hash` -> `entry_hash`). SQLite database triggers reject any SQL `UPDATE` or `DELETE`. | `app/audit.py:25-90`<br>`app/seed.py:75-90` |
| **Cross-Role Cache Poisoning** | High | The in-memory LRU cache stores raw tuples. On a cache hit, rows are dynamically passed through the caller's specific `MaskingEngine`. | `app/query_engine.py:170-180` |
| **Credential & Secret Exposure** | High | Passwords hashed with bcrypt. Raw session tokens not stored in database. HMAC keys stored in `data/secrets` with `0600` permissions. | `app/config.py:90-110`<br>`app/security.py:40-60` |
| **Database Corruption / Write Mutation** | Critical | SQLite opened with `PRAGMA query_only = ON`. MySQL uses `START TRANSACTION READ ONLY`. Source rows fingerprinted with SHA-256 before and after queries. | `app/connectors.py:150-210`<br>`app/integrity.py:15-60` |

---

## 3. Cryptographic Implementations

### 3.1 SHA-256 Tamper-Evident Audit Chain
Each entry in `audit_events` contains a cryptographic digest linking it to its predecessor:

$$\text{entry\_hash} = \text{SHA256}(\text{prev\_hash} \,||\, \text{ts} \,||\, \text{actor\_id} \,||\, \text{role} \,||\, \text{action} \,||\, \text{outcome} \,||\, \text{details\_json})$$

The genesis block begins with an empty string (`""`). Modifying, reordering, or deleting any historical row invalidates all subsequent hashes, immediately detected by `GET /api/audit/verify`.

### 3.2 HMAC-SHA-256 Keyed Pseudonymization
To allow analysts to perform relational joins (`customers.id` to `transactions.customer_id`) without discovering the actual customer ID, DreamGuard uses HMAC-SHA-256:

$$\text{pseudonym} = \text{"hm\_k1\_"} \,||\, \text{HMAC-SHA256}(K_{\text{server}}, \text{plaintext})[:16]$$

The secret key $K_{\text{server}}$ resides in `data/secrets/hmac_k1.key` (or environment variable `SENTINEL_HMAC_KEY`) with restricted operating system permissions. It is never transmitted to the browser or exposed via APIs.

### 3.3 Source Data Cryptographic Fingerprinting
To mathematically prove to compliance officers that protected queries never mutate source records, DreamGuard computes a cumulative SHA-256 digest:

$$\text{table\_fingerprint} = \text{SHA256}\left(\sum_{\text{row} \in \text{table}} \text{SHA256}(\text{row\_tuple})\right)$$

The overall database fingerprint is the SHA-256 of all sorted table fingerprints.

---

## 4. Secrets Management & Environment Isolation

1. **Local Secrets Isolation:**
   - Generated secrets (HMAC keys, encrypted password keys) reside in `data/secrets/`.
   - On creation, files are set with `0600` (read/write by owner only).
   - The directory `/data/` is strictly git-ignored.
2. **No Secrets in Version Control:**
   - The repository contains `.env.example` with non-functional placeholders.
   - Live `.env` files and `.db` database files are excluded by `.gitignore`.
3. **No Secrets in API Responses:**
   - Database connection passwords (`secret_enc`) are stored encrypted at rest via AES/Fernet.
   - API endpoints returning connection details (`/api/databases`) always redact passwords.
   - Raw SQL logged in `audit_events` has all literals sanitized to `?` placeholders.

---

## 5. Security Vulnerability Reporting

If you identify a security issue or vulnerability during technical evaluation, please report it to the development team:
- **Team ID:** 234
- **Project:** DreamGuard (Talent AP Mega Hackathon 2026)
- **Problem Statement:** B1

