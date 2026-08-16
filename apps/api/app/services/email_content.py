from html.parser import HTMLParser
from urllib.parse import urlsplit

IGNORED_EMAIL_HTML_ELEMENTS = frozenset(
    {
        "head",
        "noscript",
        "script",
        "style",
        "template",
    }
)


class _VisibleEmailTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._ignored_depth = 0
        self._link_stack: list[tuple[str | None, int]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in IGNORED_EMAIL_HTML_ELEMENTS:
            self._ignored_depth += 1
            return
        if self._ignored_depth or normalized_tag != "a":
            return
        href = next(
            (
                safe_link
                for key, value in attrs
                if key.lower() == "href" and value and (safe_link := _safe_email_link(value))
            ),
            None,
        )
        self._link_stack.append((href, len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in IGNORED_EMAIL_HTML_ELEMENTS:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth or normalized_tag != "a" or not self._link_stack:
            return
        href, start_index = self._link_stack.pop()
        if not href:
            return
        label = " ".join(self.parts[start_index:]).strip()
        if not any(existing_href == href for _, existing_href in self.links):
            self.links.append((label, href))

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        normalized = data.strip()
        if normalized:
            self.parts.append(normalized)


def readable_email_body(
    *,
    text: str,
    html: str,
    empty_fallback: str = "",
) -> str:
    normalized_text = text.strip()
    if not html:
        return normalized_text or empty_fallback

    parser = _VisibleEmailTextExtractor()
    parser.feed(html)
    parser.close()
    body = "\n".join(parser.parts).strip() or normalized_text
    missing_links = [
        f"{label}: {href}" if label and label != href else href
        for label, href in parser.links
        if href not in body
    ]
    if missing_links:
        body = "\n".join(part for part in (body, *missing_links) if part).strip()
    return body or empty_fallback


def _safe_email_link(value: str) -> str | None:
    candidate = value.strip()
    if not candidate or len(candidate) > 8192 or "\\" in candidate:
        return None
    if any(character.isspace() or ord(character) < 32 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    return candidate
