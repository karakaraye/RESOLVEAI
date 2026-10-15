import re
from typing import Dict, Any, Tuple
from django.core.exceptions import ValidationError
from apps.communications.models import MessageTemplate


class TemplateValidationError(ValidationError):
    """Raised when a template violates variable constraints or security policies."""
    pass


class TemplateEngine:
    """
    Safe rendering and sanitisation engine for customer communications.
    Enforces strict permitted variable sets and scrubs sensitive banking data
    (PANs, PINs, CVVs, passwords) from outbound messages.
    """

    # Approved variable allowlist for customer-facing templates
    GLOBAL_APPROVED_VARIABLES = {
        "customer_name",
        "complaint_reference",
        "resolution_outcome",
        "delay_reason",
        "institution_name",
        "support_contact",
        "reopen_reason",
        "category_label",
        "request_details",
        "incident_reference",
    }

    # Prohibited sensitive fields that MUST NEVER appear in customer communications
    PROHIBITED_SENSITIVE_VARIABLES = {
        "card_number",
        "pan",
        "pin",
        "cvv",
        "cvc",
        "password",
        "auth_token",
        "token",
        "secret",
        "account_balance",
        "balance",
        "raw_balance",
        "bvn",
        "nin",
        "ssn",
        "credentials",
    }

    # Sensitive patterns to scrub/mask
    CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    SENSITIVE_KEYWORD_PATTERN = re.compile(
        r"(?i)\b(pin|cvv|cvc|password|auth_token|otp)\s*[:=]\s*([a-zA-Z0-9_\-]+)"
    )

    @classmethod
    def sanitize_content(cls, text: str) -> str:
        """
        Masks full card numbers, CVVs, PINs, and credentials.
        Never allow raw 16-digit PANs to escape into customer emails or SMS.
        """
        if not text:
            return ""

        # Mask PANs to last 4 digits
        def mask_card(match):
            raw = re.sub(r"[ -]", "", match.group(0))
            if len(raw) in (15, 16, 19):
                return f"**** **** **** {raw[-4:]}"
            return match.group(0)

        sanitized = cls.CARD_PATTERN.sub(mask_card, text)

        # Redact PIN/CVV/OTP keywords
        def redact_secret(match):
            keyword = match.group(1)
            return f"{keyword}: [REDACTED]"

        sanitized = cls.SENSITIVE_KEYWORD_PATTERN.sub(redact_secret, sanitized)
        return sanitized

    @classmethod
    def validate_template_variables(cls, body_template: str, permitted_variables: list[str]) -> None:
        """
        Ensures that all placeholder tokens in body_template belong to permitted_variables
        and strictly adhere to privacy standards (rejecting prohibited banking secrets).
        """
        found_tokens = re.findall(r"\{([a-zA-Z0-9_]+)\}", body_template)
        permitted_set = set(permitted_variables or [])

        # Check for prohibited variables
        prohibited = [tok for tok in found_tokens if tok.lower() in cls.PROHIBITED_SENSITIVE_VARIABLES]
        if prohibited:
            raise TemplateValidationError(
                f"Security violation: Template exposes prohibited financial or credential fields: {', '.join(prohibited)}."
            )

        disallowed = [tok for tok in found_tokens if tok not in permitted_set]
        if disallowed:
            raise TemplateValidationError(
                f"Template contains unapproved placeholder variables: {', '.join(disallowed)}. "
                f"Permitted variables are: {', '.join(sorted(permitted_set))}."
            )

    @classmethod
    def render(
        cls,
        template: MessageTemplate,
        context: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Renders a versioned MessageTemplate with context.
        Returns (rendered_subject, rendered_body) with full sanitisation applied.
        """
        if not template.is_approved:
            raise TemplateValidationError(
                f"Cannot render unapproved template '{template.code}' (v{template.version})."
            )

        # Validate variables against approval specification
        cls.validate_template_variables(template.body_template, template.permitted_variables)

        # Build clean string dictionary with safe defaults
        safe_context = {}
        for var in template.permitted_variables:
            raw_val = context.get(var, "")
            # Ensure no nested braces or unvetted scripts
            clean_val = str(raw_val).strip() if raw_val is not None else ""
            clean_val = cls.sanitize_content(clean_val)
            safe_context[var] = clean_val

        # Safe python format substitution
        try:
            rendered_body = template.body_template.format(**safe_context)
        except KeyError as e:
            raise TemplateValidationError(f"Missing required context variable for template: {e}")

        rendered_subject = template.subject
        if rendered_subject:
            # Also safely substitute subject if placeholders present
            subject_tokens = re.findall(r"\{([a-zA-Z0-9_]+)\}", rendered_subject)
            for tok in subject_tokens:
                if tok in safe_context:
                    rendered_subject = rendered_subject.replace(f"{{{tok}}}", safe_context[tok])

        # Final sanitisation pass on rendered output
        rendered_subject = cls.sanitize_content(rendered_subject)
        rendered_body = cls.sanitize_content(rendered_body)

        return rendered_subject, rendered_body
