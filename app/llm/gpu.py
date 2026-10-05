"""Discovery of the NVIDIA graphics cards available for local inference."""
import asyncio
import shutil
from dataclasses import asdict, dataclass

NVIDIA_QUERY_FIELDS = "index,uuid,name,memory.total,memory.used,utilization.gpu,compute_cap"


@dataclass
class GraphicsCard:
    """One NVIDIA GPU as reported by nvidia-smi."""
    index: int
    uuid: str
    name: str
    memory_total_megabytes: int
    memory_used_megabytes: int
    utilization_percent: int
    compute_capability: str


async def list_graphics_cards() -> list[dict]:
    """Return every NVIDIA GPU, or an empty list when nvidia-smi is unavailable."""
    nvidia_smi_executable = shutil.which("nvidia-smi")
    if nvidia_smi_executable is None:
        return []
    process = await asyncio.create_subprocess_exec(
        nvidia_smi_executable, f"--query-gpu={NVIDIA_QUERY_FIELDS}", "--format=csv,noheader,nounits",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    standard_output, _standard_error = await process.communicate()
    if process.returncode != 0:
        return []
    graphics_cards = []
    for output_line in standard_output.decode(errors="replace").splitlines():
        columns = [column.strip() for column in output_line.split(",")]
        if len(columns) < 7:
            continue
        graphics_cards.append(GraphicsCard(
            index=int(columns[0]),
            uuid=columns[1],
            name=columns[2],
            memory_total_megabytes=int(float(columns[3])),
            memory_used_megabytes=int(float(columns[4])),
            utilization_percent=int(float(columns[5])) if columns[5].replace(".", "").isdigit() else 0,
            compute_capability=columns[6],
        ))
    return [asdict(graphics_card) for graphics_card in graphics_cards]
