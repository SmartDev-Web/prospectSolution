"""Background job orchestration with live progress reporting."""
import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.database import utc_now_iso
from app.events import event_bus

logger = logging.getLogger(__name__)
MAX_JOB_LOG_LINES = 200


@dataclass
class Job:
    """State of one background job exposed to the interface."""
    identifier: int
    kind: str
    label: str
    status: str = "running"
    progress_current: int = 0
    progress_total: int = 0
    message: str = ""
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    task: asyncio.Task | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the job for the API and the event bus."""
        return {
            "id": self.identifier,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "log_lines": self.log_lines[-20:],
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class JobContext:
    """Handle given to a running job so it can report its progress."""

    def __init__(self, job: Job) -> None:
        self._job = job

    @property
    def job_identifier(self) -> int:
        return self._job.identifier

    def set_progress(self, current: int, total: int | None = None, message: str | None = None) -> None:
        """Update the progress counters and notify the interface."""
        self._job.progress_current = current
        if total is not None:
            self._job.progress_total = total
        if message is not None:
            self._job.message = message
        publish_job_update(self._job)

    def advance(self, message: str | None = None) -> None:
        """Increment the progress counter by one step."""
        self.set_progress(self._job.progress_current + 1, message=message)

    def log(self, line: str) -> None:
        """Append a human readable line to the job log."""
        logger.info("[job %s] %s", self._job.identifier, line)
        self._job.log_lines.append(line)
        del self._job.log_lines[:-MAX_JOB_LOG_LINES]
        self._job.message = line
        publish_job_update(self._job)

    def set_result(self, **result_values: Any) -> None:
        """Store summary values displayed once the job ends."""
        self._job.result.update(result_values)


def publish_job_update(job: Job) -> None:
    """Broadcast the current state of a job."""
    event_bus.publish("job.updated", job.to_dict())


class JobManager:
    """Start, track and cancel background jobs."""

    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._identifier_sequence = itertools.count(1)

    def start(self, kind: str, label: str, job_function: Callable[[JobContext], Awaitable[None]]) -> Job:
        """Launch a coroutine as a tracked background job."""
        job = Job(identifier=next(self._identifier_sequence), kind=kind, label=label)
        self._jobs[job.identifier] = job
        job.task = asyncio.create_task(self._run(job, job_function))
        publish_job_update(job)
        return job

    async def _run(self, job: Job, job_function: Callable[[JobContext], Awaitable[None]]) -> None:
        try:
            await job_function(JobContext(job))
            job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.message = "Tâche annulée"
        except Exception as error:
            logger.exception("Job %s failed", job.identifier)
            job.status = "failed"
            job.error = f"{type(error).__name__} : {error}"
        job.finished_at = utc_now_iso()
        publish_job_update(job)

    def cancel(self, job_identifier: int) -> bool:
        """Request cancellation of a running job."""
        job = self._jobs.get(job_identifier)
        if job is None or job.task is None or job.task.done():
            return False
        job.task.cancel()
        return True

    def remove(self, job_identifier: int) -> bool:
        """Forget a finished job so that it leaves the interface."""
        job = self._jobs.get(job_identifier)
        if job is None or job.status == "running":
            return False
        del self._jobs[job_identifier]
        event_bus.publish("job.removed", {"id": job_identifier})
        return True

    def clear_finished(self) -> int:
        """Forget every finished, failed or cancelled job."""
        finished_identifiers = [job.identifier for job in self._jobs.values() if job.status != "running"]
        for job_identifier in finished_identifiers:
            self.remove(job_identifier)
        return len(finished_identifiers)

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return every known job, most recent first."""
        return [job.to_dict() for job in sorted(self._jobs.values(), key=lambda job: job.identifier, reverse=True)]

    def has_running_job(self, kind: str) -> bool:
        """Tell whether a job of the given kind is still running."""
        return any(job.kind == kind and job.status == "running" for job in self._jobs.values())

    async def shutdown(self) -> None:
        """Cancel every running job and wait for them to stop."""
        running_tasks = [job.task for job in self._jobs.values() if job.task and not job.task.done()]
        for running_task in running_tasks:
            running_task.cancel()
        await asyncio.gather(*running_tasks, return_exceptions=True)


job_manager = JobManager()
