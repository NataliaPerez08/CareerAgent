"""Job ingestion: load a job posting from a plain URL.

Purpose: let the user fetch a vacancy from a job-board URL instead of
pasting the description manually. Rules (from the sprint):

- respect a timeout;
- send a reasonable user-agent;
- never attempt anti-bot bypass or aggressive scraping;
- fail gracefully (errors are explicit, the UI keeps manual paste);
- never resolve to private/internal hosts (SSRF guard).

The extraction is best-effort and dependency-light (stdlib HTMLParser):
title, company and description come from common page metadata
(``<title>``, Open Graph, ``meta[name=description]``) and degrade to the
page's visible text. No JS execution, no fragile selectors. Nothing here
calls the LLM.
"""

import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

try:
    import httpx
except ImportError:  # pragma: no cover - import safety for minimal runtimes
    httpx = None  # type: ignore[assignment]


class JobFetchError(ValueError):
    """Base class for all job ingestion failures."""


class JobUrlError(JobFetchError):
    """The URL is invalid, has a disallowed scheme, or is not public."""


class JobFetchTimeoutError(JobFetchError):
    """The remote host did not answer within the timeout."""


class JobFetchStatusError(JobFetchError):
    """The remote host answered with a non-success status."""


class JobEmptyError(JobFetchError):
    """No usable job description could be extracted from the page."""


@dataclass(frozen=True)
class JobPosting:
    """Structured content extracted from a job posting URL."""

    title: str
    company: str
    description: str
    source_url: str


MAX_RESPONSE_BYTES = int(os.getenv("JOB_FETCH_MAX_BYTES", "2000000"))
TIMEOUT_SECONDS = float(os.getenv("JOB_FETCH_TIMEOUT_SECONDS", "10"))
MIN_DESCRIPTION_CHARS = int(os.getenv("JOB_MIN_DESCRIPTION_CHARS", "20"))
ALLOW_PRIVATE_HOSTS = os.getenv("JOB_FETCH_ALLOW_PRIVATE_HOSTS", "").lower() in {"1", "true", "yes"}
USER_AGENT = "CareerAgent/1.0 (hackathon demo; polite fetching)"
SCHEMES = ("http", "https")


def fetch_job(url, *, transport=None) -> JobPosting:
    """Fetch a job posting from ``url`` and return its structured content.

    ``transport`` is injected in tests (``httpx.MockTransport``); when
    omitted, a short-lived client with a bounded timeout is used.
    """
    if httpx is None:  # pragma: no cover - import safety guard
        raise JobFetchError("Job ingestion is unavailable in this runtime.")

    parsed = _validate_url(url)

    client = httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain,application/xhtml+xml,*/*;q=0.8",
        },
        transport=transport,
    )
    try:
        try:
            response = client.get(parsed.geturl())
        except httpx.TimeoutException as exc:
            raise JobFetchTimeoutError(
                f"Job URL did not respond within {TIMEOUT_SECONDS:g}s."
            ) from exc
        except httpx.RequestError as exc:
            raise JobFetchError(f"Could not reach the job URL: {exc}") from exc
        finally:
            client.close()
    except JobFetchError:
        raise
    except httpx.HTTPError as exc:
        raise JobFetchError(f"Could not reach the job URL: {exc}") from exc

    if response.status_code >= 400:
        raise JobFetchStatusError(
            f"Job URL answered HTTP {response.status_code} — nothing to load."
        )
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise JobFetchError("Job URL page is too large to ingest.")

    content_type = response.headers.get("content-type", "")
    text = response.text
    if "html" in content_type:
        parsed_page = _parse_html(text)
    else:
        parsed_page = _Page(company=_site_name_from_host(parsed.hostname), text=[text])

    description = _extract_description(parsed_page)
    if len(description) < MIN_DESCRIPTION_CHARS:
        raise JobEmptyError(
            "Could not extract a job description from that URL. "
            "The page may block automated reads or be mostly empty — paste it manually."
        )

    return JobPosting(
        title=parsed_page.title,
        company=parsed_page.company,
        description=description,
        source_url=parsed.geturl(),
    )


@dataclass
class _Page:
    title: str = ""
    company: str = ""
    description: str = ""
    text: list[str] | None = None
    json_blocks: list[str] | None = None


def _validate_url(url: str):
    parsed = urlparse(url.strip())
    if parsed.scheme not in SCHEMES or not parsed.hostname:
        raise JobUrlError("Only http:// and https:// job URLs are supported.")
    if not ALLOW_PRIVATE_HOSTS and _is_private_host(parsed.hostname):
        raise JobUrlError("Job URLs pointing to private, loopback or internal hosts are rejected.")
    return parsed


def _is_private_host(hostname: str) -> bool:
    """Reject literal private/link-local addresses and obvious local hosts.

    Hostnames are only rejected when DNS resolves them *entirely* to
    non-public addresses (basic SSRF guard). A hostname that cannot be
    resolved is allowed here — it is unreachable anyway and the fetch
    fails with a network error.
    """
    if hostname in {"localhost", "::1"}:
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        return _is_non_public(address)
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    return all(_is_non_public(ipaddress.ip_address(info[4][0])) for info in infos)


def _is_non_public(address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _site_name_from_host(hostname: str) -> str:
    labels = hostname.split(".")
    if len(labels) >= 2:
        return labels[-2].capitalize()
    return hostname.capitalize()


class _JobPageParser(HTMLParser):
    """Collect the metadata, embedded JSON and visible text of a job page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.og_title = ""
        self.og_site_name = ""
        self.og_description = ""
        self.meta_description = ""
        self.json_blocks: list[str] = []
        self._json_buffer: list[str] | None = None
        self._skip_depth = 0
        self._in_title = False
        self._text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip_depth += 1
            if tag == "script" and (attributes.get("type") or "").lower() in _JSON_SCRIPT_TYPES:
                self._json_buffer = []
        elif tag == "title":
            self._in_title = True
        if tag == "meta":
            _capture_meta(self, attributes)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip_depth:
            self._skip_depth -= 1
            if tag == "script" and self._json_buffer is not None:
                block = "".join(self._json_buffer).strip()
                if block:
                    self.json_blocks.append(block)
                self._json_buffer = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._json_buffer is not None:
            self._json_buffer.append(data)
            return
        if self._skip_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self._in_title:
            self.title += (" " if self.title else "") + cleaned
            return
        self._text.append(cleaned)


def _capture_meta(parser: _JobPageParser, attributes: dict) -> None:
    name = (attributes.get("name") or attributes.get("property") or "").lower()
    content = (attributes.get("content") or "").strip()
    if not content:
        return
    if name == "twitter:title" or name == "og:title":
        parser.og_title = content
    elif name == "og:site_name":
        parser.og_site_name = content
    elif name == "og:description":
        parser.og_description = content
    elif name == "description":
        parser.meta_description = content


_JSON_SCRIPT_TYPES = frozenset(
    {"application/ld+json", "application/json", "text/template", "text/x-template"}
)
_DESCRIPTION_KEYS = frozenset({"description", "content", "jobdescription", "job_description"})
_COMPANY_KEYS = ("hiringOrganization", "company", "organization", "employer")
_MAX_JSON_BLOCKS = 25
_MAX_JSON_WALK = 500


def _parse_html(html: str) -> _Page:
    parser = _JobPageParser()
    try:
        parser.feed(html)
    except (ValueError, UnicodeError):
        raise JobEmptyError(
            "Could not parse that job page as HTML — paste the description manually."
        ) from None
    title = parser.og_title or parser.title
    return _Page(
        title=title.strip(),
        company=parser.og_site_name.strip(),
        description=parser.og_description or parser.meta_description,
        text=parser._text,
        json_blocks=parser.json_blocks,
    )


def _extract_description(page: _Page) -> str:
    """Resolution order: page metadata → embedded job JSON → visible body text."""
    if _usable(page.description):
        return page.description
    json_title, json_company, description = _extract_from_json_blocks(page.json_blocks or [])
    if description:
        # JSON only fills fields the metadata could not provide.
        if not page.title and json_title:
            page.title = json_title
        if not page.company and json_company:
            page.company = json_company
        return description
    lines = [line for line in (page.text or []) if len(line) > 1]
    lines = _merge_body_lines(lines)
    return "\n".join(lines).strip()


def _extract_from_json_blocks(blocks: list[str]) -> tuple[str, str, str]:
    """Find (title, company, description) inside embedded JSON script blocks.

    SPA job boards (Phenom, Greenhouse, Workday…) publish the posting as a
    JSON blob in a data script tag; reading it is deterministic and not an
    anti-bot bypass — it is data the page itself ships to every visitor.
    """
    for block in blocks[:_MAX_JSON_BLOCKS]:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        found = _find_job_node(data, budget=[_MAX_JSON_WALK])
        if found is not None:
            return found
    return "", "", ""


def _find_job_node(node, budget: list[int]) -> tuple[str, str, str] | None:
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    if isinstance(node, dict):
        hit = _job_fields(node)
        if hit is not None:
            return hit
        for value in node.values():
            hit = _find_job_node(value, budget)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for item in node[:50]:
            hit = _find_job_node(item, budget)
            if hit is not None:
                return hit
    return None


def _job_fields(obj: dict) -> tuple[str, str, str] | None:
    """A node qualifies when it pairs a title with a usable description.

    Requiring the title prevents matching generic page blobs (e.g. an
    Organization JSON-LD with only a marketing description).
    """
    title = obj.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    for key, value in obj.items():
        if isinstance(value, str) and key.lower() in _DESCRIPTION_KEYS:
            description = _html_to_text(value)
            if _usable(description):
                return title.strip(), _company_of(obj).strip(), description
    return None


def _company_of(obj: dict) -> str:
    for key in _COMPANY_KEYS:
        value = obj.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            return value["name"]
    return ""


def _html_to_text(fragment: str) -> str:
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|ul|ol)\s*>", "\n", fragment)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _usable(text: str) -> bool:
    return len(text.strip()) >= MIN_DESCRIPTION_CHARS


def _merge_body_lines(lines: list[str]) -> list[str]:
    """Cap and clean body text so a noisy layout never produces a huge blob."""
    merged = []
    for line in lines[:200]:
        if line not in merged:
            merged.append(line)
    return merged[:120]