from __future__ import annotations

CONSUMER_EMAIL_DOMAINS = {
    "aol.com",
    "fastmail.com",
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "mail.com",
    "me.com",
    "msn.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
    "ymail.com",
}
COUNTRY_CODE_SECOND_LEVEL_DOMAINS = {"ac", "co", "com", "gov", "net", "org"}
BRAND_OVERRIDES = {
    "docusign": "DocuSign",
    "facebook": "Facebook",
    "facebookmail": "Facebook",
    "github": "GitHub",
    "google": "Google",
    "linkedin": "LinkedIn",
    "openai": "OpenAI",
    "upwork": "Upwork",
}


def local_part_display_name(email_address: str) -> str:
    local_part = email_address.strip().split("@", 1)[0]
    return local_part.replace(".", " ").replace("_", " ").replace("-", " ").title()


def email_domain_brand(email_address: str) -> str | None:
    normalized = email_address.strip().lower()
    if "@" not in normalized:
        return None
    domain = normalized.rsplit("@", 1)[1].strip(".")
    if not domain or domain in CONSUMER_EMAIL_DOMAINS:
        return None
    labels = [label for label in domain.split(".") if label]
    if len(labels) < 2:
        return None
    root_index = -2
    if (
        len(labels) >= 3
        and len(labels[-1]) == 2
        and labels[-2] in COUNTRY_CODE_SECOND_LEVEL_DOMAINS
    ):
        root_index = -3
    root = labels[root_index]
    compact_root = "".join(character for character in root if character.isalnum())
    if compact_root in BRAND_OVERRIDES:
        return BRAND_OVERRIDES[compact_root]
    label = root.replace("-", " ").replace("_", " ").strip()
    return label.title() or None


def fallback_email_contact_name(email_address: str) -> str:
    return (
        email_domain_brand(email_address) or local_part_display_name(email_address) or email_address
    )


def general_email_display_name(current_name: str, email_address: str | None) -> str:
    name = current_name.strip()
    if not email_address:
        return name
    legacy_fallback = local_part_display_name(email_address)
    if name.casefold() != legacy_fallback.casefold():
        return name
    return email_domain_brand(email_address) or name
