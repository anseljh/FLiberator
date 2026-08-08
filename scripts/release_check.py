"""Build and validate distributable FLiberator artifacts in an isolated directory."""

import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def check_sdist(dist: pathlib.Path) -> None:
    forbidden = ("/.claude/", "/.github/", "/data/", "/plans/", "/scripts/", "/tests/")
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        included = archive.getnames()
    unexpected = [name for name in included if any(part in name for part in forbidden)]
    if unexpected:
        message = "source distribution includes repository-only files:\n" + "\n".join(unexpected)
        raise SystemExit(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="fliberator-release-") as temporary:
        temporary_path = pathlib.Path(temporary)
        dist = temporary_path / "dist"
        run(sys.executable, "-m", "build", "--outdir", str(dist))
        check_sdist(dist)

        artifacts = sorted(str(path) for path in dist.iterdir())
        run(sys.executable, "-m", "twine", "check", "--strict", *artifacts)

        environment = temporary_path / "venv"
        run(sys.executable, "-m", "venv", str(environment))
        bin_directory = environment / ("Scripts" if os.name == "nt" else "bin")
        wheel = next(dist.glob("*.whl"))
        run(str(bin_directory / "python"), "-m", "pip", "install", str(wheel))
        run(str(bin_directory / "fliberate"), "--version")


if __name__ == "__main__":
    main()
