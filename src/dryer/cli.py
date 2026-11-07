"""Command line for the multi-language duplication finder."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from dryer.crapper_link import ensure_crapper
from dryer.discover import is_source_file, iter_source_files, language_of
from dryer.platform import lf_stdout, platform_refusal, platform_warning, windows_build
from dryer.report import format_text, render_edn, write_metrics
from dryer.scan import find_duplicates, scan_files

HELP = """\
Usage: dryer [options] [path-or-filter ...]

Find candidate duplicate code in Clojure, Java, Go, TypeScript, Rust, Python,
and Lua. Each form is normalized — call and method names, operators, and
tree shape stay; local names, field names, and literals do not — and compared
with the other forms of the same language. The score is Jaccard similarity of
those structural fingerprints, the same score as dry4clj.

Prints a report and writes .metrics/dry.edn.

Languages: Clojure (.clj .cljc .cljs .cljd .bb), Java (.java), Go (.go),
TypeScript (.ts .tsx .mts .cts), Rust (.rs), Python (.py), Lua (.lua).

Options:
  -h, --help                    Print this help and exit.
  --root <path>                 Project root. Metrics are written here.
                                Default: the current directory.
  -s, --source-root <path>      Walk this tree instead of the project root.
                                May be repeated. Path arguments and --changed
                                are narrowed to the files under a source root.
  --exclude <glob>              Leave out files under this path or glob,
                                relative to the project root. May be repeated.
                                * and ? match within one directory name, **
                                matches any number of directories, and a
                                matched directory excludes everything in it.
  --changed                     Compare source files git reports as added,
                                modified, renamed, or untracked under the
                                project root. With --source-root, only those
                                under a root.
  --threshold N                 Minimum similarity score, default 0.82.
  --min-lines N                 Minimum source lines in a candidate form,
                                default 4.
  --min-nodes N                 Minimum normalized syntax nodes, default 20.
  --format F                    text or edn, default text.
  --edn                         Same as --format edn.
  --text                        Same as --format text.

Arguments:
  path              File or directory to compare within --root. Sources outside
                    the project root are a usage error before publication.
                    A file you name is compared
                    even when it is a test or sits in a skipped directory; to
                    match crapper and mutator, pass the same -s and --exclude
                    instead of a file list. With --source-root, a named file
                    outside every root is dropped:
                    "Skipping <path>; it is outside the source roots" on stderr.
  filter            When the argument is not a path, only source files whose
                    path contains this text are compared.

With no paths, source files under the project root are compared. Files are
chosen as crapper and mutator choose them, plus .cljd. Directories named test,
tests, spec, specs, vendor, node_modules, and target are skipped, as are
*_test.go, *.spec.ts, test_*.py, *_test.py, *_spec.lua, and *_test.cljd files.

Each side of a candidate in .metrics/dry.edn carries the :namespace and :name
crapper reports for that function, or nil when crapper has no function there.

Clojure compares every top-level form except ns. The other languages compare
functions and methods. A form is only compared with forms in the same language.

Exit codes:
  0  the report was written
  1  usage error, including a bad --exclude or crapper missing
  2  unknown output format
"""


@dataclass
class Options:
    action: str
    message: str = ""
    exit_code: int = 0
    project_root: Path = field(default_factory=lambda: Path("."))
    source_roots: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    positionals: list[str] = field(default_factory=list)
    threshold: float = 0.82
    min_lines: int = 4
    min_nodes: int = 20
    format: str = "text"
    changed: bool = False


def _take(args: list[str], index: int, option: str) -> str:
    if index + 1 >= len(args) or not args[index + 1] or args[index + 1].startswith("-"):
        raise ValueError(f"{option} requires a value")
    return args[index + 1]


def _number(value: str, option: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{option} requires a number") from exc


def _count(value: str, option: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{option} requires an integer") from exc
    if parsed < 0:
        raise ValueError(f"{option} requires a non-negative integer")
    return parsed


def _path(value: str, option: str) -> Path:
    return Path(value)


def _text(value: str, option: str) -> str:
    return value


_VALUE_OPTIONS = {
    "--root": ("project_root", _path),
    "--threshold": ("threshold", _number),
    "--min-lines": ("min_lines", _count),
    "--min-nodes": ("min_nodes", _count),
    "--format": ("format", _text),
}

_LISTS = {"-s": "source_roots", "--source-root": "source_roots", "--exclude": "excludes"}

_FLAG_OPTIONS = {
    "--edn": ("format", "edn"),
    "--text": ("format", "text"),
    "--changed": ("changed", True),
}


def _parse_option(options: Options, args: list[str], index: int) -> int:
    """Apply the option at `index` and return the index of the next one."""

    arg = args[index]
    if arg in _LISTS:
        getattr(options, _LISTS[arg]).append(_take(args, index, arg))
        return index + 2
    if arg in _VALUE_OPTIONS:
        name, convert = _VALUE_OPTIONS[arg]
        setattr(options, name, convert(_take(args, index, arg), arg))
        return index + 2
    if arg in _FLAG_OPTIONS:
        name, value = _FLAG_OPTIONS[arg]
        setattr(options, name, value)
        return index + 1
    if arg.startswith("-"):
        raise ValueError(f"Unknown option: {arg}")
    options.positionals.append(arg)
    return index + 1


def parse_args(argv: list[str] | None = None) -> Options:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg in {"-h", "--help"} for arg in args):
        return Options(action="help", message=HELP, exit_code=0)
    options = Options(action="scan")
    index = 0
    try:
        while index < len(args):
            index = _parse_option(options, args, index)
    except ValueError as exc:
        return Options(action="help", message=f"{exc}\n\n{HELP}", exit_code=1)
    if options.format not in {"text", "edn"}:
        return Options(
            action="format",
            message=f"Unknown format: {options.format}\n",
            exit_code=2,
        )
    return _refusal(options) or options


def _require_crapper() -> str | None:
    try:
        ensure_crapper()
    except ImportError as exc:
        return str(exc)
    return None


def _refusal(options: Options) -> Options | None:
    """crapper picks the files, so it must be there, and exclusions stay in the project."""

    missing = _require_crapper()
    if missing:
        return Options(action="help", message=missing, exit_code=1)
    errors = [error for error in map(_crapper().exclusion_error, options.excludes) if error]
    if errors:
        return Options(action="help", message=f"{errors[0]}\n\n{HELP}", exit_code=1)
    return None


def _crapper():
    return ensure_crapper().discover


def _positionals(root: Path, args: list[str]) -> tuple[list[Path], list[str]]:
    existing: list[Path] = []
    filters: list[str] = []
    for arg in args:
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = root / arg
        if candidate.exists():
            existing.append(candidate.resolve())
        else:
            filters.append(arg)
    return existing, filters


def _changed_source(root: Path) -> list[Path]:
    return [path for path in _crapper().changed_files(root) if is_source_file(path)]


def _in_scope(files: list[Path], roots: list[Path]) -> list[Path]:
    """Source roots narrow every other selection to the files under them."""

    return _crapper().under_roots(files, roots) if roots else files


def _shown(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def _explicit_files(existing: list[Path], root: Path, excludes: list[str], roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in existing:
        if path.is_dir():
            files.extend(_in_scope(iter_source_files([path]), roots))
        elif not _in_scope([path], roots):
            print(f"Skipping {_shown(path, root)}; it is outside the source roots", file=sys.stderr)
        elif _crapper().excluded(path, root, excludes):
            print(f"Skipping excluded {path.relative_to(root).as_posix()}", file=sys.stderr)
        elif language_of(path) is not None:
            files.append(path)
    return files


def _selected(options: Options, root: Path, existing: list[Path]) -> list[Path]:
    roots = [(root / path).resolve() for path in options.source_roots]
    if options.changed:
        return _in_scope(_changed_source(root), roots)
    if existing:
        return _explicit_files(existing, root, options.excludes, roots)
    return iter_source_files(roots or [root])


def _apply_filters(files: list[Path], filters: list[str]) -> list[Path]:
    if not filters:
        return files
    return [path for path in files if any(item in path.as_posix() for item in filters)]


def select_files(options: Options) -> list[Path]:
    root = options.project_root.resolve()
    existing, filters = _positionals(root, options.positionals)
    selected = _crapper().without_excluded(_selected(options, root, existing), root, options.excludes)
    files = _apply_filters(selected, filters)
    resolved = {path.resolve() for path in files}
    for path in resolved:
        if not path.is_relative_to(root):
            raise ValueError(f"Source {path.as_posix()} is outside the project root")
    return sorted(resolved, key=lambda path: path.as_posix())


def run(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    if options.action == "help":
        stream = sys.stdout if options.exit_code == 0 else sys.stderr
        print(options.message, file=stream, end="" if options.message.endswith("\n") else "\n")
        return options.exit_code
    if options.action == "format":
        print(options.message, file=sys.stderr, end="")
        return options.exit_code

    refusal = platform_refusal(sys.platform, windows_build() if sys.platform == "win32" else None)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    root = options.project_root.resolve()
    warning = platform_warning(sys.platform, root)
    if warning:
        print(warning, file=sys.stderr)
    try:
        files = select_files(options)
    except ValueError as error:
        print(f"dryer: {error}", file=sys.stderr)
        return 1
    if not files:
        print("No source files to analyze.")
        return 0

    entries, warnings = scan_files(files, root, options.min_lines, options.min_nodes)
    for warning in warnings:
        print(f"dryer: {warning}", file=sys.stderr)
    candidates = find_duplicates(entries, options.threshold)
    metrics = write_metrics(candidates, root)
    if options.format == "edn":
        print(render_edn(candidates), end="")
    else:
        print(format_text(candidates), end="")
    print(f"Wrote {metrics}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> None:
    lf_stdout()
    sys.exit(run(argv))
