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
import os
import re
import socket
from dataclasses import dataclass
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


def _validate_url(url: str):
    parsed = urlparse(url.strip())
    if parsed.scheme not in SCHEMES or not parsed.hostname:
        raise JobUrlError("Only http:// and https:// job URLs are supported.")
    if _is_private_host(parsed.hostname):
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
    """Collect the metadata and visible text of a job page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.og_title = ""
        self.og_site_name = ""
        self.og_description = ""
        self.meta_description = ""
        self._skip_depth = 0
        self._in_title = False
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        attributes = dict(attrs)
        if tag == "meta":
            _capture_meta(self, attributes)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
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
    )


def _extract_description(page: _Page) -> str:
    if _usable(page.description):
        return page.description
    lines = [line for line in (page.text or []) if len(line) > 1]
    lines = _merge_body_lines(lines)
    return "\n".join(lines).strip()


def _usable(text: str) -> bool:
    return len(text.strip()) >= MIN_DESCRIPTION_CHARS


def _merge_body_lines(lines: list[str]) -> list[str]:
    """Cap and clean body text so a noisy layout never produces a huge blob."""
    merged = []
    for line in lines[:200]:
        if line not in merged:
            merged.append(line)
    return merged[:120]