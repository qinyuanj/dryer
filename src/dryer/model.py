from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """Where one candidate form sits, and the crapper function it belongs to."""

    file: str
    start_line: int
    end_line: int
    namespace: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class Duplicate:
    """One pair of forms whose normalized structure is similar enough to report."""

    score: float
    language: str
    left: Span
    right: Span
    left_nodes: int
    right_nodes: int


@dataclass(frozen=True)
class Entry:
    """A normalized form ready to compare. Forms are only compared within one language."""

    language: str
    file: str
    start_line: int
    end_line: int
    nodes: int
    fingerprints: frozenset[str]
    namespace: str | None = None
    name: str | None = None
