"""Name each form after the function crapper reports for it.

uml-viewer joins metrics on namespace and function name, so a candidate side
that carries crapper's names lines up with `.metrics/crap.edn`.
"""

from __future__ import annotations

from dataclasses import replace

from dryer.crapper_link import ensure_crapper
from dryer.model import Entry


def _size(fn) -> tuple[int, int]:
    return fn.end_line - fn.start_line, fn.start_line


def owner(functions, start: int, end: int):
    """The function starting on the form's line, else the smallest one around it."""

    exact = [fn for fn in functions if fn.start_line == start]
    around = [fn for fn in functions if fn.start_line <= start and end <= fn.end_line]
    return min(exact or around, key=_size, default=None)


def named(entries: list[Entry], language: str, source: str, file: str, root: str) -> list[Entry]:
    functions = ensure_crapper().languages.functions_in_file(language, source, file, root)
    found = []
    for entry in entries:
        fn = owner(functions, entry.start_line, entry.end_line)
        if fn is not None:
            entry = replace(entry, namespace=fn.namespace, name=fn.name)
        found.append(entry)
    return found
