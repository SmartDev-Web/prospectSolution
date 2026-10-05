import asyncio
import json

from app.llm import gpu


def install_fake_commands(monkeypatch, nvidia_query_output, windows_adapters):
    async def fake_run_command(*arguments):
        if arguments[0] == "nvidia-smi" and arguments[1].startswith("--query-gpu"):
            return nvidia_query_output
        if arguments[0] == "nvidia-smi":
            return None
        return json.dumps(windows_adapters)
    monkeypatch.setattr(gpu, "run_command", fake_run_command)
    monkeypatch.setattr(gpu.sys, "platform", "win32")


def test_both_cards_are_listed_even_with_unsupported_values(monkeypatch):
    nvidia_output = "0, GPU-aaa, NVIDIA GeForce GTX 1660 Ti, 6144, 812, 4, 7.5\n1, GPU-bbb, NVIDIA GeForce GTX 1060 6GB, 6144, [N/A], [Not Supported], 6.1\n"
    install_fake_commands(monkeypatch, nvidia_output, [{"Name": "NVIDIA GeForce GTX 1660 Ti", "ConfigManagerErrorCode": 0}, {"Name": "NVIDIA GeForce GTX 1060 6GB", "ConfigManagerErrorCode": 0}])
    description = asyncio.run(gpu.describe_graphics_cards())
    assert [card["uuid"] for card in description["graphics_cards"]] == ["GPU-aaa", "GPU-bbb"]
    assert description["graphics_cards"][1]["memory_used_megabytes"] is None
    assert description["ignored_graphics_cards"] == []


def test_card_ignored_by_the_driver_is_explained(monkeypatch):
    nvidia_output = "0, GPU-aaa, NVIDIA GeForce GTX 1660 Ti, 6144, 812, 4, 7.5\n"
    install_fake_commands(monkeypatch, nvidia_output, [{"Name": "NVIDIA GeForce GTX 1660 Ti", "ConfigManagerErrorCode": 0}, {"Name": "NVIDIA GeForce GTX 1060 6GB", "ConfigManagerErrorCode": 43}])
    description = asyncio.run(gpu.describe_graphics_cards())
    assert len(description["graphics_cards"]) == 1
    assert description["ignored_graphics_cards"][0]["name"] == "NVIDIA GeForce GTX 1060 6GB"
    assert "code 43" in description["ignored_graphics_cards"][0]["problem"]
