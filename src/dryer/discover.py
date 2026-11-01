"""Pick source files the way crapper and mutator do.

The one difference is `.cljd`: dry4clj reads it, so it is Clojure here and
`_test.cljd` is a test.
"""

import os
from pathlib import Path

from dryer.crapper_link import ensure_crapper


def _crapper():
    return ensure_crapper().discover


def language_of(path: str | Path) -> str | None:
    if Path(path).suffix == ".cljd":
        return "clojure"
    return _crapper().language_of(path)


def is_test_file(path: str | Path) -> bool:
    return Path(path).name.endswith("_test.cljd") or _crapper().is_test_file(path)


def is_source_file(path: Path) -> bool:
    return language_of(path) is not None and not is_test_file(path)


def _walk(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    skipped = _crapper().SKIP_DIRS | _crapper().TEST_DIRS
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in skipped]
        paths = (Path(dirpath) / name for name in filenames)
        found.extend(path for path in paths if is_source_file(path))
    return found


def iter_source_files(roots: list[Path]) -> list[Path]:
    files = {path.resolve() for root in roots for path in _walk(root)}
    return sorted(files, key=lambda path: path.as_posix())
