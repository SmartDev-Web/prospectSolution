"""Discovery of the graphics cards usable for local inference, and diagnosis of the ones the NVIDIA driver ignores."""
import asyncio
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass

NVIDIA_QUERY_FIELDS = ("index", "uuid", "name", "memory.total", "memory.used", "utilization.gpu", "compute_cap")
NVIDIA_LIST_PATTERN = re.compile(r"GPU (\d+): (.+?) \(UUID: (GPU-[0-9a-fA-F-]+)\)")
WINDOWS_ADAPTER_COMMAND = (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name, PNPDeviceID, Status, ConfigManagerErrorCode | ConvertTo-Json -Compress"
)
# Device Manager error codes most often met on secondary or former mining cards
WINDOWS_DEVICE_PROBLEMS = {
    10: "le périphérique ne peut pas démarrer (code 10) : pilote à réinstaller ou alimentation PCIe insuffisante",
    12: "ressources insuffisantes (code 12) : activer « Above 4G decoding » dans le BIOS",
    22: "carte désactivée dans le Gestionnaire de périphériques (code 22) : clic droit puis « Activer »",
    28: "pilote non installé pour cette carte (code 28)",
    31: "pilote incorrect (code 31) : réinstaller le pilote NVIDIA",
    43: "Windows a arrêté la carte (code 43) : pilote à réinstaller proprement (DDU), riser ou alimentation à vérifier",
}


@dataclass
class GraphicsCard:
    """One NVIDIA GPU usable by CUDA, as reported by nvidia-smi."""
    index: int
    uuid: str
    name: str
    memory_total_megabytes: int | None
    memory_used_megabytes: int | None
    utilization_percent: int | None
    compute_capability: str | None


def parse_number(raw_value: str) -> int | None:
    """Convert an nvidia-smi value, which may be [N/A] or [Not Supported] on older cards."""
    try:
        return int(float(raw_value))
    except ValueError:
        return None


async def run_command(*arguments: str) -> str | None:
    """Run a command and return its output, or None when it is missing or fails."""
    if shutil.which(arguments[0]) is None:
        return None
    process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    standard_output, _standard_error = await process.communicate()
    return standard_output.decode(errors="replace") if process.returncode == 0 else None


async def query_nvidia_cards() -> list[GraphicsCard]:
    """List the cards seen by the NVIDIA driver, tolerating old drivers and partial values."""
    for query_fields in (NVIDIA_QUERY_FIELDS, NVIDIA_QUERY_FIELDS[:-1]):
        query_output = await run_command("nvidia-smi", f"--query-gpu={','.join(query_fields)}", "--format=csv,noheader,nounits")
        if query_output is None:
            continue
        graphics_cards = []
        for output_line in query_output.splitlines():
            columns = [column.strip() for column in output_line.split(",")]
            if len(columns) < len(query_fields) or not columns[0].isdigit():
                continue
            graphics_cards.append(GraphicsCard(
                index=int(columns[0]),
                uuid=columns[1],
                name=columns[2],
                memory_total_megabytes=parse_number(columns[3]),
                memory_used_megabytes=parse_number(columns[4]),
                utilization_percent=parse_number(columns[5]),
                compute_capability=columns[6] if len(query_fields) > 6 else None,
            ))
        if graphics_cards:
            return graphics_cards
    list_output = await run_command("nvidia-smi", "-L") or ""
    return [
        GraphicsCard(index=int(index), uuid=uuid, name=name, memory_total_megabytes=None, memory_used_megabytes=None, utilization_percent=None, compute_capability=None)
        for index, name, uuid in NVIDIA_LIST_PATTERN.findall(list_output)
    ]


async def list_system_nvidia_adapters() -> list[dict]:
    """List the NVIDIA adapters known to the operating system, whatever the state of their driver."""
    if sys.platform == "win32":
        adapters_output = await run_command("powershell", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_ADAPTER_COMMAND)
        if not adapters_output:
            return []
        decoded_adapters = json.loads(adapters_output)
        adapters = decoded_adapters if isinstance(decoded_adapters, list) else [decoded_adapters]
        return [
            {"name": adapter.get("Name") or "", "error_code": adapter.get("ConfigManagerErrorCode") or 0}
            for adapter in adapters
            if "nvidia" in (adapter.get("Name") or "").lower() or "VEN_10DE" in (adapter.get("PNPDeviceID") or "").upper()
        ]
    lspci_output = await run_command("lspci") or ""
    return [{"name": line.split(": ", 1)[-1], "error_code": 0} for line in lspci_output.splitlines() if "NVIDIA" in line and ("VGA" in line or "3D" in line)]


def find_ignored_adapters(usable_cards: list[GraphicsCard], system_adapters: list[dict]) -> list[dict]:
    """Return the NVIDIA adapters present in the machine but unusable for computing, with the reason."""
    remaining_usable_names = [card.name.lower() for card in usable_cards]
    ignored_adapters = []
    for adapter in system_adapters:
        adapter_name = adapter["name"].lower()
        matching_name = next((usable_name for usable_name in remaining_usable_names if usable_name in adapter_name or adapter_name in usable_name), None)
        if matching_name and not adapter["error_code"]:
            remaining_usable_names.remove(matching_name)
            continue
        problem = WINDOWS_DEVICE_PROBLEMS.get(adapter["error_code"]) or (
            f"erreur du Gestionnaire de périphériques (code {adapter['error_code']})" if adapter["error_code"]
            else "présente dans la machine mais ignorée par le pilote NVIDIA : réinstaller le pilote ou vérifier qu'elle est bien alimentée"
        )
        ignored_adapters.append({"name": adapter["name"], "problem": problem})
    return ignored_adapters


async def describe_graphics_cards() -> dict:
    """Return the usable NVIDIA cards and the ones the driver ignores."""
    usable_cards, system_adapters = await asyncio.gather(query_nvidia_cards(), list_system_nvidia_adapters())
    return {
        "graphics_cards": [asdict(graphics_card) for graphics_card in usable_cards],
        "ignored_graphics_cards": find_ignored_adapters(usable_cards, system_adapters),
    }
