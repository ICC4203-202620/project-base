"""Build four isolated Linux Lambda ZIPs; never copy the local Python environment.

Each ``backend/manifests/<function>.json`` explicitly selects source paths,
the handler and a requirements file. All paths are relative to ``backend``.
Dependencies must have binary wheels for the selected Lambda target.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

FUNCTION_NAMES = ("accounts", "domain", "photos", "notifications")
MAX_UNZIPPED_BYTES = 250 * 1024 * 1024
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
EXCLUDED_DIRECTORIES = {
    ".git",
    ".aws",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


class PackageError(ValueError):
    """A manifest, path or dependency set is not safe to deploy."""


def _excluded(path: Path) -> bool:
    name = path.name.lower()
    return (
        any(part in EXCLUDED_DIRECTORIES for part in path.parts)
        or name == ".env"
        or name.startswith(".env.")
        or name in {"credentials", "secrets", "secrets.json", "secrets.toml"}
        or name
        in {
            f"credentials.{suffix}" for suffix in ("json", "toml", "ini", "yaml", "yml")
        }
        or path.suffix.lower() in SECRET_SUFFIXES | {".pyc", ".pyo"}
    )


def _safe_source(root: Path, relative: str) -> Path:
    # POSIX manifest paths behave identically on Windows, macOS and Linux.
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
    ):
        raise PackageError("Manifest paths must be nonempty relative POSIX paths")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise PackageError(f"Path escapes backend: {relative}")
    path = root
    for part in parsed.parts:
        path = path / part
        if path.is_symlink():
            raise PackageError(f"Symbolic links are not packaged: {relative}")
    if not path.resolve().is_relative_to(root) or not path.exists():
        raise PackageError(f"Missing or external backend path: {relative}")
    if _excluded(path.relative_to(root)):
        raise PackageError(f"Excluded source path: {relative}")
    return path


def _requirements(root: Path, path: Path, seen: set[Path] | None = None) -> None:
    """Validate recursive includes before pip can read files outside backend.

    These manifests accept index requirements and local -r/-c includes, not
    executable editable/source projects, external paths or credentialed URLs.
    Pip still parses markers, hashes and the actual requirement specifiers.
    """
    seen = set() if seen is None else seen
    if path in seen:
        return
    seen.add(path)
    if not path.is_file():
        raise PackageError("A requirements path must be a regular file")
    content = path.read_text(encoding="utf-8").replace("\\\n", "")
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens = shlex.split(line, comments=True)
        if not tokens:
            continue
        first = tokens[0]
        include = None
        if first in {"-r", "--requirement", "-c", "--constraint"}:
            if len(tokens) != 2:
                raise PackageError("Requirements includes must name one local file")
            include = tokens[1]
        elif first.startswith(("--requirement=", "--constraint=")):
            if len(tokens) != 1:
                raise PackageError("Requirements includes must name one local file")
            include = first.partition("=")[2]
        elif first.startswith(("-r", "-c")) and not first.startswith("--"):
            if len(tokens) != 1:
                raise PackageError("Requirements includes must name one local file")
            include = first[2:]
        if include is not None:
            if ".." in PurePosixPath(include).parts:
                raise PackageError(
                    "Requirements includes must not traverse parent directories"
                )
            child = _safe_source(
                root, (path.parent.relative_to(root) / include).as_posix()
            )
            _requirements(root, child, seen)
            continue
        if first.startswith("-") or not re.match(
            r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[|[<>=!~; ]|$)", line
        ):
            raise PackageError(
                "Only indexed wheel requirements and local -r/-c includes are supported"
            )
        if any(marker in line for marker in ("@", "://", "${", "file:", "git+")):
            raise PackageError(
                "Direct URLs, environment expansion and local projects are not supported"
            )


def _source_files(root: Path, paths: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for relative in paths:
        selected = _safe_source(root, relative)
        candidates = sorted(selected.rglob("*")) if selected.is_dir() else [selected]
        for source in candidates:
            destination = source.relative_to(root)
            if _excluded(destination):
                continue
            if source.is_symlink():
                raise PackageError(f"Symbolic links are not packaged: {destination}")
            if source.is_file():
                result[destination.as_posix()] = source
    return result


def _load_manifest(root: Path, name: str) -> tuple[dict[str, Path], Path]:
    manifest_path = _safe_source(root, f"manifests/{name}.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackageError(f"Invalid manifest for {name}") from error
    if not isinstance(manifest, dict) or set(manifest) != {
        "handler",
        "files",
        "requirements",
    }:
        raise PackageError(
            f"Manifest {name} must contain handler, files and requirements"
        )
    handler = manifest["handler"]
    if not isinstance(handler, str) or not re.fullmatch(
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", handler
    ):
        raise PackageError(f"Invalid handler for {name}")
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        raise PackageError(f"Manifest {name} must select source files")
    sources = _source_files(root, manifest["files"])
    module = handler.rsplit(".", 1)[0].replace(".", "/")
    if f"{module}.py" not in sources and f"{module}/__init__.py" not in sources:
        raise PackageError(f"Manifest {name} does not include its handler module")
    requirements = _safe_source(root, manifest["requirements"])
    _requirements(root, requirements)
    return sources, requirements


def _pip_command(
    target: Path, requirements: Path, python_version: str, architecture: str
) -> list[str]:
    if python_version != "3.14":
        raise PackageError(
            "This base targets Lambda Python 3.14; runtime changes require a new compatibility check"
        )
    try:
        machine = {"x86_64": "x86_64", "arm64": "aarch64"}[architecture]
    except KeyError as error:
        raise PackageError("Lambda architecture must be x86_64 or arm64") from error
    command = [
        sys.executable,
        "-m",
        "pip",
        "--isolated",
        "--disable-pip-version-check",
        "install",
        "--target",
        str(target),
        "--implementation",
        "cp",
        "--python-version",
        python_version,
        "--only-binary=:all:",
        "--no-compile",
        "--ignore-installed",
    ]
    # Lambda Python 3.14 uses AL2023 (glibc 2.34). No host OS tags are allowed.
    # Leaving ABI selection to pip also admits CPython's older stable-ABI wheels.
    for minor in range(34, 16, -1):
        command.extend(["--platform", f"manylinux_2_{minor}_{machine}"])
    command.extend(
        ["--platform", f"manylinux2014_{machine}", "--requirement", str(requirements)]
    )
    return command


def _write_zip(directory: Path, destination: Path) -> None:
    files = []
    total_bytes = 0
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        # Application sources were already filtered before staging. Dependency
        # wheels contain legitimate credentials.py modules and public CA PEMs;
        # removing those breaks botocore imports and TLS certificate validation.
        # Only host caches/metadata are excluded from installed dependencies.
        if any(
            part in EXCLUDED_DIRECTORIES for part in relative.parts
        ) or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise PackageError("A dependency installed an unsupported symbolic link")
        if path.is_file():
            total_bytes += path.stat().st_size
            files.append((path, relative.as_posix()))
    if total_bytes >= MAX_UNZIPPED_BYTES:
        raise PackageError("Lambda ZIP contents must be smaller than 250 MiB")
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source, relative in files:
            info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())


def build_packages(
    backend_dir: Path,
    output_dir: Path,
    *,
    python_version: str = "3.14",
    architecture: str = "x86_64",
) -> dict[str, Path]:
    """Build every manifest into independent ZIPs, without calling AWS.

    Source selection is validated before installing anything. ZIPs replace
    earlier build artifacts only after all four builds have succeeded.
    """
    root = Path(backend_dir).resolve(strict=True)
    output = Path(output_dir).resolve()
    manifests = {name: _load_manifest(root, name) for name in FUNCTION_NAMES}
    _pip_command(Path("unused"), Path("unused"), python_version, architecture)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lambda-package-", dir=output) as workspace:
        temporary = Path(workspace)
        for name, (sources, requirements) in manifests.items():
            target = temporary / name
            target.mkdir()
            try:
                subprocess.run(
                    _pip_command(target, requirements, python_version, architecture),
                    check=True,
                    cwd=root,
                )
            except subprocess.CalledProcessError as error:
                raise PackageError(
                    f"Compatible Linux wheels could not be installed for {name}"
                ) from error
            for relative, source in sources.items():
                destination = target / relative
                if destination.exists():
                    raise PackageError(
                        f"Application source collides with an installed dependency: {relative}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            _write_zip(target, temporary / f"{name}.zip")
        result = {}
        for name in FUNCTION_NAMES:
            destination = output / f"{name}.zip"
            os.replace(temporary / destination.name, destination)
            result[name] = destination
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", type=Path, default=Path(__file__).resolve().parents[1] / "backend"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".build" / "packages",
    )
    parser.add_argument("--python-version", default="3.14")
    parser.add_argument("--architecture", choices=("x86_64", "arm64"), default="x86_64")
    args = parser.parse_args()
    try:
        packages = build_packages(
            args.backend,
            args.output,
            python_version=args.python_version,
            architecture=args.architecture,
        )
    except (PackageError, OSError) as error:
        parser.exit(1, f"Packaging failed: {error}\n")
    for name, path in packages.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
