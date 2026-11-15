"""Discover optional local tools without storing machine-specific paths."""
import argparse
import os
import shutil
from pathlib import Path


def resolve_vice(value=None):
    location = value or os.environ.get("VICE_ROOT")
    if location:
        path = Path(location).expanduser()
        if path.is_dir():
            for directory in (path / "bin", path):
                for name in ("x64sc.exe", "x64sc"):
                    executable = directory / name
                    if executable.is_file():
                        return str(executable.resolve())
        elif path.is_file():
            return str(path.resolve())
        executable = shutil.which(location)
        if executable:
            return executable
        raise FileNotFoundError("VICE was not found at the supplied location. Set VICE_ROOT to its installation directory.")
    executable = shutil.which("x64sc")
    if executable:
        return executable
    raise FileNotFoundError("VICE was not found. Put x64sc on PATH or set VICE_ROOT to its installation directory.")


def add_vice_argument(parser):
    def parse(value):
        try:
            return resolve_vice(value)
        except OSError as error:
            raise argparse.ArgumentTypeError(str(error)) from error

    parser.add_argument("--vice", type=parse, default=os.environ.get("VICE_ROOT") or "x64sc",
                        help="VICE executable or installation directory (default: VICE_ROOT or PATH)")
