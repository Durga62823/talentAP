from decimal import Decimal

from app import masking as m


def test_full_redaction():
    assert m.apply("REDACT", "john@example.com", "EMAIL") == "[REDACTED]"
    assert m.apply("REDACT", 9876543210, "PHONE") == "[REDACTED]"


def test_partial_examples_from_spec():
    assert m.apply("PARTIAL", "4111111111111111", "CREDIT_CARD") == "4111-XXXX-XXXX-1111"
    assert m.apply("PARTIAL", "john@example.com", "EMAIL") == "j***@example.com"
    assert m.apply("PARTIAL", "9876543210", "PHONE") == "******3210"
    assert m.apply("PARTIAL", "123456789012", "ACCOUNT_NUMBER") == "********9012"


def test_amex_and_spaced_card():
    assert m.apply("PARTIAL", "378282246310005", "CREDIT_CARD") == "3782-XXXX-XXX-0005"
    assert m.apply("PARTIAL", "5555 5555 5555 4444", "CREDIT_CARD") == "5555-XXXX-XXXX-4444"


def test_hmac_deterministic_and_keyed():
    a = m.apply("HASH", "asha@inbox.example", "EMAIL")
    assert a == m.apply("HASH", "ASHA@inbox.example ", "EMAIL")  # normalised
    assert a != m.apply("HASH", "asha@inbox.org", "EMAIL")
    assert a.startswith("hm_k1_") and "asha" not in a
    # domain separation: same string, different category -> different pseudonym
    assert m.apply("HASH", "1234", "CUSTOMER_ID") != m.apply("HASH", "1234", "ACCOUNT_NUMBER")


def test_null_and_empty():
    for action in m.ACTIONS:
        assert m.apply(action, None, "EMAIL") is None
    assert m.apply("PARTIAL", "", "EMAIL") == ""


def test_unicode_inputs():
    assert m.apply("PARTIAL", "José Núñez", "PERSON_NAME") == "J*** N****"
    assert m.apply("PARTIAL", "zoë@example.com", "EMAIL") == "z***@example.com"
    assert m.apply("HASH", "Zoë", "PERSON_NAME").startswith("hm_")


def test_short_and_malformed_values():
    assert m.apply("PARTIAL", "12", "PHONE") == "****"
    assert m.apply("PARTIAL", "987", "ACCOUNT_NUMBER") == "****"
    assert m.apply("PARTIAL", "not-an-email", "EMAIL") == "***-**-*mail"
    assert m.apply("PARTIAL", "@", "EMAIL") == "[REDACTED]"
    assert m.apply("PARTIAL", "41", "CREDIT_CARD") == "****"


def test_amounts_never_get_fake_digits():
    out = m.apply("PARTIAL", Decimal("15234.50"), "FINANCIAL_AMOUNT")
    assert out == "10,000–50,000"
    assert m.apply("GENERALIZE", -12, "FINANCIAL_AMOUNT") == "< 0"
    assert m.apply("GENERALIZE", "1987-04-12", "DATE_OF_BIRTH") == "1987"


def test_non_sensitive_allow_passthrough():
    assert m.apply("ALLOW", 42, "NONE") == 42
    assert m.apply("ALLOW", "retail", "NONE") == "retail"


def test_unknown_action_fails_closed():
    assert m.apply("SOMETHING_NEW", "secret", "EMAIL") == "[REDACTED]"


def test_free_text_span_masking():
    out = m.apply("PARTIAL", "Call +1-202-555-0143, card 4111111111111111", "FREE_TEXT_PII")
    assert "555-0143" not in out and "4111111111111111" not in out and "4111-XXXX-XXXX-1111" in out
