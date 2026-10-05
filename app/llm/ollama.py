"""Local language model served by Ollama, optionally pinned to a dedicated GPU."""
import asyncio
import json
import logging
import os
import re
import shutil
import sys
from typing import Any, Callable

import httpx

from app.events import event_bus
from app.settings_service import load_settings

logger = logging.getLogger(__name__)
SERVER_READY_TIMEOUT_SECONDS = 60
GENERATION_TIMEOUT_SECONDS = 240
WINDOWS_CREATE_NO_WINDOW = 0x08000000
LISTENING_LOG_MARKER = "Listening on"
INFERENCE_DEVICE_PATTERN = re.compile(r'msg="inference compute".*?name="?([^"]+?)"?\s+total="?([^"\s]+(?:\s\w+)?)"?')


class OllamaService:
    """Start, stop and query an Ollama server."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._log_reader_task: asyncio.Task | None = None
        self._ready_event = asyncio.Event()
        self._status = "stopped"
        self._last_error: str | None = None
        self._inference_device: str | None = None
        self._recent_log_lines: list[str] = []

    def base_url(self) -> str:
        """Return the URL of the Ollama server selected in the settings."""
        settings = load_settings()
        if settings["llm_mode"] == "managed":
            return f"http://127.0.0.1:{settings['llm_managed_port']}"
        return settings["llm_external_url"].rstrip("/")

    def _publish_status(self) -> None:
        event_bus.publish("llm.status", self.status_snapshot())

    def status_snapshot(self) -> dict[str, Any]:
        """Return the current server state for the interface."""
        settings = load_settings()
        return {
            "mode": settings["llm_mode"],
            "status": self._status if settings["llm_mode"] == "managed" else ("external" if settings["llm_mode"] == "external" else "disabled"),
            "base_url": self.base_url(),
            "model": settings["llm_model"],
            "gpu_uuid": settings["llm_gpu_uuid"],
            "inference_device": self._inference_device,
            "last_error": self._last_error,
            "recent_log_lines": self._recent_log_lines[-15:],
        }

    async def start_managed_server(self) -> dict[str, Any]:
        """Launch 'ollama serve' restricted to the selected GPU and wait until it listens."""
        if self._process is not None and self._process.returncode is None:
            return self.status_snapshot()
        settings = load_settings()
        ollama_executable = shutil.which(settings["ollama_executable"]) or settings["ollama_executable"]
        environment_variables = dict(os.environ)
        environment_variables["OLLAMA_HOST"] = f"127.0.0.1:{settings['llm_managed_port']}"
        if settings["llm_gpu_uuid"]:
            # Ollama only sees the selected card, leaving the other GPU entirely to the desktop
            environment_variables["CUDA_VISIBLE_DEVICES"] = settings["llm_gpu_uuid"]
            environment_variables["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        self._ready_event = asyncio.Event()
        self._status = "starting"
        self._last_error = None
        self._inference_device = None
        self._recent_log_lines = []
        self._publish_status()
        try:
            self._process = await asyncio.create_subprocess_exec(
                ollama_executable, "serve",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=environment_variables,
                creationflags=WINDOWS_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except FileNotFoundError:
            self._status = "error"
            self._last_error = "Ollama introuvable : installez-le depuis https://ollama.com puis relancez."
            self._publish_status()
            return self.status_snapshot()
        self._log_reader_task = asyncio.create_task(self._read_server_logs(self._process))
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=SERVER_READY_TIMEOUT_SECONDS)
            self._status = "running"
        except asyncio.TimeoutError:
            self._status = "error"
            self._last_error = self._last_error or "Ollama n'a pas démarré dans les temps (voir les logs)."
        self._publish_status()
        return self.status_snapshot()

    async def _read_server_logs(self, process: asyncio.subprocess.Process) -> None:
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break
            log_line = raw_line.decode(errors="replace").rstrip()
            self._recent_log_lines.append(log_line)
            del self._recent_log_lines[:-200]
            if LISTENING_LOG_MARKER in log_line:
                self._ready_event.set()
            if "address already in use" in log_line.lower() or "only one usage of each socket address" in log_line.lower():
                self._last_error = "Le port est déjà utilisé : un autre serveur Ollama tourne peut-être déjà sur ce port."
            device_match = INFERENCE_DEVICE_PATTERN.search(log_line)
            if device_match:
                self._inference_device = f"{device_match.group(1)} ({device_match.group(2)})"
                self._publish_status()
        await process.wait()
        if self._status in ("running", "starting"):
            self._status = "error" if process.returncode else "stopped"
            self._last_error = self._last_error or (f"Ollama s'est arrêté (code {process.returncode})" if process.returncode else None)
            self._publish_status()

    async def stop_managed_server(self) -> dict[str, Any]:
        """Stop the managed server if it runs."""
        if self._process is not None and self._process.returncode is None:
            self._status = "stopped"
            self._process.terminate()
            await self._process.wait()
        self._process = None
        self._status = "stopped"
        self._publish_status()
        return self.status_snapshot()

    async def list_installed_models(self) -> list[str]:
        """Return the names of the models already downloaded."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url()}/api/tags")
            response.raise_for_status()
        return [model["name"] for model in response.json().get("models", [])]

    async def pull_model(self, model_name: str, report_progress: Callable[[int, int, str], None]) -> None:
        """Download a model, streaming the progress."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url()}/api/pull", json={"model": model_name, "stream": True}) as response:
                response.raise_for_status()
                async for response_line in response.aiter_lines():
                    if not response_line:
                        continue
                    progress_update = json.loads(response_line)
                    if progress_update.get("error"):
                        raise RuntimeError(progress_update["error"])
                    report_progress(int(progress_update.get("completed") or 0), int(progress_update.get("total") or 0), progress_update.get("status", ""))

    async def is_available(self) -> bool:
        """Tell whether the configured server answers."""
        if load_settings()["llm_mode"] == "disabled":
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url()}/api/version")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Ask the model for a JSON answer."""
        settings = load_settings()
        request_body = {
            "model": settings["llm_model"],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.4, "num_ctx": 4096},
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(GENERATION_TIMEOUT_SECONDS, connect=10.0)) as client:
            response = await client.post(f"{self.base_url()}/api/chat", json=request_body)
            response.raise_for_status()
        return json.loads(response.json()["message"]["content"])


ollama_service = OllamaService()
