import re
from typing import Tuple


class BankingDataSanitizer:
    """
    Privacy, Data Minimization, and Prompt-Injection Defense for Banking AI.
    Redacts sensitive payment credentials (PAN, PIN, CVV, Account Numbers, Phone, Email)
    and enforces safe boundary tags around untrusted customer narratives.
    """

    # 13 to 19 digit PAN regex with Luhn-like or card structure
    CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    # 10-digit NUBAN account numbers
    ACCOUNT_REGEX = re.compile(r"\b\d{10}\b")
    # 3-4 digit CVV/CVC near keywords
    CVV_REGEX = re.compile(r"(?i)\b(?:cvv|cvc|security code)[\s:=]+(\d{3,4})\b")
    # 4-6 digit PIN near keywords
    PIN_REGEX = re.compile(r"(?i)\b(?:pin|passcode)[\s:=]+(\d{4,6})\b")
    # Email
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    # Phone numbers (+234 or local 11-digit)
    PHONE_REGEX = re.compile(r"(?:\+?234|0)[789][01]\d{8}\b")

    @classmethod
    def redact_sensitive_data(cls, text: str) -> Tuple[str, bool]:
        """
        Redacts sensitive financial PII from text before passing to external AI models.
        Returns (redacted_text, was_redacted).
        """
        if not text:
            return "", False

        original = text
        redacted = text

        # 1. Redact CVV / CVC
        redacted = cls.CVV_REGEX.sub(r"[CVV_REDACTED]", redacted)

        # 2. Redact PINs
        redacted = cls.PIN_REGEX.sub(r"[PIN_REDACTED]", redacted)

        # 3. Redact Card numbers (preserving last 4 digits if possible)
        def mask_card(match):
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) >= 13 and len(digits) <= 19:
                return f"[CARD_REDACTED_*{digits[-4:]}]"
            return match.group(0)

        redacted = cls.CARD_REGEX.sub(mask_card, redacted)

        # 4. Mask 10-digit bank account numbers (preserve last 4 digits)
        def mask_nuban(match):
            num = match.group(0)
            return f"******{num[-4:]}"

        redacted = cls.ACCOUNT_REGEX.sub(mask_nuban, redacted)

        # 5. Redact Email
        redacted = cls.EMAIL_REGEX.sub(r"[EMAIL_REDACTED]", redacted)

        # 6. Redact Phone
        redacted = cls.PHONE_REGEX.sub(r"[PHONE_REDACTED]", redacted)

        was_redacted = redacted != original
        return redacted, was_redacted

    @classmethod
    def wrap_untrusted_input(cls, text: str, source_label: str = "customer_complaint") -> str:
        """
        Defends against prompt injection by isolating untrusted external content
        within explicit XML delimiter boundaries and instructing the LLM to treat it as data only.
        """
        redacted_text, _ = cls.redact_sensitive_data(text)
        # Strip potential XML boundary breakout attempts
        sanitized = redacted_text.replace("</untrusted_input>", "").replace("<untrusted_input>", "")
        return (
            f"<{source_label}>\n"
            f"{sanitized}\n"
            f"</{source_label}>"
        )
