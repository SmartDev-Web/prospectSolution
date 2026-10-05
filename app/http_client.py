"""Shared HTTP helpers for open data APIs, with bounded retries on transient failures."""
import asyncio
import logging
from typing import Any

import httpx

from app.config import OPEN_DATA_USER_AGENT

logger = logging.getLogger(__name__)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0)


class OpenDataError(RuntimeError):
    """Raised when an open data API stays unavailable after every retry."""


def create_open_data_client(timeout_seconds: float = 30.0) -> httpx.AsyncClient:
    """Create an HTTP client identified with the open data user agent."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": OPEN_DATA_USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
        transport=httpx.AsyncHTTPTransport(retries=2),
    )


async def request_json_with_retries(client: httpx.AsyncClient, method: str, url: str, **request_options: Any) -> Any:
    """Send a request and decode its JSON body, retrying on network errors and rate limits."""
    last_error: Exception | None = None
    for attempt_index, backoff_seconds in enumerate((0.0, *RETRY_BACKOFF_SECONDS)):
        if backoff_seconds:
            # Exponential backoff is required by the APIs rate limiting policy after a refusal
            await asyncio.sleep(backoff_seconds)
        try:
            response = await client.request(method, url, **request_options)
        except httpx.TransportError as error:
            last_error = error
            logger.warning("Attempt %s on %s failed : %s", attempt_index + 1, url, error)
            continue
        if response.status_code in TRANSIENT_STATUS_CODES:
            last_error = OpenDataError(f"HTTP {response.status_code}")
            logger.warning("Attempt %s on %s returned HTTP %s", attempt_index + 1, url, response.status_code)
            continue
        response.raise_for_status()
        return response.json()
    raise OpenDataError(f"{url} unavailable : {last_error}")
