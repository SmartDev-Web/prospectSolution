"""Raw HTTP and TLS checks performed before rendering a website."""
import asyncio
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.config import BROWSER_USER_AGENT

REQUEST_TIMEOUT_SECONDS = 20.0
CONNECTION_RETRIES = 2


@dataclass
class HttpProbeResult:
    """Outcome of fetching the homepage over HTTP."""
    requested_url: str
    final_url: str | None = None
    status_code: int | None = None
    html: str = ""
    redirect_chain: list[str] = field(default_factory=list)
    elapsed_milliseconds: int | None = None
    error: str | None = None
    certificate_error: str | None = None
    http_redirects_to_https: bool | None = None

    @property
    def reachable(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400


@dataclass
class CertificateInfo:
    """Validity of the TLS certificate served by a host."""
    valid: bool
    days_remaining: int | None = None
    error: str | None = None


def build_http_client(verify_certificates: bool) -> httpx.AsyncClient:
    """Create the client used to probe websites like a regular browser."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        follow_redirects=True,
        verify=verify_certificates,
        transport=httpx.AsyncHTTPTransport(retries=CONNECTION_RETRIES, verify=verify_certificates),
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        },
    )


async def fetch_homepage(url: str) -> HttpProbeResult:
    """Fetch a homepage, retrying without certificate validation to tell TLS errors from outages."""
    probe_result = HttpProbeResult(requested_url=url)
    for verify_certificates in (True, False):
        try:
            async with build_http_client(verify_certificates) as client:
                response = await client.get(url)
        except httpx.ConnectError as error:
            certificate_failure = isinstance(error.__cause__, ssl.SSLError) or "CERTIFICATE" in str(error).upper()
            if verify_certificates and certificate_failure:
                probe_result.certificate_error = str(error)
                continue
            probe_result.error = f"connexion impossible ({error or type(error).__name__})"
            return probe_result
        except httpx.TimeoutException:
            probe_result.error = "délai de réponse dépassé"
            return probe_result
        except httpx.HTTPError as error:
            probe_result.error = f"erreur HTTP ({type(error).__name__})"
            return probe_result
        probe_result.final_url = str(response.url)
        probe_result.status_code = response.status_code
        probe_result.html = response.text if "html" in response.headers.get("content-type", "html") else ""
        probe_result.redirect_chain = [str(history_response.url) for history_response in response.history]
        probe_result.elapsed_milliseconds = int(response.elapsed.total_seconds() * 1000)
        if response.status_code >= 400:
            probe_result.error = f"code HTTP {response.status_code}"
        return probe_result
    probe_result.error = probe_result.error or "connexion impossible"
    return probe_result


async def check_http_redirect(host_name: str) -> bool | None:
    """Tell whether the plain HTTP version of a host redirects to HTTPS."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True, headers={"User-Agent": BROWSER_USER_AGENT}, transport=httpx.AsyncHTTPTransport(retries=CONNECTION_RETRIES)) as client:
            response = await client.get(f"http://{host_name}/")
    except httpx.HTTPError:
        return None
    return str(response.url).startswith("https://")


def read_certificate_blocking(host_name: str, port: int = 443) -> CertificateInfo:
    """Open a TLS connection and read the expiry date of the presented certificate."""
    verifying_context = ssl.create_default_context()
    try:
        with socket.create_connection((host_name, port), timeout=10) as raw_socket:
            with verifying_context.wrap_socket(raw_socket, server_hostname=host_name) as tls_socket:
                peer_certificate = tls_socket.getpeercert()
    except ssl.SSLCertVerificationError as error:
        return CertificateInfo(valid=False, error=error.verify_message or str(error))
    except (OSError, ssl.SSLError) as error:
        return CertificateInfo(valid=False, error=str(error))
    expiry_date = datetime.fromtimestamp(ssl.cert_time_to_seconds(peer_certificate["notAfter"]), tz=timezone.utc)
    return CertificateInfo(valid=True, days_remaining=(expiry_date - datetime.now(timezone.utc)).days)


async def inspect_certificate(url: str) -> CertificateInfo | None:
    """Inspect the TLS certificate of an HTTPS URL without blocking the event loop."""
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        return None
    return await asyncio.to_thread(read_certificate_blocking, parsed_url.hostname, parsed_url.port or 443)
