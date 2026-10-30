"""Synthetic training corpus for the PII column classifier (training time only; needs Faker).

Every column is fully synthetic: Faker (en_IN / en_US) values with realistic banking formats,
messy legacy column names, opaque names (col_7, field_3) that force the model to read values,
nulls, sparse legacy fields and mixed-content columns. No real or official data is used.

Honesty guard: column names that exactly match a column of the official evaluation dataset
are excluded, so the evaluation set's names are never seen verbatim during training."""
from __future__ import annotations

import random
import string
from datetime import date, timedelta
from typing import Any, Callable

UP = string.ascii_uppercase
DIG = string.digits


# ---------------------------------------------------------------- value generators ----------

def luhn_digit(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d -= 9 if d > 9 else 0
        total += d
    return str((10 - total % 10) % 10)


def card(r: random.Random) -> str:
    prefix = r.choice(["4", "51", "52", "53", "54", "55", "60", "65", "37"])
    length = 15 if prefix == "37" else 16
    body = prefix + "".join(r.choice(DIG) for _ in range(length - len(prefix) - 1))
    num = body + luhn_digit(body)
    style = r.random()
    if style < 0.4:
        return num
    sep = " " if style < 0.7 else "-"
    return sep.join(num[i:i + 4] for i in range(0, len(num), 4))


VERHOEFF_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
              [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
VERHOEFF_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],
              [4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
VERHOEFF_INV = [0,4,3,2,1,5,6,7,8,9]


def verhoeff_digit(body: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(body)):
        c = VERHOEFF_D[c][VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(VERHOEFF_INV[c])


def aadhaar(r: random.Random) -> str:
    body = r.choice("23456789") + "".join(r.choice(DIG) for _ in range(10))
    # Real data mixes checksum-valid and invalid numbers; the official pack deliberately uses invalid ones.
    num = body + (verhoeff_digit(body) if r.random() < 0.5 else r.choice(DIG))
    style = r.random()
    if style < 0.45:
        return num
    if style < 0.85:
        return f"{num[:4]} {num[4:8]} {num[8:]}"
    return f"XXXX XXXX {num[8:]}"


def pan(r: random.Random) -> str:
    return "".join(r.choice(UP) for _ in range(3)) + r.choice("PCHFATBLJG") + r.choice(UP) + "".join(r.choice(DIG) for _ in range(4)) + r.choice(UP)


def ssn(r: random.Random) -> str:
    return f"{r.randint(100, 665):03d}-{r.randint(1, 99):02d}-{r.randint(1, 9999):04d}"


def passport(r: random.Random) -> str:
    return r.choice("ABCDEFGHJKLMNPRSTUVWZ") + str(r.randint(1, 9)) + "".join(r.choice(DIG) for _ in range(5)) + str(r.randint(1, 9))


def national_id(r: random.Random) -> str:
    return r.choices([aadhaar, pan, ssn, passport], weights=[4, 4, 2, 1])[0](r)


def iban(r: random.Random) -> str:
    country = r.choice(["GB", "DE", "FR", "NL", "AE"])
    bban = "".join(r.choice(UP) for _ in range(4)) + "".join(r.choice(DIG) for _ in range(14))
    rearranged = bban + country + "00"
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    check = 98 - int(numeric) % 97
    return f"{country}{check:02d}{bban}"


def phone(r: random.Random, fk: Any) -> str:
    if r.random() < 0.15:
        return f"({r.randint(201, 989)}) {r.randint(200, 999)}-{r.randint(0, 9999):04d}"  # US
    num = r.choice("6789") + "".join(r.choice(DIG) for _ in range(9))
    return r.choices([num, "+91" + num, "+91 " + num[:5] + " " + num[5:], "0" + num, "91-" + num], weights=[6, 2, 1, 1, 1])[0]


def upi(r: random.Random, fk: Any) -> str:
    handle = r.choice([fk.user_name(), fk.first_name().lower() + str(r.randint(1, 999)), "".join(r.choice(DIG) for _ in range(10))])
    return f"{handle}@{r.choice(['okaxis', 'oksbi', 'ybl', 'paytm', 'okhdfcbank', 'ibl', 'apl', 'upi'])}"


def digit_string(r: random.Random) -> str:
    """Long digit runs. Shared by account numbers AND non-sensitive references (UTR, RRN, txn
    numbers): real values are indistinguishable, so only the column name can separate them."""
    n = "".join(r.choice(DIG) for _ in range(r.choice([9, 11, 12, 14, 15, 16, 18])))
    return n if r.random() < 0.85 else r.choice(["SB", "CA", "OD", "TX", "RF"]) + n


acct_no = digit_string

ID_PREFIXES = ["CIF", "C", "CU", "CL", "TXN", "TKT", "APP", "REQ", "DOC", "CRD", "LN", "KYC", "E", "ID", ""]


def generic_id(r: random.Random) -> str:
    """Alphanumeric identifiers. Shared by customer IDs AND other record IDs (ticket, application,
    card reference), for the same reason: the values carry no class information."""
    return r.choice(ID_PREFIXES) + r.choice(["-", "", ""]) + "".join(r.choice(UP + DIG) for _ in range(r.randint(6, 10)))


def ifsc(r: random.Random) -> str:
    return "".join(r.choice(UP) for _ in range(4)) + "0" + "".join(r.choice(UP + DIG) for _ in range(6))


def dob(r: random.Random) -> str:
    d = date(1935, 1, 1) + timedelta(days=r.randint(0, 365 * 70))
    return d.isoformat() if r.random() < 0.85 else d.strftime("%d/%m/%Y")


def recent_date(r: random.Random) -> str:
    d = date(2012, 1, 1) + timedelta(days=r.randint(0, 365 * 14))
    return d.isoformat()


def timestamp(r: random.Random) -> str:
    return f"{recent_date(r)}T{r.randint(0, 23):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}"


def amount(r: random.Random) -> float:
    return round(r.lognormvariate(9, 2), 2) * (1 if r.random() < 0.95 else -1)


def free_text_pii(r: random.Random, fk: Any) -> str:
    starters = ["Customer called regarding", "Cust says", "pls check", "Refund pending for", "Escalated:", "KYC update -",
                "Debit dispute raised,", "Callback requested,", "card blocked,", "UPI failed for"]
    entity = r.choice([lambda: phone(r, fk), lambda: fk.email(), lambda: card(r), lambda: upi(r, fk), lambda: aadhaar(r), lambda: fk.name(), lambda: acct_no(r)])()
    tail = r.choice(["please call back", "amount not credited", "resolve asap", "verified identity", "issue persists", "kindly reverse"])
    return f"{r.choice(starters)} {r.choice(['reach on', 'contact', 'ref', 'details', 'id'])} {entity} {tail}"


def plain_text(r: random.Random, fk: Any) -> str:
    return r.choice([fk.sentence(nb_words=r.randint(4, 12)), "Passbook re-issued", "Address proof verified", "Nomination updated",
                     "Cheque book dispatched", "Standing instruction set", "Statement requested", "No remarks"])


def mixed_legacy(r: random.Random, fk: Any) -> str:
    """Legacy free field: mostly harmless notes, sometimes an embedded identifier."""
    return free_text_pii(r, fk) if r.random() < r.uniform(0.15, 0.5) else plain_text(r, fk)


# ---------------------------------------------------------------- column specs ----------

def _tbl(*names: str) -> list[str]:
    return list(names)


PERSON_TABLES = _tbl("customers", "customer_master", "clients", "account_holders", "cust_profile", "kyc", "beneficiaries", "users",
                     "nominees", "cardholders", "loan_applicants", "employees", "borrowers", "members")
TXN_TABLES = _tbl("transactions", "txn_log", "payments", "ledger", "statements", "transfers", "upi_txn")
ACCT_TABLES = _tbl("accounts", "deposits", "loans", "cards", "credit_lines", "wallets", "fixed_deposits")
ORG_TABLES = _tbl("branches", "branch_master", "offices", "merchants", "atm_locations", "vendors", "service_centres")
ANY_TABLES = PERSON_TABLES + TXN_TABLES + ACCT_TABLES + _tbl("support_tickets", "complaints", "audit_trail", "products", "loan_applications")

Spec = dict[str, Any]
SPECS: list[Spec] = [
    {"cat": "CREDIT_CARD", "tables": ACCT_TABLES + PERSON_TABLES, "types": ["VARCHAR(19)", "VARCHAR(20)", "TEXT", "CHAR(16)"],
     "names": ["card_number", "card_num", "cardno", "cc_no", "ccnum", "credit_card", "debit_card_no", "card_pan", "pan_card_no",
               "primary_card", "crd_no", "card_nbr", "CardNumber", "card_no_masked_src", "plastic_no"],
     "gen": lambda r, fk: card(r)},
    {"cat": "NATIONAL_ID", "weight": 0.35, "tables": PERSON_TABLES, "types": ["VARCHAR(12)", "VARCHAR(14)", "VARCHAR(16)", "TEXT"],
     "names": ["aadhaar", "aadhar_number", "uid_no", "aadhaar_num", "uidai_no", "aadhaar_card", "adhar_no", "uid"],
     "gen": lambda r, fk: aadhaar(r)},
    {"cat": "NATIONAL_ID", "weight": 0.35, "tables": PERSON_TABLES + _tbl("loan_applications", "tax_records"), "types": ["VARCHAR(10)", "CHAR(10)", "TEXT"],
     "names": ["pan", "pan_number", "pan_card", "pan_id", "tax_pan", "permanent_account_no", "income_tax_pan", "pancard"],
     "gen": lambda r, fk: pan(r)},
    {"cat": "NATIONAL_ID", "weight": 0.2, "tables": PERSON_TABLES + _tbl("us_clients", "nri_customers"), "types": ["VARCHAR(11)", "CHAR(11)", "TEXT"],
     "names": ["social_security_no", "social_sec_num", "ssn_no", "ss_number", "us_ssn", "tax_id", "tin"],
     "gen": lambda r, fk: ssn(r)},
    {"cat": "NATIONAL_ID", "weight": 0.1, "tables": PERSON_TABLES, "types": ["VARCHAR(9)", "VARCHAR(12)"],
     "names": ["passport_no", "passport_number", "passport", "ppt_no", "travel_doc_no"],
     "gen": lambda r, fk: passport(r)},
    {"cat": "BANK_ACCOUNT", "tables": PERSON_TABLES + TXN_TABLES, "types": ["VARCHAR(34)", "TEXT"],
     "names": ["iban", "iban_no", "beneficiary_iban", "intl_account", "swift_account", "foreign_acct_iban", "iban_code"],
     "gen": lambda r, fk: iban(r)},
    {"cat": "EMAIL", "tables": PERSON_TABLES, "types": ["VARCHAR(80)", "VARCHAR(120)", "TEXT"],
     "names": ["email", "email_address", "e_mail", "mail_id", "email_addr", "contact_email", "personal_email", "alt_email",
               "EmailAddress", "mailid", "eml", "communication_email", "registered_email"],
     "gen": lambda r, fk: fk.email()},
    {"cat": "PHONE", "tables": PERSON_TABLES, "types": ["VARCHAR(15)", "VARCHAR(20)", "VARCHAR(24)", "TEXT"],
     "names": ["phone", "phone_no", "mobile", "mobile_number", "mob", "mobile_no", "cell", "contact_no", "telephone", "msisdn",
               "alt_phone", "alternate_mobile", "rmn", "registered_mobile", "whatsapp_no", "ph_no", "MobileNo", "landline"],
     "gen": phone},
    {"cat": "PERSON_NAME", "tables": PERSON_TABLES + TXN_TABLES, "types": ["VARCHAR(80)", "VARCHAR(60)", "TEXT"],
     "names": ["name", "full_name", "customer_name", "first_name", "last_name", "surname", "holder_name", "account_holder", "father_name",
               "mother_name", "spouse_name", "nominee_name", "guardian_nm", "beneficiary_name", "payee_name", "applicant_nm", "emp_name",
               "name_on_account", "FullName", "cardholder_name", "cust_name", "fname", "lname"],
     "gen": lambda r, fk: fk.name() if r.random() < 0.8 else fk.name().upper()},
    {"cat": "POSTAL_ADDRESS", "tables": PERSON_TABLES, "types": ["VARCHAR(120)", "VARCHAR(160)", "TEXT"],
     "names": ["address", "address_line1", "address_line_2", "addr1", "street", "street_address", "residential_address",
               "permanent_address", "corr_address", "mailing_addr", "res_addr", "home_address", "AddressLine1", "comm_addr"],
     "gen": lambda r, fk: fk.street_address() if r.random() < 0.6 else fk.address().replace("\n", ", ")},
    {"cat": "POSTAL_ADDRESS", "weight": 0.5, "tables": PERSON_TABLES, "types": ["VARCHAR(120)", "TEXT"],
     "names": ["address_line2", "addr2", "address_2", "locality", "landmark", "area_locality", "street2", "address_line_3"],
     "gen": lambda r, fk: r.choice([f"Near {fk.last_name()} {r.choice(['Chowk', 'Market', 'Temple', 'School', 'Mall'])}",
                                    f"{fk.last_name()} {r.choice(['Nagar', 'Colony', 'Residency', 'Enclave', 'Apartments', 'Vihar'])}",
                                    f"Sector {r.randint(1, 60)}, {fk.city()}", f"Flat {r.randint(1, 999)}, {fk.last_name()} Heights"])},
    {"cat": "DATE_OF_BIRTH", "tables": PERSON_TABLES, "types": ["DATE", "VARCHAR(10)", "TEXT"],
     "names": ["dob", "date_of_birth", "birth_date", "birthdate", "birthday", "dt_of_birth", "dob_date", "DateOfBirth", "bdate", "birth_dt"],
     "gen": lambda r, fk: dob(r)},
    {"cat": "FREE_TEXT_PII", "tables": _tbl("support_tickets", "complaints", "call_notes", "transactions", "accounts", "crm_notes"),
     "types": ["TEXT", "VARCHAR(500)"],
     "names": ["description", "comments", "comment", "remarks", "note", "notes_text", "message", "body", "details", "narrative",
               "memo", "agent_notes", "complaint_text", "free_text", "misc_info", "additional_info", "legacy_notes"],
     "gen": lambda r, fk: free_text_pii(r, fk) if r.random() < 0.8 else plain_text(r, fk)},
    {"cat": "FREE_TEXT_PII", "tables": ANY_TABLES, "types": ["TEXT", "VARCHAR(200)"],  # sparse mixed legacy fields
     "names": ["extra", "misc", "other_info", "legacy_field", "info", "aux_data", "ref_text", "memo_line", "addl_details", "notes2"],
     "gen": mixed_legacy, "sparse": True},
    {"cat": "UPI_ID", "tables": PERSON_TABLES + TXN_TABLES, "types": ["VARCHAR(60)", "TEXT"],
     "names": ["upi", "upi_id", "vpa", "upi_handle", "payer_vpa", "payee_vpa", "virtual_address", "upi_address", "collect_vpa"],
     "gen": upi},
    {"cat": "ACCOUNT_NUMBER", "tables": ACCT_TABLES + TXN_TABLES + PERSON_TABLES, "types": ["VARCHAR(18)", "VARCHAR(20)", "CHAR(14)", "TEXT"],
     "names": ["account_number", "acct_number", "acc_no", "account_num", "ac_no", "acctno", "savings_acct", "linked_account",
               "debit_account", "credit_account", "beneficiary_acct", "loan_account_no", "AccountNo", "a_c_no", "src_acct", "dest_acct"],
     "gen": lambda r, fk: acct_no(r)},
    {"cat": "FINANCIAL_AMOUNT", "tables": ACCT_TABLES + TXN_TABLES + PERSON_TABLES, "types": ["DECIMAL(15, 2)", "NUMERIC(18,2)", "REAL", "DOUBLE"],
     "names": ["balance", "current_balance", "avail_bal", "ledger_bal", "amount", "txn_amount", "amt", "loan_amt", "salary",
               "annual_income", "monthly_income", "net_worth", "credit_limit", "outstanding", "emi_amount", "principal_amt",
               "closing_balance", "opening_bal", "overdraft_limit", "sanction_amount", "deposit_amt", "Balance", "txn_amt_inr"],
     "gen": lambda r, fk: amount(r)},
    {"cat": "CREDIT_SCORE", "tables": PERSON_TABLES + _tbl("loan_applications", "bureau_reports", "underwriting"), "types": ["INTEGER", "SMALLINT", "INT"],
     "names": ["cibil", "cibil_score", "credit_score", "bureau_score", "experian_score", "risk_score_bureau", "fico", "fico_score", "crif_score"],
     "gen": lambda r, fk: r.randint(300, 900)},
    {"cat": "CUSTOMER_ID", "tables": PERSON_TABLES + ACCT_TABLES + TXN_TABLES, "types": ["VARCHAR(16)", "VARCHAR(12)", "CHAR(10)"],
     "names": ["cust_id", "client_id", "cif", "cif_no", "cif_id", "customer_no", "customer_ref", "party_id", "CustomerId", "custid",
               "client_code", "member_id", "ucic"],
     "gen": lambda r, fk: generic_id(r)},
    {"cat": "ORG_CONTACT", "weight": 0.35, "tables": ORG_TABLES, "types": ["VARCHAR(20)", "VARCHAR(24)"],
     "names": ["branch_phone", "office_phone", "contact_number", "phone", "helpline", "store_phone", "branch_contact", "landline_no"],
     "gen": phone},
    {"cat": "ORG_CONTACT", "weight": 0.35, "tables": ORG_TABLES, "types": ["VARCHAR(80)"],
     "names": ["branch_email", "office_email", "email", "contact_email", "merchant_email", "support_mail", "branch_mail_id"],
     "gen": lambda r, fk: f"{r.choice(['branch', 'ops', 'info', 'care', 'manager'])}{r.randint(1, 999)}@{fk.domain_name()}"},
    {"cat": "ORG_CONTACT", "weight": 0.3, "tables": ORG_TABLES, "types": ["VARCHAR(160)", "TEXT"],
     "names": ["branch_address", "address", "office_addr", "location_address", "premises", "site_address", "addr_full"],
     "gen": lambda r, fk: r.choice(["Ground Floor, ", "First Floor, ", "Shop No. 4, ", ""]) + fk.street_address()},
]

NONE_GENS: list[tuple[list[str], list[str], Callable[[random.Random, Any], Any]]] = [
    (["status", "acct_status", "txn_state", "state_flag", "kyc_state", "is_active", "record_status", "approval_status", "card_state"],
     ["VARCHAR(12)", "VARCHAR(10)"], lambda r, fk: r.choice(["ACTIVE", "CLOSED", "PENDING", "BLOCKED", "DORMANT", "APPROVED", "REJECTED"])),
    (["channel", "txn_channel", "mode", "payment_mode", "source_channel", "via"], ["VARCHAR(12)"],
     lambda r, fk: r.choice(["UPI", "NEFT", "IMPS", "ATM", "POS", "BRANCH", "NETBANKING", "MOBILE"])),
    (["type", "acct_type", "product_type", "loan_kind", "card_category", "account_class", "variant", "tier", "segment_code"], ["VARCHAR(16)"],
     lambda r, fk: r.choice(["SAVINGS", "CURRENT", "GOLD", "PLATINUM", "HOME", "AUTO", "PERSONAL", "RETAIL", "SME", "CLASSIC"])),
    (["gender", "sex"], ["VARCHAR(8)", "CHAR(1)"], lambda r, fk: r.choice(["M", "F", "O", "Male", "Female"])),
    (["city", "town", "district", "state", "region", "zone", "country", "location"], ["VARCHAR(40)"],
     lambda r, fk: r.choice([fk.city(), fk.state(), r.choice(["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"])])),
    (["pin", "pin_code", "postal_code", "zip", "zipcode"], ["VARCHAR(6)", "VARCHAR(10)"], lambda r, fk: str(r.randint(110001, 855999))),
    (["created_at", "updated_at", "txn_time", "event_ts", "logged_at", "processed_ts", "posted_at", "closed_ts", "login_time"],
     ["TIMESTAMP", "DATETIME", "TEXT"], lambda r, fk: timestamp(r)),
    (["open_date", "opening_dt", "start_date", "maturity_date", "expiry_dt", "valid_till", "review_date", "approved_on",
      "disbursed_on", "issue_date", "value_date", "joined_on", "effective_dt"], ["DATE", "VARCHAR(10)"], lambda r, fk: recent_date(r)),
    (["opened_on", "established_on", "incorporated_dt", "inception_date", "since_date", "commissioned_on", "start_dt", "launch_dt"],
     ["DATE", "VARCHAR(10)"], lambda r, fk: (date(1950, 1, 1) + timedelta(days=r.randint(0, 365 * 75))).isoformat()),
    (["company_nm", "merchant_nm", "org_nm", "bank_nm", "scheme_nm", "product_nm", "employer_name", "firm_nm", "office_nm", "store_nm"],
     ["VARCHAR(60)", "VARCHAR(80)"],
     lambda r, fk: r.choice([fk.company(), f"{fk.last_name()} {r.choice(['Traders', 'Enterprises', '& Sons', 'Industries', 'Pvt Ltd', 'Agencies', 'Textiles'])}",
                             f"{r.choice(['Saffron', 'Central', 'City', 'Main'])} Branch - {fk.city()}"])),
    (["transaction_id", "txn_no", "payment_id", "event_no", "trace_number", "order_no", "invoice_id"], ["VARCHAR(16)", "BIGINT"],
     lambda r, fk: digit_string(r)),
    (["card_ref", "acct_ref", "doc_ref", "record_ref", "app_ref", "token_ref", "loan_ref", "case_ref"], ["VARCHAR(16)"],
     lambda r, fk: generic_id(r)),
    (["txn_ref", "reference_no", "utr", "rrn_no", "trace_id", "batch_no", "voucher_no", "cheque_no", "stan"], ["VARCHAR(24)", "VARCHAR(12)"],
     lambda r, fk: digit_string(r) if r.random() < 0.6 else generic_id(r)),
    (["id", "txn_id", "ticket_no", "case_id", "application_id", "request_id", "order_id", "row_id", "event_id", "doc_id", "kyc_ref"],
     ["VARCHAR(16)", "INTEGER"], lambda r, fk: generic_id(r)),
    (["ifsc_code", "ifsc", "bank_ifsc", "micr", "branch_id", "branch_cd", "sol_id", "office_code"], ["VARCHAR(11)", "VARCHAR(6)"],
     lambda r, fk: ifsc(r) if r.random() < 0.6 else "".join(r.choice(DIG) for _ in range(r.choice([4, 6, 9])))),
    (["interest_rate", "roi", "rate_pct", "fee_pct", "discount_rate", "tax_rate", "fx_rate", "multiplier"], ["DECIMAL(5, 2)", "REAL"],
     lambda r, fk: round(r.uniform(0.5, 24), 2)),
    (["tenure_months", "term", "qty", "count", "num_attempts", "age_days", "retries", "priority_level", "seq", "version", "exp_month",
      "exp_year", "days_past_due"], ["INTEGER", "SMALLINT"], lambda r, fk: r.randint(0, 2030) if r.random() < 0.3 else r.randint(0, 120)),
    (["language", "lang_pref", "currency", "ccy", "network", "card_network", "occupation", "employment_type", "relationship",
      "decision", "priority", "category", "purpose", "risk_band", "kyc_mode", "doc_type"], ["VARCHAR(20)"],
     lambda r, fk: r.choice(["English", "Hindi", "INR", "USD", "VISA", "RUPAY", "MASTERCARD", "Salaried", "Self-employed", "Spouse",
                             "Father", "APPROVED", "HIGH", "LOW", "MEDIUM", "Education", "Aadhaar", "Passport", "Voter ID", "VIDEO"])),
    (["product_name", "merchant_name", "employer", "company", "bank_name", "branch_name", "scheme_name", "plan_name", "store"], ["VARCHAR(60)"],
     lambda r, fk: fk.company()),
    (["description", "remarks", "comments", "product_desc", "note"], ["TEXT"], lambda r, fk: plain_text(r, fk)),
    (["flag", "is_primary", "fatca_flag", "nri_flag", "kyc_done", "active"], ["BOOLEAN", "CHAR(1)", "VARCHAR(1)"],
     lambda r, fk: r.choice(["Y", "N", "1", "0", "true", "false"])),
    (["assigned_to", "created_by", "maker_id", "checker_id", "officer", "agent_code", "verified_by_emp"], ["VARCHAR(20)"],
     lambda r, fk: r.choice(["E", "EMP", "agent_", "ops_"]) + str(r.randint(10, 99999))),
    (["score", "risk_rating", "rating", "nps", "satisfaction"], ["INTEGER"], lambda r, fk: r.randint(1, 10)),
    (["amount_bucket", "limit_band", "income_band"], ["VARCHAR(16)"], lambda r, fk: r.choice(["<1L", "1L-5L", "5L-10L", ">10L"])),
]

OPAQUE = ["col_{n}", "field_{n}", "attr{n}", "c{n}", "data_{n}", "val{n}", "x{n}", "column{n}", "f{n}", "var_{n}"]


def _name(r: random.Random, names: list[str]) -> str:
    if r.random() < 0.12:
        _name.base = "__opaque__"  # type: ignore[attr-defined]
        return r.choice(OPAQUE).format(n=r.randint(1, 40))
    n = r.choice(names)
    _name.base = n.lower()  # type: ignore[attr-defined]
    roll = r.random()
    if roll < 0.15:
        n = n.upper()
    elif roll < 0.22:
        n = f"{n}_{r.choice(['1', '2', 'old', 'new', 'src', 'tmp'])}"
    elif roll < 0.28:
        n = f"{r.choice(['cust', 'c', 'primary', 'alt', 'old', 'x'])}_{n}"
    return n


def _column(r: random.Random, fk: Any, cat: str, names: list[str], tables: list[str], types: list[str],
            gen: Callable[[random.Random, Any], Any], sparse: bool = False) -> dict[str, Any]:
    size = r.randint(40, 150)
    null_rate = r.uniform(0.6, 0.95) if sparse else (r.uniform(0, 0.4) if r.random() < 0.4 else 0.0)
    values = [None if r.random() < null_rate else gen(r, fk) for _ in range(size)]
    column = _name(r, names)
    return {"table": r.choice(tables), "column": column, "base_name": _name.base, "data_type": r.choice(types),  # type: ignore[attr-defined]
            "nullable": null_rate > 0, "primary_key": False, "values": values, "label": cat}


def generate(n_per_category: int = 260, n_none: int = 1800, seed: int = 7, exclude_names: set[str] | None = None) -> list[dict[str, Any]]:
    from faker import Faker

    r = random.Random(seed)
    fakers = [Faker("en_IN"), Faker("en_US")]
    for i, f in enumerate(fakers):
        f.seed_instance(seed + i)
    exclude = {n.lower() for n in (exclude_names or set())}
    cols: list[dict[str, Any]] = []

    def add(c: dict[str, Any]) -> None:
        if c["column"].lower() not in exclude:
            cols.append(c)

    for spec in SPECS:
        count = int(n_per_category * spec.get("weight", 0.5 if spec.get("sparse") else 1.0))
        for _ in range(count):
            fk = fakers[0] if r.random() < 0.8 else fakers[1]
            add(_column(r, fk, spec["cat"], spec["names"], spec["tables"], spec["types"], spec["gen"], spec.get("sparse", False)))
    for _ in range(n_none):
        names, types, gen = r.choice(NONE_GENS)
        add(_column(r, fakers[0], "NONE", names, ANY_TABLES + ORG_TABLES, types, gen))
    r.shuffle(cols)
    return cols
