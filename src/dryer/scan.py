"""Read source files and pair the forms that clear the similarity threshold."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

from dryer.discover import language_of
from dryer.extract import entries_in_source
from dryer.model import Duplicate, Entry, Span
from dryer.names import named
from dryer.platform import read_source
from dryer.shape import jaccard


def display_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    return resolved.relative_to(root.resolve()).as_posix()


def _keep(entry: Entry, min_lines: int, min_nodes: int) -> bool:
    lines = entry.end_line - entry.start_line + 1
    return lines >= min_lines and entry.nodes >= min_nodes


def scan_files(
    files: list[Path], root: Path, min_lines: int, min_nodes: int
) -> tuple[list[Entry], list[str]]:
    entries: list[Entry] = []
    warnings: list[str] = []
    for path in files:
        language = language_of(path)
        if language is None:
            continue
        source = read_source(path)
        file = display_path(path, root)
        found, warning = entries_in_source(language, source, path.as_posix(), file)
        if warning:
            warnings.append(f"{file}:{warning}")
        kept = [entry for entry in found if _keep(entry, min_lines, min_nodes)]
        entries.extend(named(kept, language, source, file, str(root.resolve())))
    return entries, warnings


def _span(entry: Entry) -> Span:
    return Span(entry.file, entry.start_line, entry.end_line, entry.namespace, entry.name)


def _same_span(left: Entry, right: Entry) -> bool:
    if left.file != right.file:
        return False
    if left.start_line != right.start_line:
        return False
    return left.end_line == right.end_line


def _duplicate_key(item: Duplicate):
    score = -item.score
    return (
        score,
        item.language,
        item.left.file,
        item.left.start_line,
        item.right.file,
        item.right.start_line,
    )


def find_duplicates(entries: list[Entry], threshold: float) -> list[Duplicate]:
    """Pair forms of the same language. Each unordered pair is reported once."""

    by_language: dict[str, list[Entry]] = {}
    for entry in entries:
        by_language.setdefault(entry.language, []).append(entry)

    found: list[Duplicate] = []
    for language, group in by_language.items():
        for left, right in combinations(group, 2):
            if _same_span(left, right):
                continue
            score = jaccard(left.fingerprints, right.fingerprints)
            if score < threshold:
                continue
            found.append(
                Duplicate(
                    score=score,
                    language=language,
                    left=_span(left),
                    right=_span(right),
                    left_nodes=left.nodes,
                    right_nodes=right.nodes,
                )
            )
    found.sort(key=_duplicate_key)
    return found
