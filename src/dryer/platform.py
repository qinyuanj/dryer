"""Everything that differs between Linux and native Windows.

Scanning and normalization stay host-agnostic: sources are read with universal
newlines, so a CRLF file normalizes like its LF twin, and the snapshot is
written as LF bytes, so `.metrics/dry.edn` is byte-identical on every host.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Windows 10 22H2. Windows 11 builds start at 22000.
MIN_WINDOWS_BUILD = 19045

# ERROR_ACCESS_DENIED and ERROR_SHARING_VIOLATION: another process (an editor,
# a viewer, antivirus) holds the snapshot open without FILE_SHARE_DELETE.
_TRANSIENT_WINERRORS = {5, 32}
REPLACE_ATTEMPTS = 8
_FIRST_DELAY = 0.05
_MAX_DELAY = 1.0


def windows_build() -> int:
    return sys.getwindowsversion().build


def platform_refusal(platform: str, build: int | None) -> str | None:
    """Native Windows runs from Windows 10 22H2 on; older builds are refused."""

    if platform != "win32" or build >= MIN_WINDOWS_BUILD:
        return None
    return (
        f"dryer needs Windows 10 22H2 (build {MIN_WINDOWS_BUILD}) or later; this is build {build}. "
        "Update Windows, or run dryer inside WSL2; see the README."
    )


def platform_warning(platform: str, root: Path) -> str | None:
    """Under WSL2, a project on a Windows drive is slow and loses symlinks."""

    if platform != "win32" and root.as_posix().startswith("/mnt/"):
        return (
            f"{root} is on a Windows drive. Under WSL2, clone the project under ~/ "
            "for speed and working symlinks."
        )
    return None


def lf_stdout() -> None:
    """Windows stdout writes CRLF by default; the EDN report must be the same bytes everywhere."""

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(newline="\n")


def read_source(path: Path) -> str:
    """Decode with universal newlines: CRLF and CR read as LF."""

    with open(path, encoding="utf-8", errors="replace", newline=None) as stream:
        return stream.read()


def _transient(error: OSError) -> bool:
    return getattr(error, "winerror", None) in _TRANSIENT_WINERRORS


def _replace(temp: str, path: Path) -> None:
    delay = _FIRST_DELAY
    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            os.replace(temp, path)
            return
        except OSError as error:
            if attempt == REPLACE_ATTEMPTS or not _transient(error):
                raise
        time.sleep(delay)
        delay = min(delay * 2, _MAX_DELAY)


def publish(path: Path, text: str) -> None:
    """Write LF bytes beside `path`, then swap them in, so a reader never sees half a file."""

    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
        os.chmod(temp, 0o644)
        _replace(temp, path)
    except BaseException:
        os.unlink(temp)
        raise
