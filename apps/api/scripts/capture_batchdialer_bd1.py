from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx

BASE_URL = "https://app.batchdialer.com/api"
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "batchdialer"
    / "bd1"
    / "v1"
)
LOCAL_CAPTURE_ENV_PATH = Path.home() / ".stonegate" / "batchdialer_bd1.env"
CAPTURE_TOOL_VERSION = "1.4"
SANITIZATION_PROFILE = "stonegate_bd1_strict_v1"
MAX_RESPONSE_BYTES = 1_000_000
MAX_RUN_BYTES = 2_000_000
MAX_REQUESTS = 8
MAX_CDR_PAGE_LENGTH = 5

DOCUMENTATION_URLS = {
    "campaigns_active": (
        "get_campaigns",
        "https://developer.batchdialer.com/docs/batchdialer/h2xkp24zesogx-get-campaigns",
    ),
    "campaign_search_page_one": (
        "campaign_search",
        "https://developer.batchdialer.com/docs/batchdialer/rw0nq2fp5bu7a-search",
    ),
    "campaign_search_page_two": (
        "campaign_search",
        "https://developer.batchdialer.com/docs/batchdialer/rw0nq2fp5bu7a-search",
    ),
    "target_contact": (
        "contact_retrieval",
        "https://developer.batchdialer.com/docs/batchdialer/q2v2uqf6v4uig-get-single-contact-by-id",
    ),
    "cdr_cursor_page_one": (
        "cdr_pagination",
        "https://developer.batchdialer.com/docs/batchdialer/kjto0ggvaavor-get-recent-contacts-v2",
    ),
    "cdr_cursor_page_two": (
        "cdr_pagination",
        "https://developer.batchdialer.com/docs/batchdialer/kjto0ggvaavor-get-recent-contacts-v2",
    ),
    "target_call_history": (
        "vendor_contact_call_history",
        "https://developer.batchdialer.com/docs/batchdialer/j8znbe36cqcm6-get-recent-calls-by-vendor-contact-id",
    ),
    "target_transcript": (
        "transcript_json",
        "https://developer.batchdialer.com/docs/batchdialer/1ipr1j1l9zkyn-get-transcription-json",
    ),
    "authentication_failure": (
        "getting_started",
        "https://developer.batchdialer.com/docs/batchdialer/f4e6fa31af431-getting-started",
    ),
}

ALLOWED_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "retry-after",
    "x-request-id",
    "x-correlation-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
}
FORBIDDEN_KEY_PARTS = {
    "authorization",
    "cookie",
    "apikey",
    "api_key",
    "access_token",
    "refresh_token",
    "securityphrase",
    "secret",
    "password",
    "signed_url",
}
ENUM_KEYS = {
    "callresult",
    "call_result",
    "calltype",
    "call_type",
    "direction",
    "disposition",
    "mode",
    "mood",
    "numbertype",
    "role",
    "status",
    "type",
}
SAFE_ENUM_VALUES = {
    "active",
    "answering machine",
    "appointment set",
    "callback",
    "completed",
    "do not call",
    "inbound",
    "inactive",
    "mobile",
    "no answer",
    "not interested",
    "outbound",
    "predictive",
    "qualified seller - follow up",
    "successful sale",
    "voicemail",
    "wrong number",
}
METRIC_KEYS = {
    "abandon",
    "agents",
    "answered",
    "companydnccount",
    "contacts",
    "dialedcount",
    "dnrcount",
    "duration",
    "level",
    "newleads",
    "numberofcontacts",
    "page",
    "pagelength",
    "recyclecount",
    "redialscount",
    "totalpages",
    "voicemail",
}
TIMESTAMP_KEYS = {
    "callendtime",
    "callstarttime",
    "capturedat",
    "dateadded",
    "date_added",
    "datedeleted",
    "datemodified",
    "date_time",
    "time",
}
PHONE_KEYS = {
    "ani",
    "customernumber",
    "did",
    "dnis",
    "from",
    "mobile",
    "phone",
    "phoneno",
    "phone_no",
    "to",
}
TEXT_KEYS = {
    "comment",
    "comments",
    "description",
    "note",
    "notes",
    "summary",
    "text",
    "transcript",
}
URL_KEYS = {
    "attachment",
    "attachments",
    "callrecordurl",
    "media",
    "recording",
    "recordingurl",
    "url",
}
KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
SAFE_LABEL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z '\-\u2013\u2014/&]{0,79}$")
SAFE_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
ALLOWED_CAPTURE_ENV_KEYS = {
    "BATCHDIALER_BD1_API_KEY",
    "BATCHDIALER_BD1_CALL_DATE",
    "BATCHDIALER_BD1_CAMPAIGN_ID",
    "BATCHDIALER_BD1_CDR_ID",
    "BATCHDIALER_BD1_CONTACT_ID",
    "BATCHDIALER_BD1_CONTROLLED_CAMPAIGN_CONFIRMED",
    "BATCHDIALER_BD1_VENDOR_CONTACT_ID",
}

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
RootKind = Literal["list", "dict", "any"]
ResponseSelector = Callable[[JsonValue], JsonValue]

OPERATION_CONTRACTS: dict[str, tuple[str, str, RootKind]] = {
    "campaigns_active": ("GET", "/campaigns", "list"),
    "campaign_search_page_one": ("POST", "/campaigns/search", "list"),
    "campaign_search_page_two": ("POST", "/campaigns/search", "list"),
    "target_contact": ("GET", "/contact/{contactID}", "dict"),
    "cdr_cursor_page_one": ("GET", "/v2/cdrs", "dict"),
    "cdr_cursor_page_two": ("GET", "/v2/cdrs", "dict"),
    "target_call_history": ("POST", "/cdrs/by-lead-id", "list"),
    "target_transcript": ("GET", "/cdrs/{cdrID}/transcription", "list"),
}

ACTIVE_CAMPAIGN_RESPONSE_KEYS = {
    "dateadded",
    "externalid",
    "id",
    "level",
    "mode",
    "name",
    "numberofcontacts",
    "parentid",
    "recyclecount",
    "status",
}
CAMPAIGN_SEARCH_RESPONSE_KEYS = {
    "abandon",
    "agents",
    "agentslist",
    "answered",
    "answermode",
    "companydnccount",
    "contacts",
    "dateadded",
    "deals",
    "dialerstatus",
    "dnc",
    "dnr",
    "id",
    "level",
    "mode",
    "name",
    "newleads",
    "parentid",
    "parents",
    "recyclecount",
    "redials",
    "ringtone",
    "scrubcompany",
    "scrubfederal",
    "status",
    "updating",
    "voicemail",
    "worktime",
}
# BatchDialer currently returns ``externalid`` from /campaigns/search even though
# its operation schema documents that field only as a request filter. The same
# field is formally documented in the GET /campaigns response, so this exact
# provider addition is reviewed and masked while all other schema drift remains
# fail-closed.
CAMPAIGN_SEARCH_COMPATIBILITY_KEYS = {"externalid"}
CONTACT_RESPONSE_KEYS = {
    "address",
    "addressurls",
    "answered",
    "calldate",
    "campaignscount",
    "city",
    "clientid",
    "comments",
    "contactid",
    "country",
    "currentagentid",
    "customfields",
    "dateadded",
    "dateofbirth",
    "datelasttouched",
    "datemodified",
    "dialedcount",
    "disposition",
    "dnc",
    "email",
    "federaldnc",
    "firstname",
    "gender",
    "id",
    "lastcallid",
    "lastname",
    "lists",
    "listscount",
    "mailingaddress",
    "mailingcity",
    "mailingpostalcode",
    "mailingstate",
    "middlename",
    "numberid",
    "numbertype",
    "phonenumber",
    "phonenumber1",
    "phonenumbers",
    "postalcode",
    "reachable",
    "recalcscore",
    "score",
    "securityphrase",
    "state",
    "stats",
    "status",
    "tested",
    "title",
    "vendorcontactid",
    "voicemail",
}
CDR_RESPONSE_KEYS = {
    "address",
    "agent",
    "callendtime",
    "callid",
    "callrecordurl",
    "callstarttime",
    "campaign",
    "city",
    "client",
    "comments",
    "contact",
    "customernumber",
    "did",
    "direction",
    "disposition",
    "duration",
    "email",
    "firstname",
    "id",
    "items",
    "lastname",
    "mood",
    "name",
    "nextpage",
    "recordingenabled",
    "state",
    "status",
    "voicemailid",
    "zip",
}
CALL_HISTORY_RESPONSE_KEYS = {
    "agent",
    "attachments",
    "callresult",
    "calltype",
    "campaign",
    "datetime",
    "duration",
    "noteonly",
    "notes",
    "phoneno",
}
TRANSCRIPT_RESPONSE_KEYS = {"role", "text", "time"}
RESPONSE_KEY_ALLOWLISTS = {
    "campaigns_active": ACTIVE_CAMPAIGN_RESPONSE_KEYS,
    "campaign_search_page_one": (
        CAMPAIGN_SEARCH_RESPONSE_KEYS | CAMPAIGN_SEARCH_COMPATIBILITY_KEYS
    ),
    "campaign_search_page_two": (
        CAMPAIGN_SEARCH_RESPONSE_KEYS | CAMPAIGN_SEARCH_COMPATIBILITY_KEYS
    ),
    "target_contact": CONTACT_RESPONSE_KEYS,
    "cdr_cursor_page_one": CDR_RESPONSE_KEYS,
    "cdr_cursor_page_two": CDR_RESPONSE_KEYS,
    "target_call_history": CALL_HISTORY_RESPONSE_KEYS,
    "target_transcript": TRANSCRIPT_RESPONSE_KEYS,
}

class CaptureError(RuntimeError):
    """A secret-free failure from the bounded BD1 evidence capture."""


def load_local_capture_environment(path: Path = LOCAL_CAPTURE_ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.stat().st_size > 16_384:
        raise CaptureError("The local BD1 environment file is unexpectedly large.")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CaptureError(f"The local BD1 environment file has an invalid line {line_number}.")
        key, value = (part.strip() for part in line.split("=", 1))
        if not ENV_KEY_PATTERN.fullmatch(key) or key not in ALLOWED_CAPTURE_ENV_KEYS:
            raise CaptureError(
                f"The local BD1 environment file has a forbidden key on line {line_number}."
            )
        if key in values:
            raise CaptureError(
                f"The local BD1 environment file repeats a key on line {line_number}."
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class CaptureConfig:
    api_key: str = field(repr=False)
    campaign_id: str = field(repr=False)
    contact_id: str = field(repr=False)
    call_date: str = field(repr=False)
    controlled_campaign_confirmed: bool
    vendor_contact_id: str | None = field(default=None, repr=False)
    cdr_id: str | None = field(default=None, repr=False)
    timeout_seconds: float = 10.0
    cdr_page_length: int = MAX_CDR_PAGE_LENGTH

    def __post_init__(self) -> None:
        if len(self.api_key.strip()) < 16:
            raise CaptureError("BATCHDIALER_BD1_API_KEY is missing or implausibly short.")
        if not self.controlled_campaign_confirmed:
            raise CaptureError(
                "BATCHDIALER_BD1_CONTROLLED_CAMPAIGN_CONFIRMED must be true before capture."
            )
        for label, value in (
            ("campaign", self.campaign_id),
            ("contact", self.contact_id),
        ):
            if not SAFE_PATH_SEGMENT_PATTERN.fullmatch(value):
                raise CaptureError(f"The controlled {label} identifier has an invalid format.")
        if self.vendor_contact_id and not SAFE_PATH_SEGMENT_PATTERN.fullmatch(
            self.vendor_contact_id
        ):
            raise CaptureError("The controlled vendor-contact identifier has an invalid format.")
        if self.cdr_id and not self.cdr_id.isdecimal():
            raise CaptureError("The controlled CDR identifier must be numeric.")
        try:
            datetime.fromisoformat(self.call_date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CaptureError("BATCHDIALER_BD1_CALL_DATE must be ISO 8601.") from exc
        if not 1 <= self.cdr_page_length <= MAX_CDR_PAGE_LENGTH:
            raise CaptureError(
                f"The BD1 CDR page length must be between 1 and {MAX_CDR_PAGE_LENGTH}."
            )

    @classmethod
    def from_environment(cls) -> CaptureConfig:
        local_values = load_local_capture_environment()
        environment_values = {
            name: os.environ.get(name, "") for name in ALLOWED_CAPTURE_ENV_KEYS
        }
        environment_has_values = any(value for value in environment_values.values())
        local_has_values = any(value for value in local_values.values())
        if environment_has_values and local_has_values:
            raise CaptureError(
                "BD1 capture inputs must come entirely from either the process environment "
                "or the fixed local capture file, not both."
            )
        source = environment_values if environment_has_values else local_values

        def value(name: str) -> str:
            return source.get(name, "")

        required = {
            "api_key": value("BATCHDIALER_BD1_API_KEY"),
            "campaign_id": value("BATCHDIALER_BD1_CAMPAIGN_ID"),
            "contact_id": value("BATCHDIALER_BD1_CONTACT_ID"),
            "call_date": value("BATCHDIALER_BD1_CALL_DATE"),
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            names = ", ".join(
                {
                    "api_key": "BATCHDIALER_BD1_API_KEY",
                    "campaign_id": "BATCHDIALER_BD1_CAMPAIGN_ID",
                    "contact_id": "BATCHDIALER_BD1_CONTACT_ID",
                    "call_date": "BATCHDIALER_BD1_CALL_DATE",
                }[name]
                for name in missing
            )
            raise CaptureError(f"Missing required environment configuration: {names}.")
        return cls(
            **required,
            controlled_campaign_confirmed=value(
                "BATCHDIALER_BD1_CONTROLLED_CAMPAIGN_CONFIRMED"
            ).strip().lower()
            == "true",
            vendor_contact_id=value("BATCHDIALER_BD1_VENDOR_CONTACT_ID") or None,
            cdr_id=value("BATCHDIALER_BD1_CDR_ID") or None,
        )


@dataclass(frozen=True)
class Operation:
    operation_id: str
    method: Literal["GET", "POST"]
    path: str = field(repr=False)
    path_template: str
    root_kind: RootKind
    params: Mapping[str, str | int] | None = field(default=None, repr=False)
    body: Mapping[str, Any] | None = field(default=None, repr=False)
    expected_statuses: frozenset[int] = frozenset(range(200, 300))

    def __post_init__(self) -> None:
        contract = OPERATION_CONTRACTS.get(self.operation_id)
        if self.operation_id not in DOCUMENTATION_URLS or contract is None:
            raise CaptureError("The capture operation is not allowlisted.")
        expected_method, expected_path_template, expected_root_kind = contract
        if (
            self.method != expected_method
            or self.path_template != expected_path_template
            or self.root_kind != expected_root_kind
        ):
            raise CaptureError("The capture operation does not match its fixed contract.")
        if expected_path_template == "/contact/{contactID}":
            valid_path = re.fullmatch(r"/contact/[A-Za-z0-9_-]{1,80}", self.path)
        elif expected_path_template == "/cdrs/{cdrID}/transcription":
            valid_path = re.fullmatch(r"/cdrs/[0-9]{1,20}/transcription", self.path)
        else:
            valid_path = self.path == expected_path_template
        if not valid_path or self.path.startswith("/v2/cdrs/last"):
            raise CaptureError("The capture path is forbidden.")
        self._validate_request_shape()

    def _validate_request_shape(self) -> None:
        params = dict(self.params or {})
        body = dict(self.body or {})
        if self.operation_id in {
            "campaigns_active",
            "target_contact",
            "target_transcript",
        }:
            if params or body:
                raise CaptureError("The fixed capture operation does not accept input data.")
            return
        if self.operation_id.startswith("campaign_search_page_"):
            expected_page = 1 if self.operation_id.endswith("one") else 2
            expected_body = {
                "sortfield": "campaigns.id",
                "sortdir": "desc",
                "pagelength": 1,
                "page": expected_page,
            }
            if params or body != expected_body:
                raise CaptureError("The campaign-search request does not match the fixed plan.")
            return
        if self.operation_id.startswith("cdr_cursor_page_"):
            expected_keys = {"pagelength", "callDate"}
            if self.operation_id.endswith("two"):
                expected_keys.add("next_page")
            if body or set(params) != expected_keys:
                raise CaptureError("The CDR request does not match the fixed plan.")
            page_length = params.get("pagelength")
            if not isinstance(page_length, int) or not 1 <= page_length <= MAX_CDR_PAGE_LENGTH:
                raise CaptureError("The CDR page length is outside the capture boundary.")
            try:
                datetime.fromisoformat(str(params["callDate"]).replace("Z", "+00:00"))
            except ValueError as exc:
                raise CaptureError("The CDR call date is not valid ISO 8601.") from exc
            if "next_page" in params:
                cursor = params["next_page"]
                if not isinstance(cursor, str) or not 1 <= len(cursor) <= 512:
                    raise CaptureError("The CDR cursor is outside the capture boundary.")
            return
        if self.operation_id == "target_call_history":
            vendor_contact_id = body.get("vendor_contact_id")
            if (
                params
                or set(body) != {"vendor_contact_id"}
                or not isinstance(vendor_contact_id, str)
                or not SAFE_PATH_SEGMENT_PATTERN.fullmatch(vendor_contact_id)
            ):
                raise CaptureError("The call-history request does not match the fixed plan.")
            return
        raise CaptureError("The capture request shape is not allowlisted.")


@dataclass(frozen=True)
class CaptureResult:
    operation_id: str
    status_code: int
    sha256: str
    fixture_path: Path


class AliasBook:
    def __init__(self) -> None:
        self._aliases: dict[tuple[str, type[object], str], int] = {}

    def ordinal(self, kind: str, value: object) -> int:
        key = (kind, type(value), str(value))
        if key not in self._aliases:
            self._aliases[key] = len(
                [known for known in self._aliases if known[0] == kind]
            ) + 1
        return self._aliases[key]

    def identifier(self, kind: str, value: object) -> str | int | float:
        ordinal = self.ordinal(kind, value)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return 9_000_000 + ordinal
        if isinstance(value, float):
            return float(9_000_000 + ordinal)
        return f"{kind}-{ordinal:03d}"

    def phone(self, value: object) -> str | int | float:
        ordinal = ((self.ordinal("phone", value) - 1) % 100) + 1
        digits = 2_025_550_099 + ordinal
        if isinstance(value, int):
            return digits
        if isinstance(value, float):
            return float(digits)
        return f"+1{digits}"

    def timestamp(self, value: object) -> str | int | float:
        ordinal = self.ordinal("timestamp", value)
        if isinstance(value, int):
            return 946_684_800_000 + ordinal
        if isinstance(value, float):
            return float(946_684_800_000 + ordinal)
        shifted = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=ordinal)
        return shifted.isoformat().replace("+00:00", "Z")


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def strict_json_loads(raw: bytes) -> JsonValue:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CaptureError("BatchDialer returned JSON containing duplicate object keys.")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("BatchDialer returned invalid JSON.") from exc


def _identifier_kind(key: str) -> str:
    if "campaign" in key or key == "parentid":
        return "campaign"
    if "contact" in key or "lead" in key:
        return "contact"
    if "agent" in key:
        return "agent"
    if "call" in key or "cdr" in key:
        return "call"
    if "list" in key:
        return "list"
    if "external" in key:
        return "external"
    if "cursor" in key or "nextpage" in key:
        return "cursor"
    return "id"


def _is_identifier_key(key: str) -> bool:
    return (
        key == "id"
        or key.endswith("id")
        or key.endswith("ids")
        or key in {"nextpage", "parentid"}
    )


def _is_phone_key(key: str) -> bool:
    return key in PHONE_KEYS or "phone" in key or key.endswith("number")


def _project_scalar(
    value: str | int | float | bool | None,
    key: str,
    aliases: AliasBook,
    *,
    mask_operational_values: bool,
) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str) and not value.strip():
        return value
    if _is_phone_key(key):
        return aliases.phone(value)
    if _is_identifier_key(key):
        return aliases.identifier(_identifier_kind(key), value)
    if "email" in key:
        ordinal = aliases.ordinal("email", value)
        return f"seller{ordinal}@example.com"
    if "address" in key or key in {"street", "street1", "street2"}:
        ordinal = aliases.ordinal("address", value)
        return f"{100 + ordinal} Example Street"
    if key in {"city", "mailingcity"}:
        return "Example City"
    if key in {"state", "mailingstate"}:
        return "GA"
    if "zip" in key or "postal" in key:
        return "30303" if isinstance(value, str) else 30303
    if key in {"birthday", "dateofbirth", "dob"}:
        return "1970-01-01" if isinstance(value, str) else 0
    if key in TEXT_KEYS or any(token in key for token in TEXT_KEYS):
        return "[REDACTED CONTROLLED TEXT]" if isinstance(value, str) else 0
    if key in URL_KEYS or any(token in key for token in URL_KEYS):
        return "[REDACTED URL]" if isinstance(value, str) else 0
    if "campaign" in key and isinstance(value, str):
        ordinal = aliases.ordinal("campaign_name", value)
        return f"Controlled Campaign {ordinal}"
    if "agent" in key and isinstance(value, str):
        ordinal = aliases.ordinal("agent_name", value)
        return f"Fictional Agent {ordinal}"
    if "name" in key and isinstance(value, str):
        ordinal = aliases.ordinal("person_name", value)
        return f"Fictional Person {ordinal}"
    if key in ENUM_KEYS:
        if isinstance(value, str):
            normalized_value = re.sub(
                r"[\u2013\u2014]",
                "-",
                value.strip().lower(),
            )
            if (
                normalized_value in SAFE_ENUM_VALUES
                and SAFE_LABEL_PATTERN.fullmatch(value)
            ):
                return value
            ordinal = aliases.ordinal(f"enum_{key}", value)
            return f"Observed Enum {ordinal}"
        return "[REDACTED ENUM]" if isinstance(value, str) else value
    if key in TIMESTAMP_KEYS or "date" in key or key.endswith("time"):
        return aliases.timestamp(value) if mask_operational_values else value
    if key in METRIC_KEYS or key.endswith("count") or key.startswith("numberof"):
        if mask_operational_values:
            if isinstance(value, int):
                return 0
            if isinstance(value, float):
                return 0.0
        return value
    if isinstance(value, str):
        return "[REDACTED]"
    if isinstance(value, int):
        return 0
    return 0.0


def project_json(
    value: JsonValue,
    aliases: AliasBook,
    key: str = "root",
    *,
    allowed_keys: set[str] | None = None,
    mask_operational_values: bool = False,
    quarantined_property_fingerprints: set[str] | None = None,
) -> JsonValue:
    normalized_key = normalize_key(key)
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if not KEY_PATTERN.fullmatch(child_key):
                raise CaptureError("BatchDialer returned an unsafe JSON property name.")
            child_normalized = normalize_key(child_key)
            if allowed_keys is not None and child_normalized not in allowed_keys:
                property_fingerprint = hashlib.sha256(
                    child_normalized.encode("utf-8")
                ).hexdigest()[:12]
                if quarantined_property_fingerprints is not None:
                    quarantined_property_fingerprints.add(property_fingerprint)
                    continue
                raise CaptureError(
                    "BatchDialer returned an undocumented JSON property "
                    f"(fingerprint {property_fingerprint})."
                )
            if any(part in child_normalized for part in FORBIDDEN_KEY_PARTS):
                continue
            projected[child_key] = project_json(
                child_value,
                aliases,
                child_key,
                allowed_keys=allowed_keys,
                mask_operational_values=mask_operational_values,
                quarantined_property_fingerprints=quarantined_property_fingerprints,
            )
        return projected
    if isinstance(value, list):
        return [
            project_json(
                item,
                aliases,
                key,
                allowed_keys=allowed_keys,
                mask_operational_values=mask_operational_values,
                quarantined_property_fingerprints=quarantined_property_fingerprints,
            )
            for item in value
        ]
    return _project_scalar(
        value,
        normalized_key,
        aliases,
        mask_operational_values=mask_operational_values,
    )


def _lookup(record: Mapping[str, Any], *names: str) -> Any:
    wanted = {normalize_key(name) for name in names}
    for key, value in record.items():
        if normalize_key(key) in wanted:
            return value
    return None


def _matches_controlled_target(
    record: Mapping[str, Any], *, campaign_id: str, contact_id: str
) -> bool:
    record_campaign = _lookup(record, "campaignID", "campaign_id", "campaignid")
    record_contact = _lookup(record, "contactID", "contact_id", "contactid")
    nested_campaign = _lookup(record, "campaign")
    nested_contact = _lookup(record, "contact")
    if isinstance(nested_campaign, Mapping):
        record_campaign = _lookup(nested_campaign, "id")
    if isinstance(nested_contact, Mapping):
        record_contact = _lookup(nested_contact, "id")
    return (
        str(record_contact or "") == contact_id
        and str(record_campaign or "") == campaign_id
    )


def _select_campaign(campaign_id: str) -> ResponseSelector:
    def selector(payload: JsonValue) -> JsonValue:
        if not isinstance(payload, list):
            raise CaptureError("BatchDialer campaigns returned an unexpected response shape.")
        matches = [
            item
            for item in payload
            if isinstance(item, dict) and str(_lookup(item, "id") or "") == campaign_id
        ][:1]
        if not matches:
            raise CaptureError("The controlled BatchDialer campaign was not returned as active.")
        return matches

    return selector


def _select_cdr_target(
    campaign_id: str, contact_id: str, *, require_match: bool
) -> Callable[[JsonValue], JsonValue]:
    def selector(payload: JsonValue) -> JsonValue:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise CaptureError("BatchDialer CDRs returned an unexpected response shape.")
        items = [
            item
            for item in payload["items"]
            if isinstance(item, dict)
            and _matches_controlled_target(
                item,
                campaign_id=campaign_id,
                contact_id=contact_id,
            )
        ]
        if require_match and not items:
            raise CaptureError("The controlled BatchDialer contact was not found in the CDR page.")
        return {"items": items[:5], "nextPage": payload.get("nextPage")}

    return selector


def _bounded_list(max_items: int) -> ResponseSelector:
    def selector(payload: JsonValue) -> JsonValue:
        if not isinstance(payload, list):
            raise CaptureError("BatchDialer returned an unexpected list response shape.")
        return payload[:max_items]

    return selector


def _identity(payload: JsonValue) -> JsonValue:
    return payload


def _sanitize_headers(headers: httpx.Headers, aliases: AliasBook) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.lower()
        if lowered not in ALLOWED_RESPONSE_HEADERS:
            continue
        if lowered in {"x-request-id", "x-correlation-id"}:
            sanitized[lowered] = str(aliases.identifier("request", value))
        elif lowered == "content-type":
            sanitized[lowered] = value.split(";", 1)[0].strip().lower()
        elif lowered == "date":
            sanitized[lowered] = "[REDACTED PROVIDER DATE]"
        elif re.fullmatch(r"[0-9]{1,12}", value.strip()):
            sanitized[lowered] = value.strip()
        else:
            sanitized[lowered] = "[REDACTED HEADER]"
    return sanitized


def _validate_root(payload: JsonValue, root_kind: RootKind, operation_id: str) -> None:
    if root_kind == "list" and not isinstance(payload, list):
        raise CaptureError(f"{operation_id} returned an unexpected response shape.")
    if root_kind == "dict" and not isinstance(payload, dict):
        raise CaptureError(f"{operation_id} returned an unexpected response shape.")


class CaptureSession:
    def __init__(
        self,
        config: CaptureConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        fixture_root: Path = FIXTURE_ROOT,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.aliases = AliasBook()
        self.fixture_root = fixture_root.resolve()
        self.now = now or (lambda: datetime.now(UTC))
        self.run_started_at = self.now()
        self.run_id = f"{self.run_started_at:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        self.run_dir = self.fixture_root / "captured" / self.run_id
        self.request_count = 0
        self.run_bytes = 0
        self.results: list[CaptureResult] = []
        self.pending_fixtures: list[tuple[str, dict[str, Any], int]] = []
        self.client = httpx.Client(
            base_url=BASE_URL,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self) -> CaptureSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.client.close()

    def _request(
        self,
        operation: Operation,
        *,
        selector: ResponseSelector,
    ) -> tuple[JsonValue, int, dict[str, str]]:
        if self.request_count >= MAX_REQUESTS:
            raise CaptureError("The BD1 request cap was reached.")
        self.request_count += 1
        try:
            with self.client.stream(
                operation.method,
                operation.path,
                params=operation.params,
                json=operation.body,
                headers={"X-ApiKey": self.config.api_key},
            ) as response:
                if 300 <= response.status_code < 400:
                    raise CaptureError(f"{operation.operation_id} returned a forbidden redirect.")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise CaptureError(
                            f"{operation.operation_id} exceeded the response-size limit."
                        )
                    if self.run_bytes + len(raw) > MAX_RUN_BYTES:
                        raise CaptureError("The BD1 run exceeded the total response-size limit.")
                self.run_bytes += len(raw)
                status_code = response.status_code
                headers = _sanitize_headers(response.headers, self.aliases)
        except CaptureError:
            raise
        except httpx.HTTPError as exc:
            raise CaptureError(f"{operation.operation_id} could not reach BatchDialer.") from exc

        if not raw:
            payload: JsonValue = {}
        else:
            try:
                payload = strict_json_loads(bytes(raw))
            except CaptureError:
                if status_code in operation.expected_statuses:
                    raise
                payload = {"responseKind": "non_json", "responseBytes": len(raw)}
        if status_code in operation.expected_statuses:
            _validate_root(payload, operation.root_kind, operation.operation_id)
        selected = selector(payload)
        return selected, status_code, headers

    def capture(
        self,
        operation: Operation,
        *,
        selector: ResponseSelector = _identity,
        provenance: Literal[
            "controlled_account_observation", "account_schema_observation"
        ] = "controlled_account_observation",
    ) -> JsonValue:
        selected, status_code, headers = self._request(
            operation,
            selector=selector,
        )
        if status_code not in operation.expected_statuses:
            raise CaptureError(
                f"{operation.operation_id} returned unexpected HTTP {status_code}."
            )
        source_id, documentation_url = DOCUMENTATION_URLS[operation.operation_id]
        quarantined_property_fingerprints: set[str] = set()
        try:
            sanitized_response_body = project_json(
                selected,
                self.aliases,
                allowed_keys=RESPONSE_KEY_ALLOWLISTS[operation.operation_id],
                mask_operational_values=True,
                quarantined_property_fingerprints=quarantined_property_fingerprints,
            )
        except CaptureError as exc:
            raise CaptureError(
                f"{operation.operation_id} response sanitization stopped: {exc}"
            ) from exc
        fixture = {
            "schema_version": "batchdialer_bd1_capture_v1",
            "capture_tool_version": CAPTURE_TOOL_VERSION,
            "capture_run_id": self.run_id,
            "sanitization_profile": SANITIZATION_PROFILE,
            "official_source_id": source_id,
            "endpoint_documentation_url": documentation_url,
            "captured_at": self.now().isoformat().replace("+00:00", "Z"),
            "review_status": "pending_review",
            "controlled_campaign_confirmed": self.config.controlled_campaign_confirmed,
            "provenance": provenance,
            "operation": operation.operation_id,
            "request": {
                "method": operation.method,
                "path_template": operation.path_template,
                "params": project_json(dict(operation.params or {}), self.aliases),
                "body": project_json(dict(operation.body or {}), self.aliases),
            },
            "response": {
                "status": status_code,
                "headers": headers,
                "schema_drift": {
                    "undocumented_property_fingerprints": sorted(
                        quarantined_property_fingerprints
                    ),
                },
                "body": sanitized_response_body,
            },
        }
        self.pending_fixtures.append((operation.operation_id, fixture, status_code))
        return selected

    def _commit_pending_fixtures(self) -> None:
        if self.results or not self.pending_fixtures:
            raise CaptureError("The BD1 evidence run cannot be committed in its current state.")
        for operation_id, fixture, status_code in self.pending_fixtures:
            self.results.append(self._write_fixture(operation_id, fixture, status_code))

    def _write_fixture(
        self,
        operation_id: str,
        fixture: dict[str, Any],
        status_code: int,
    ) -> CaptureResult:
        self.run_dir.mkdir(parents=True, exist_ok=False) if not self.run_dir.exists() else None
        destination = (self.run_dir / f"{operation_id}.json").resolve()
        if not destination.is_relative_to(self.fixture_root):
            raise CaptureError("The fixture destination escaped the BD1 evidence directory.")
        encoded = (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=self.run_dir,
            prefix=f".{operation_id}-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(encoded)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        try:
            os.replace(temp_path, destination)
        finally:
            temp_path.unlink(missing_ok=True)
        return CaptureResult(
            operation_id=operation_id,
            status_code=status_code,
            sha256=hashlib.sha256(encoded).hexdigest(),
            fixture_path=destination,
        )

    def run(self) -> list[CaptureResult]:
        campaign_selector = _select_campaign(self.config.campaign_id)
        self.capture(
            Operation(
                "campaigns_active",
                "GET",
                "/campaigns",
                "/campaigns",
                "list",
            ),
            selector=campaign_selector,
        )
        for page in (1, 2):
            self.capture(
                Operation(
                    f"campaign_search_page_{'one' if page == 1 else 'two'}",
                    "POST",
                    "/campaigns/search",
                    "/campaigns/search",
                    "list",
                    body={
                        "sortfield": "campaigns.id",
                        "sortdir": "desc",
                        "pagelength": 1,
                        "page": page,
                    },
                ),
                selector=_bounded_list(1),
                provenance="account_schema_observation",
            )

        contact = self.capture(
            Operation(
                "target_contact",
                "GET",
                f"/contact/{self.config.contact_id}",
                "/contact/{contactID}",
                "dict",
            )
        )
        if not isinstance(contact, dict):
            raise CaptureError("The controlled contact response was not an object.")
        if str(_lookup(contact, "id") or "") != self.config.contact_id:
            raise CaptureError(
                "BatchDialer returned a different contact than the controlled target."
            )

        cdr_params: dict[str, str | int] = {
            "pagelength": self.config.cdr_page_length,
            "callDate": self.config.call_date,
        }
        first_cdr = self.capture(
            Operation(
                "cdr_cursor_page_one",
                "GET",
                "/v2/cdrs",
                "/v2/cdrs",
                "dict",
                params=cdr_params,
            ),
            selector=_select_cdr_target(
                self.config.campaign_id,
                self.config.contact_id,
                require_match=True,
            ),
        )
        raw_next_page = first_cdr.get("nextPage") if isinstance(first_cdr, dict) else None
        second_cdr: JsonValue | None = None
        if isinstance(raw_next_page, str) and raw_next_page:
            second_cdr = self.capture(
                Operation(
                    "cdr_cursor_page_two",
                    "GET",
                    "/v2/cdrs",
                    "/v2/cdrs",
                    "dict",
                    params={**cdr_params, "next_page": raw_next_page},
                ),
                selector=_select_cdr_target(
                    self.config.campaign_id,
                    self.config.contact_id,
                    require_match=False,
                ),
            )

        derived_vendor_contact_id = _lookup(
            contact,
            "vendorcontactid",
            "vendor_contact_id",
        )
        if self.config.vendor_contact_id and str(derived_vendor_contact_id or "") != str(
            self.config.vendor_contact_id
        ):
            raise CaptureError(
                "The configured vendor-contact ID does not match the controlled contact."
            )

        matched_cdr_ids: list[str] = []
        for page_payload in (first_cdr, second_cdr):
            if not isinstance(page_payload, dict):
                continue
            for item in page_payload.get("items", []):
                if not isinstance(item, dict):
                    continue
                candidate = _lookup(item, "id")
                if isinstance(candidate, int) or (
                    isinstance(candidate, str) and candidate.isdecimal()
                ):
                    matched_cdr_ids.append(str(candidate))

        if self.config.cdr_id and self.config.cdr_id not in matched_cdr_ids:
            raise CaptureError(
                "The configured CDR ID does not match the controlled campaign/contact."
            )

        vendor_contact_id = derived_vendor_contact_id
        if vendor_contact_id:
            self.capture(
                Operation(
                    "target_call_history",
                    "POST",
                    "/cdrs/by-lead-id",
                    "/cdrs/by-lead-id",
                    "list",
                    body={"vendor_contact_id": str(vendor_contact_id)},
                ),
                selector=_bounded_list(10),
            )

        cdr_id = self.config.cdr_id or (matched_cdr_ids[0] if matched_cdr_ids else None)
        if cdr_id is not None:
            self.capture(
                Operation(
                    "target_transcript",
                    "GET",
                    f"/cdrs/{cdr_id}/transcription",
                    "/cdrs/{cdrID}/transcription",
                    "list",
                ),
                selector=_bounded_list(100),
            )

        self._commit_pending_fixtures()
        return list(self.results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture bounded, sanitized BatchDialer BD1 evidence. All identifiers and the API key "
            "must come from environment variables; raw provider data is never written."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the fixed read-only capture plan. Without this flag, no request is sent.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.execute:
        print("BD1 capture is ready. No provider request was sent; add --execute to run it.")
        return 0
    try:
        config = CaptureConfig.from_environment()
        with CaptureSession(config) as session:
            results = session.run()
    except CaptureError as exc:
        print(f"BD1 capture stopped safely: {exc}")
        return 1
    for result in results:
        relative_path = result.fixture_path.relative_to(FIXTURE_ROOT)
        print(
            f"{result.operation_id}: HTTP {result.status_code} "
            f"sha256={result.sha256} fixture={relative_path.as_posix()}"
        )
    print("Evidence is pending human review; the manifest and BD1 status were not advanced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
