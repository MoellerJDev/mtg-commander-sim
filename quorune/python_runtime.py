"""Supported Python runtime policy for the application and its tooling."""

from __future__ import annotations

import sys
import platform
from typing import Protocol


SUPPORTED_PYTHON = (3, 12)
SUPPORTED_PYTHON_TEXT = "3.12"
REQUIRES_PYTHON = ">=3.12,<3.13"


class VersionInfo(Protocol):
    major: int
    minor: int


class UnsupportedPythonRuntime(RuntimeError):
    """Raised when the application is executed outside its pinned runtime."""


def require_supported_python(version_info: VersionInfo = sys.version_info) -> None:
    require_supported_runtime(version_info)


def require_supported_runtime(
    version_info: VersionInfo = sys.version_info,
    *,
    implementation: str = platform.python_implementation(),
    maxsize: int = sys.maxsize,
) -> None:
    observed = (version_info.major, version_info.minor)
    if observed != SUPPORTED_PYTHON or implementation != "CPython" or maxsize <= 2**32:
        raise UnsupportedPythonRuntime(
            "Quorune requires 64-bit CPython 3.12.x exactly; "
            f"found {implementation} {version_info.major}.{version_info.minor} "
            f"({64 if maxsize > 2**32 else 32}-bit). "
            "On Windows, create the project environment with "
            "`py -3.12 -m venv .venv`."
        )
