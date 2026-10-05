"""Guards applied to every request sent to prospect websites: public web addresses only, bounded downloads."""
import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.config import BROWSER_USER_AGENT

# Pages larger than this are truncated: no small business homepage needs more to be audited
MAXIMUM_PAGE_BYTES = 5 * 1024 * 1024
BLOCKED_ADDRESS_MESSAGE = "adresse locale ou privée refusée"
# Verdicts are reused briefly: a host whose DNS answer changes is checked again a few minutes later
HOST_VERDICT_LIFETIME_SECONDS = 300.0
_host_verdicts: dict[str, tuple[bool, float]] = {}


def is_web_url(url: str | None) -> bool:
    """Tell whether a URL is an http or https address with a host name."""
    if not url:
        return False
    parsed_url = urlparse(url)
    return parsed_url.scheme in ("http", "https") and bool(parsed_url.hostname)


def is_public_address(address: str) -> bool:
    """Tell whether an IP address belongs to the public Internet."""
    try:
        parsed_address = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(parsed_address, ipaddress.IPv6Address) and parsed_address.ipv4_mapped:
        parsed_address = parsed_address.ipv4_mapped
    return parsed_address.is_global and not parsed_address.is_multicast


async def is_public_host(host_name: str) -> bool:
    """Tell whether every address of a host is public, so that a prospect website can never reach the user's network."""
    normalized_host = host_name.strip("[]").lower()
    cached_verdict = _host_verdicts.get(normalized_host)
    if cached_verdict and time.monotonic() - cached_verdict[1] < HOST_VERDICT_LIFETIME_SECONDS:
        return cached_verdict[0]
    try:
        address_records = await asyncio.get_running_loop().getaddrinfo(normalized_host, None, type=socket.SOCK_STREAM)
    except OSError:
        # An unresolvable host cannot be reached either: the request itself reports the failure
        return True
    verdict = bool(address_records) and all(is_public_address(address_record[4][0]) for address_record in address_records)
    _host_verdicts[normalized_host] = (verdict, time.monotonic())
    return verdict


async def is_public_web_url(url: str | None) -> bool:
    """Tell whether a URL is a web address whose host is on the public Internet."""
    return is_web_url(url) and await is_public_host(urlparse(url).hostname or "")


async def refuse_private_destinations(request: httpx.Request) -> None:
    """httpx hook run before every request, redirects included, refusing local and private destinations."""
    if not await is_public_web_url(str(request.url)):
        raise httpx.ConnectError(BLOCKED_ADDRESS_MESSAGE, request=request)


def create_public_web_client(timeout_seconds: float, verify_certificates: bool = True, extra_headers: dict[str, str] | None = None, retries: int = 2) -> httpx.AsyncClient:
    """Create the browser-like client used for prospect websites, restricted to public addresses."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=True,
        verify=verify_certificates,
        transport=httpx.AsyncHTTPTransport(retries=retries, verify=verify_certificates),
        headers={"User-Agent": BROWSER_USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6", **(extra_headers or {})},
        event_hooks={"request": [refuse_private_destinations]},
    )


@dataclass
class FetchedPage:
    """A response whose body was read up to the download limit."""
    url: str
    status_code: int
    content_type: str
    text: str
    redirect_urls: list[str] = field(default_factory=list)
    elapsed_milliseconds: int | None = None


async def fetch_page_text(client: httpx.AsyncClient, url: str) -> FetchedPage:
    """Download an HTML page, keeping at most MAXIMUM_PAGE_BYTES of its body; other content types are not downloaded."""
    async with client.stream("GET", url) as response:
        body_chunks: list[bytes] = []
        received_bytes = 0
        content_type = response.headers.get("content-type", "")
        response_is_html = not content_type or "html" in content_type
        if response_is_html:
            async for body_chunk in response.aiter_bytes():
                body_chunks.append(body_chunk)
                received_bytes += len(body_chunk)
                if received_bytes >= MAXIMUM_PAGE_BYTES:
                    break
        body = b"".join(body_chunks)[:MAXIMUM_PAGE_BYTES]
    return FetchedPage(
        url=str(response.url),
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        text=body.decode(response.encoding or "utf-8", errors="replace"),
        redirect_urls=[str(history_response.url) for history_response in response.history],
        elapsed_milliseconds=int(response.elapsed.total_seconds() * 1000) if response.is_closed else None,
    )
