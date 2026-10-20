from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psutil

from .config import Settings
from .errors import PipelineError
from .media import MediaTools


def nvidia_smi_path() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for candidate in (
        Path("C:/Windows/System32/nvidia-smi.exe"),
        Path("C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def gpu_snapshot() -> dict[str, Any]:
    executable = nvidia_smi_path()
    if not executable:
        return {"available": False, "reason": "nvidia-smi not found; no NVIDIA GPU assumed"}
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,driver_version,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode:
            return {"available": False, "reason": "nvidia-smi failed"}
        devices = []
        for line in result.stdout.strip().splitlines():
            name, driver, total, used, free = [part.strip() for part in line.split(",")]
            devices.append(
                {
                    "name": name,
                    "driver_version": driver,
                    "total_mib": float(total),
                    "used_mib": float(used),
                    "free_mib": float(free),
                }
            )
        return {
            "available": bool(devices),
            "devices": devices,
            "scope": "whole-device usage including other applications, not per-model allocation",
        }
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"available": False, "reason": "GPU memory query unavailable"}


def _cpu_name() -> str:
    if platform.system() == "Windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            ) as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return platform.processor()


def diagnose(settings: Settings) -> dict[str, Any]:
    directory = settings.data_dir
    while not directory.exists() and directory.parent != directory:
        directory = directory.parent
    disk = shutil.disk_usage(directory)
    memory = psutil.virtual_memory()
    packages = {}
    for name in ("faster-whisper", "ctranslate2", "pydantic", "psutil"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        media: dict[str, Any] = {"ready": True, **MediaTools(settings.media).check_capabilities()}
    except PipelineError as error:
        media = {"ready": False, "error": str(error)}
    cuda: dict[str, Any] = {"ctranslate2_available": False, "inference_validated": False}
    if packages["ctranslate2"]:
        try:
            import ctranslate2

            count = ctranslate2.get_cuda_device_count()
            cuda = {
                "ctranslate2_available": True,
                "device_count": count,
                "supported_compute_types": sorted(ctranslate2.get_supported_compute_types("cuda"))
                if count
                else [],
                "inference_validated": False,
            }
        except Exception as error:
            cuda = {
                "ctranslate2_available": True,
                "inference_validated": False,
                "error_type": error.__class__.__name__,
                "next_step": "check the installed CTranslate2 CUDA/cuDNN requirements",
            }
    return {
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": _cpu_name(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(),
        "ram_total_bytes": memory.total,
        "ram_available_bytes": memory.available,
        "disk_path": str(directory),
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "ffmpeg": media,
        "nvidia": gpu_snapshot(),
        "cuda": cuda,
        "packages": packages,
        "weights_present": (settings.transcription.model_path / "model.bin").is_file(),
        "mode": settings.mode,
        "downloads_performed": False,
        "cuda_note": "Driver detection is not proof that CUDA/cuDNN inference can run. "
        "Only a LOCAL benchmark validates the installed model and runtime.",
    }
