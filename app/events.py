"""In-process publish/subscribe bus pushing live events to the web interface."""
import asyncio
from typing import Any


class EventBus:
    """Fan out events to every connected subscriber queue."""

    def __init__(self) -> None:
        self._subscriber_queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        """Register a new subscriber and return its dedicated queue."""
        subscriber_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscriber_queues.add(subscriber_queue)
        return subscriber_queue

    def unsubscribe(self, subscriber_queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        self._subscriber_queues.discard(subscriber_queue)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Deliver an event to every subscriber without blocking the publisher."""
        event = {"type": event_type, "payload": payload}
        for subscriber_queue in list(self._subscriber_queues):
            if subscriber_queue.full():
                # A stalled client drops its oldest event rather than blocking the whole application
                subscriber_queue.get_nowait()
            subscriber_queue.put_nowait(event)


event_bus = EventBus()
