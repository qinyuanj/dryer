import os
import shutil
from pathlib import Path

import pytest

from dryer.crapper_link import ensure_crapper
from dryer.model import Duplicate, Span
from dryer.names import owner
from dryer.report import render_edn, write_metrics
from dryer.scan import find_duplicates, scan_files


def write_source(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sides(root: Path, threshold: float = 0.99, min_lines: int = 1):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    entries, warnings = scan_files(files, root, min_lines=min_lines, min_nodes=1)
    assert warnings == []
    return [
        [(side.file, side.namespace, side.name) for side in (item.left, item.right)]
        for item in find_duplicates(entries, threshold)
    ]


def fn(name: str, start: int, end: int):
    return ensure_crapper().model.Function(name, "ns", 1, start, end, "a.py", "python")


def test_python_sides_carry_crappers_namespace_and_name(tmp_path):
    write_source(
        tmp_path,
        "src/shop/cart.py",
        "class Cart:\n    def total(self, xs):\n        ys = filter(xs, odd)\n        return map(ys, inc)\n",
    )
    write_source(
        tmp_path,
        "src/shop/order.py",
        "def amount(items):\n    kept = filter(items, even)\n    return map(kept, dec)\n",
    )
    assert sides(tmp_path, threshold=0.5) == [
        [("src/shop/cart.py", "shop.cart.Cart", "total"), ("src/shop/order.py", "shop.order", "amount")]
    ]


def test_lua_sides_carry_the_require_path(tmp_path):
    project = tmp_path / "lua_project"
    shutil.copytree(Path(__file__).parent / "fixtures" / "lua_project", project)
    files = sorted((project / "src").rglob("*.lua"))
    entries, _ = scan_files(files, project, 4, 20)
    found = find_duplicates(entries, 0.82)
    assert [(item.left.namespace, item.left.name, item.right.namespace, item.right.name) for item in found] == [
        ("calc", "M.total", "calc.stats", "M.sum_clamped")
    ]


def test_clojure_defns_are_named_and_other_forms_are_not(tmp_path):
    body = "  (let [ys (filter odd? xs)]\n    (map inc ys)))\n"
    write_source(tmp_path, "src/app/left.clj", f"(ns app.left)\n\n(defn alpha [xs]\n{body}")
    write_source(tmp_path, "src/app/right.cljd", f"(ns app.right)\n\n(def beta (fn [xs]\n{body[:-1]})\n")
    assert sides(tmp_path, threshold=0.5) == [
        [("src/app/left.clj", "app.left", "alpha"), ("src/app/right.cljd", None, None)]
    ]


def test_the_function_starting_on_the_form_line_wins():
    outer = fn("outer", 1, 20)
    inner = fn("inner", 5, 9)
    other = fn("other", 5, 30)
    assert owner([outer, other, inner], 5, 9) == inner
    assert owner([outer, other], 5, 9) == other
    assert owner([inner, outer], 5, 9) == inner


def test_otherwise_the_smallest_function_around_the_form_wins():
    outer = fn("outer", 1, 20)
    middle = fn("middle", 3, 12)
    assert owner([outer, middle], 4, 12) == middle
    assert owner([middle, outer], 4, 12) == middle
    assert owner([outer, middle], 2, 13) == outer
    assert owner([outer, middle], 4, 21) is None
    assert owner([outer, middle], 21, 22) is None
    assert owner([], 1, 1) is None


def test_size_is_the_number_of_lines_spanned():
    early = fn("early", 1, 12)
    late = fn("late", 6, 15)
    assert owner([early, late], 7, 11) == late


def test_equal_sizes_prefer_the_earlier_function():
    first = fn("first", 2, 6)
    second = fn("second", 3, 7)
    assert owner([second, first], 4, 6) == first


def test_edn_sides_end_with_namespace_and_name():
    candidate = Duplicate(
        0.875,
        "python",
        Span("a.py", 10, 14, "pkg.a", 'say "hi"'),
        Span("b.py", 20, 24),
        30,
        31,
    )
    assert render_edn([candidate]) == (
        "{:candidates [\n"
        " {:score 0.875\n"
        '  :language "python"\n'
        '  :left {:file "a.py", :start-line 10, :end-line 14, :namespace "pkg.a", :name "say \\"hi\\""}\n'
        '  :right {:file "b.py", :start-line 20, :end-line 24, :namespace nil, :name nil}\n'
        "  :left-nodes 30\n"
        "  :right-nodes 31}\n"
        "]}\n"
    )


def test_the_snapshot_is_replaced_in_one_step(tmp_path, monkeypatch):
    path = tmp_path / ".metrics" / "dry.edn"
    write_metrics([], tmp_path)
    seen = []
    real = os.replace

    def replace(source, target):
        seen.append((Path(source).parent, Path(source).read_text(encoding="utf-8"), Path(target)))
        real(source, target)

    monkeypatch.setattr("dryer.report.os.replace", replace)
    assert write_metrics([], tmp_path) == path
    assert seen == [(path.parent, "{:candidates []}\n", path)]
    assert os.listdir(path.parent) == ["dry.edn"]
    assert oct(path.stat().st_mode & 0o777) == oct(0o644)


def test_a_failed_write_keeps_the_previous_snapshot(tmp_path, monkeypatch):
    path = tmp_path / ".metrics" / "dry.edn"
    path.parent.mkdir()
    path.write_text("previous\n", encoding="utf-8")

    def broken(source, target):
        raise OSError("disk full")

    monkeypatch.setattr("dryer.report.os.replace", broken)
    with pytest.raises(OSError, match="disk full"):
        write_metrics([], tmp_path)
    assert path.read_text(encoding="utf-8") == "previous\n"
    assert os.listdir(path.parent) == ["dry.edn"]

