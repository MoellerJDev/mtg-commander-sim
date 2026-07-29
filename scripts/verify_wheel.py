from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    wheels = sorted(args.dist.glob("mtg_commander_sim-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected exactly one project wheel, found {len(wheels)}")
    wheel = wheels[0].resolve()
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
    print(f"Verified clean installation and CLI smoke test for {wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
