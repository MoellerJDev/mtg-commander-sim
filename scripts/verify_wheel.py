from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile

from mtg_commander_sim.python_runtime import REQUIRES_PYTHON, require_supported_python
from packaging.specifiers import InvalidSpecifier, SpecifierSet


def _wheel_requires_python(wheel: Path) -> str | None:
    with zipfile.ZipFile(wheel) as archive:
        metadata_paths = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError(
                f"Expected one wheel METADATA file, found {len(metadata_paths)}"
            )
        for line in archive.read(metadata_paths[0]).decode("utf-8").splitlines():
            if line.startswith("Requires-Python: "):
                return line.removeprefix("Requires-Python: ")
    return None


def _requires_python_matches(observed: str | None) -> bool:
    if observed is None:
        return False
    try:
        return SpecifierSet(observed) == SpecifierSet(REQUIRES_PYTHON)
    except InvalidSpecifier:
        return False


def main() -> int:
    require_supported_python()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    wheels = sorted(args.dist.glob("mtg_commander_sim-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected exactly one project wheel, found {len(wheels)}")
    wheel = wheels[0].resolve()
    observed_requirement = _wheel_requires_python(wheel)
    if not _requires_python_matches(observed_requirement):
        raise SystemExit(
            f"Wheel Requires-Python must be {REQUIRES_PYTHON!r}; "
            f"found {observed_requirement!r}"
        )
    with tempfile.TemporaryDirectory() as temporary:
        environment = Path(temporary) / "wheel-venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = (
            environment / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else environment / "bin" / "python"
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-c",
                (
                    "import mtg_commander_sim as package; "
                    "print(package.__version__)"
                ),
            ],
            check=True,
        )
        subprocess.run(
            [str(python), "-m", "mtg_commander_sim", "--help"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(python),
                "-c",
                (
                    "from importlib.metadata import distribution; "
                    "entries = {entry.name: entry.value for entry in "
                    "distribution('mtg-commander-sim').entry_points "
                    "if entry.group == 'console_scripts'}; "
                    "assert entries['commander-server'] == "
                    "'server.__main__:main', entries"
                ),
            ],
            check=True,
        )
    print(
        "Verified clean installation, simulation CLI, and server entry point "
        f"for {wheel.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
