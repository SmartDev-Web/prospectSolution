"""Shared HTTP helpers for open data APIs, with bounded retries on transient failures."""
import asyncio
import logging
import random
import time
from typing import Any

import httpx

from app.config import OPEN_DATA_USER_AGENT

logger = logging.getLogger(__name__)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_BACKOFF_SECONDS = (2.0, 4.0, 8.0, 16.0, 30.0)
MAXIMUM_RETRY_AFTER_SECONDS = 60.0


class RequestPacer:
    """Space out the requests sent to one service, so that it never rate limits or bans the user's IP address."""

    def __init__(self, minimum_interval_seconds: float, jitter_seconds: float = 0.0) -> None:
        self._minimum_interval_seconds = minimum_interval_seconds
        self._jitter_seconds = jitter_seconds
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def wait_turn(self) -> None:
        """Wait until the service's rate limit allows the next request."""
        async with self._lock:
            remaining_seconds = self._minimum_interval_seconds + random.uniform(0, self._jitter_seconds) - (time.monotonic() - self._last_request_time)
            if remaining_seconds > 0:
                # Spacing requests is the only way to respect a rate limit that the service does not announce
                await asyncio.sleep(remaining_seconds)
            self._last_request_time = time.monotonic()


def read_retry_after_seconds(response: httpx.Response) -> float | None:
    """Return the delay requested by a Retry-After header, when present."""
    retry_after_value = response.headers.get("retry-after", "")
    return min(float(retry_after_value), MAXIMUM_RETRY_AFTER_SECONDS) if retry_after_value.replace(".", "", 1).isdigit() else None


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


async def request_json_with_retries(client: httpx.AsyncClient, method: str, url: str, pacer: RequestPacer | None = None, **request_options: Any) -> Any:
    """Send a request and decode its JSON body, retrying on network errors and rate limits."""
    last_error: Exception | None = None
    requested_delay_seconds: float | None = None
    for attempt_index, backoff_seconds in enumerate((0.0, *RETRY_BACKOFF_SECONDS)):
        if backoff_seconds:
            # Backing off after a refusal is required by the APIs rate limiting policy
            await asyncio.sleep(requested_delay_seconds or backoff_seconds)
        if pacer:
            await pacer.wait_turn()
        try:
            response = await client.request(method, url, **request_options)
        except httpx.TransportError as error:
            last_error = error
            logger.warning("Attempt %s on %s failed : %s", attempt_index + 1, url, error)
            continue
        if response.status_code in TRANSIENT_STATUS_CODES:
            requested_delay_seconds = read_retry_after_seconds(response)
            last_error = OpenDataError(f"HTTP {response.status_code}")
            logger.warning("Attempt %s on %s returned HTTP %s", attempt_index + 1, url, response.status_code)
            continue
        response.raise_for_status()
        return response.json()
    raise OpenDataError(f"{url} unavailable : {last_error}")
