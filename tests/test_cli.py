from pathlib import Path

import pytest

import subprocess

from dryer.cli import HELP, _count, main, parse_args, run, select_files
from dryer.crapper_link import ensure_crapper
from dryer.discover import is_source_file, is_test_file, iter_source_files, language_of


def write_source(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_language_detection():
    assert language_of("src/app/core.clj") == "clojure"
    assert language_of("src/app/core.cljd") == "clojure"
    assert language_of("Widget.java") == "java"
    assert language_of("board.go") == "go"
    assert language_of("ui/view.tsx") == "typescript"
    assert language_of("src/lib.rs") == "rust"
    assert language_of("src/dryer/cli.py") == "python"
    assert language_of("src/calc/init.lua") == "lua"
    assert language_of("types.d.ts") is None
    assert language_of("notes.md") is None


def test_help_does_not_scan(capsys):
    assert run(["--help"]) == 0
    out = capsys.readouterr().out
    assert "Usage: dryer" in out
    assert "--threshold" in out


def test_unknown_format(capsys):
    assert run(["--format", "csv"]) == 2
    err = capsys.readouterr().err
    assert err == "Unknown format: csv\n"


def test_unknown_option(capsys):
    assert run(["--nope"]) == 1
    assert "Unknown option: --nope" in capsys.readouterr().err


def test_parse_defaults_and_flags():
    options = parse_args(
        ["--threshold", "0.9", "--min-lines", "5", "--min-nodes", "30", "--edn", "spec"]
    )
    assert options.threshold == 0.9
    assert options.min_lines == 5
    assert options.min_nodes == 30
    assert options.format == "edn"
    assert options.positionals == ["spec"]


def test_project_report_and_snapshot(tmp_path, capsys):
    write_source(
        tmp_path,
        "src/left.py",
        "def alpha(xs):\n    ys = filter(xs, odd)\n    zs = map(ys, inc)\n    return list(zs)\n",
    )
    write_source(
        tmp_path,
        "src/right.py",
        "def beta(items):\n    kept = filter(items, even)\n    out = map(kept, dec)\n    return list(out)\n",
    )
    write_source(
        tmp_path,
        "tests/test_left.py",
        "def alpha(xs):\n    ys = filter(xs, odd)\n    zs = map(ys, inc)\n    return list(zs)\n",
    )
    code = run(["--root", str(tmp_path), "--min-lines", "3", "--min-nodes", "1"])
    captured = capsys.readouterr()
    assert code == 0
    assert "DUPLICATE score=1.00" in captured.out
    assert "src/left.py:1-" in captured.out
    assert "src/right.py:1-" in captured.out
    assert "test_left.py" not in captured.out
    text = (tmp_path / ".metrics" / "dry.edn").read_text(encoding="utf-8")
    assert ':language "python"' in text
    assert ':file "src/left.py"' in text
    assert "Wrote" in captured.err


def test_edn_stdout(tmp_path, capsys):
    write_source(tmp_path, "one.py", "def alpha(xs):\n    return xs\n")
    assert run(["--root", str(tmp_path), "--edn", "--min-lines", "1", "--min-nodes", "1"]) == 0
    out = capsys.readouterr().out
    assert out == "{:candidates []}\n"


def test_a_missing_root_is_created_for_the_snapshot(tmp_path, capsys):
    write_source(tmp_path, "src/one.py", "def alpha(xs):\n    return xs\n")
    root = tmp_path / "fresh" / "project"
    assert run(["--root", str(root), str(tmp_path / "src" / "one.py")]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"
    assert (root / ".metrics" / "dry.edn").read_text(encoding="utf-8") == "{:candidates []}\n"


def test_empty_project(tmp_path, capsys):
    assert run(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "No source files to analyze.\n"


def test_path_filter(tmp_path, capsys):
    body_a = "def alpha(xs):\n    ys = filter(xs, odd)\n    zs = map(ys, inc)\n    return list(zs)\n"
    body_b = "def beta(items):\n    kept = filter(items, even)\n    out = map(kept, dec)\n    return list(out)\n"
    write_source(tmp_path, "src/board/a.py", body_a)
    write_source(tmp_path, "src/board/b.py", body_b)
    write_source(tmp_path, "src/other/a.py", body_a)
    write_source(tmp_path, "src/other/b.py", body_b)
    assert run(["--root", str(tmp_path), "--min-lines", "3", "--min-nodes", "1", "board"]) == 0
    out = capsys.readouterr().out
    assert "src/board/a.py" in out
    assert "src/other/a.py" not in out


def test_explicit_test_file_is_included(tmp_path, capsys):
    body = "def alpha(xs):\n    ys = filter(xs, odd)\n    zs = map(ys, inc)\n    return list(zs)\n"
    other = "def beta(items):\n    kept = filter(items, even)\n    out = map(kept, dec)\n    return list(out)\n"
    write_source(tmp_path, "src/a.py", body)
    write_source(tmp_path, "tests/test_a.py", other)
    assert (
        run(
            [
                "--root",
                str(tmp_path),
                "--min-lines",
                "3",
                "--min-nodes",
                "1",
                "src/a.py",
                "tests/test_a.py",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "src/a.py" in out
    assert "tests/test_a.py" in out


def test_main_exits(monkeypatch):
    codes = []
    monkeypatch.setattr("dryer.cli.sys.exit", lambda code: codes.append(code))
    main(["--help"])
    assert codes == [0]


def test_names_that_are_tests():
    names = [
        "pkg/foo_test.go",
        "src/app_test.clj",
        "src/app_test.cljc",
        "src/app_test.cljs",
        "src/app_test.cljd",
        "src/app_test.bb",
        "ui/a.test.ts",
        "ui/a.spec.ts",
        "ui/a.test.tsx",
        "ui/a.spec.tsx",
        "ui/a.test.mts",
        "ui/a.spec.mts",
        "tests/conftest.py",
        "pkg/foo_test.py",
        "pkg/test_foo.py",
        "tests/app.py",
    ]
    for name in names:
        assert is_test_file(name), name
    assert not is_test_file("src/app.py")


def test_an_option_without_a_value_is_a_usage_error(capsys):
    assert run(["--threshold"]) == 1
    assert "--threshold requires a value" in capsys.readouterr().err


def test_an_empty_value_is_rejected(capsys):
    assert run(["file.py", "--min-lines", ""]) == 1
    assert "--min-lines requires a value" in capsys.readouterr().err


def test_a_flag_is_not_a_value(capsys):
    assert run(["--min-lines", "--min-nodes", "1"]) == 1
    assert "--min-lines requires a value" in capsys.readouterr().err


def test_zero_is_a_valid_count():
    options = parse_args(["--min-lines", "0", "--min-nodes", "0"])
    assert options.action == "scan"
    assert options.min_lines == 0
    assert options.min_nodes == 0


def test_a_negative_count_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        _count("-1", "--min-lines")


def test_a_count_must_be_an_integer(capsys):
    assert run(["--min-lines", "nope"]) == 1
    assert "--min-lines requires an integer" in capsys.readouterr().err


def test_a_threshold_must_be_a_number(capsys):
    assert run(["--threshold", "nope"]) == 1
    assert "--threshold requires a number" in capsys.readouterr().err


def test_parse_reads_the_process_arguments(monkeypatch):
    monkeypatch.setattr("dryer.cli.sys.argv", ["dryer", "only-this"])
    assert parse_args().positionals == ["only-this"]


def test_text_format_wins_when_it_comes_last(tmp_path, capsys):
    write_source(tmp_path, "one.py", "def alpha(xs):\n    return xs\n")
    assert run(["--root", str(tmp_path), "--edn", "--text", "--min-lines", "1", "--min-nodes", "1"]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"


def test_source_root_limits_the_walk(tmp_path):
    write_source(tmp_path, "src/a.py", "x = 1\n")
    write_source(tmp_path, "extra/b.py", "x = 1\n")
    options = parse_args(["--root", str(tmp_path), "--source-root", "src"])
    files = [path.relative_to(tmp_path).as_posix() for path in select_files(options)]
    assert files == ["src/a.py"]


def test_installed_tooling_is_not_project_source(tmp_path):
    write_source(tmp_path, "src/a.py", "x = 1\n")
    write_source(tmp_path, ".uml-viewer/dryer/src/b.py", "x = 1\n")
    options = parse_args(["--root", str(tmp_path)])
    files = [path.relative_to(tmp_path).as_posix() for path in select_files(options)]
    assert files == ["src/a.py"]


def test_test_files_and_skipped_directories_are_left_out(tmp_path):
    write_source(tmp_path, "src/app.py", "x = 1\n")
    write_source(tmp_path, "src/foo_test.py", "x = 1\n")
    write_source(tmp_path, "target/app.py", "x = 1\n")
    write_source(tmp_path, "tests/app.py", "x = 1\n")
    relative = [path.relative_to(tmp_path).as_posix() for path in iter_source_files([tmp_path])]
    assert relative == ["src/app.py"]


def test_a_second_report_replaces_the_snapshot(tmp_path, capsys):
    write_source(tmp_path, "one.py", "def alpha(xs):\n    return xs\n")
    args = ["--root", str(tmp_path), "--min-lines", "1", "--min-nodes", "1"]
    assert run(args) == 0
    assert run(args) == 0
    assert (tmp_path / ".metrics" / "dry.edn").read_text(encoding="utf-8") == "{:candidates []}\n"


def test_lua_fixture_reports_the_copied_function(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    project = tmp_path / "lua_project"
    shutil.copytree(Path(__file__).parent / "fixtures" / "lua_project", project)
    monkeypatch.chdir(project)
    run([])
    snapshot = (project / ".metrics" / "dry.edn").read_text(encoding="utf-8")
    assert ':language "lua"' in snapshot
    assert ':left {:file "src/calc/init.lua", :start-line 14, :end-line 20}' in snapshot
    assert ':right {:file "src/calc/stats.lua", :start-line 5, :end-line 11}' in snapshot


ALPHA = "def alpha(xs):\n    ys = filter(xs, odd)\n    zs = map(ys, inc)\n    return list(zs)\n"
BETA = "def beta(items):\n    kept = filter(items, even)\n    out = map(kept, dec)\n    return list(out)\n"
SMALL = ["--min-lines", "3", "--min-nodes", "1"]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def git_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.email", "dryer@example.com")
    git(root, "config", "user.name", "dryer")


def test_run_reports_a_missing_crapper_as_a_usage_error(monkeypatch, capsys):
    def missing():
        raise ImportError("crapper not found")

    monkeypatch.setattr("dryer.cli.ensure_crapper", missing)
    assert run(["src"]) == 1
    assert capsys.readouterr().err == "crapper not found\n"


def test_help_works_without_crapper(monkeypatch, capsys):
    def missing():
        raise ImportError("crapper not found")

    monkeypatch.setattr("dryer.cli.ensure_crapper", missing)
    assert run(["--help"]) == 0
    assert capsys.readouterr().out == HELP


def test_selection_follows_crapper_and_adds_cljd(tmp_path, monkeypatch):
    crapper = ensure_crapper()
    monkeypatch.setattr(crapper.discover, "SKIP_DIRS", crapper.discover.SKIP_DIRS | {"gen"})
    for name in ["src/a.py", "src/b.cljd", "src/b_test.cljd", "src/c.clj", "gen/d.py", "spec/e.lua", "src/f_spec.lua"]:
        write_source(tmp_path, name, "x = 1\n")
    ours = iter_source_files([tmp_path])
    theirs = crapper.discover.iter_source_files([tmp_path])
    assert [path for path in ours if path.suffix != ".cljd"] == theirs
    assert [path.relative_to(tmp_path).as_posix() for path in ours] == ["src/a.py", "src/b.cljd", "src/c.clj"]


def test_a_named_file_is_walked_as_is(tmp_path):
    write_source(tmp_path, "notes.md", "x\n")
    assert iter_source_files([tmp_path / "notes.md"]) == [(tmp_path / "notes.md").resolve()]
    assert iter_source_files([tmp_path / "missing"]) == []


def test_cljd_is_clojure_source_and_its_tests_are_tests():
    assert is_source_file(Path("src/app/core.cljd"))
    assert not is_source_file(Path("src/app/core_test.cljd"))
    assert not is_source_file(Path("README.md"))
    assert not is_source_file(Path("src/app_spec.lua"))
    assert is_test_file("src/app_spec.lua")
    assert not is_test_file("src/app.cljd")


def test_changed_finds_new_directories_under_a_subdirectory_root(tmp_path, capsys):
    git_repo(tmp_path)
    write_source(tmp_path, "sub/old.py", "x = 1\n")
    write_source(tmp_path, "sub/gone.py", "x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "sub/gone.py").unlink()
    write_source(tmp_path, "sub/fresh/a b.py", ALPHA)
    write_source(tmp_path, "sub/fresh/b.cljd", "(ns b)\n")
    write_source(tmp_path, "sub/fresh/c.py", BETA)
    write_source(tmp_path, "sub/fresh/test_c.py", BETA)
    write_source(tmp_path, "other/d.py", ALPHA)
    options = parse_args(["--root", str(tmp_path / "sub"), "--changed"])
    files = [path.relative_to(tmp_path).as_posix() for path in select_files(options)]
    assert files == ["sub/fresh/a b.py", "sub/fresh/b.cljd", "sub/fresh/c.py"]
    assert run(["--root", str(tmp_path / "sub"), "--changed", *SMALL]) == 0
    assert "fresh/a b.py:1-4\n  fresh/c.py:1-4" in capsys.readouterr().out


def test_changed_reports_git_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LC_ALL", "C")
    assert run(["--root", str(tmp_path), "--changed"]) == 0
    captured = capsys.readouterr()
    assert "not a git repository" in captured.err
    assert captured.out == "No source files to analyze.\n"


def test_exclude_filters_the_walk_and_source_roots(tmp_path):
    for name in ["src/a.py", "src/gen/b.py", "src/deep/gen/c.py", "lib/d.py", "lib/e.py"]:
        write_source(tmp_path, name, "x = 1\n")

    def chosen(*args):
        options = parse_args(["--root", str(tmp_path), *args])
        return [path.relative_to(tmp_path).as_posix() for path in select_files(options)]

    assert chosen("--exclude", "src/**/gen", "--exclude", "./lib/e.py") == ["lib/d.py", "src/a.py"]
    assert chosen("-s", "src", "--exclude", "src/gen/") == ["src/a.py", "src/deep/gen/c.py"]
    assert chosen("src", "--exclude", "src/*/gen") == ["src/a.py", "src/gen/b.py"]
    assert chosen("--exclude", "SRC") == ["lib/d.py", "lib/e.py", "src/a.py", "src/deep/gen/c.py", "src/gen/b.py"]


def test_exclude_filters_changed_files(tmp_path):
    git_repo(tmp_path)
    write_source(tmp_path, "src/a.py", "x = 1\n")
    write_source(tmp_path, "src/gen/b.py", "x = 1\n")
    options = parse_args(["--root", str(tmp_path), "--changed", "--exclude", "src\\gen"])
    assert [path.relative_to(tmp_path).as_posix() for path in select_files(options)] == ["src/a.py"]


def test_an_excluded_file_named_explicitly_is_skipped(tmp_path, capsys):
    write_source(tmp_path, "src/gen/a.py", ALPHA)
    write_source(tmp_path, "src/b.py", BETA)
    args = ["--root", str(tmp_path), "--exclude", "src/gen", "src/gen/a.py", "src/b.py"]
    options = parse_args(args)
    assert [path.relative_to(tmp_path).as_posix() for path in select_files(options)] == ["src/b.py"]
    assert capsys.readouterr().err == "Skipping excluded src/gen/a.py\n"


def test_an_exclusion_outside_the_project_is_a_usage_error(tmp_path, capsys):
    for pattern in ["/abs", "src/../x"]:
        assert run(["--root", str(tmp_path), "--exclude", pattern]) == 1
        message = f"--exclude must be a path or glob inside the project root: {pattern}\n\n{HELP}"
        assert capsys.readouterr().err == message
    assert not (tmp_path / ".metrics").exists()


def test_exclude_needs_a_value(capsys):
    assert run(["--exclude"]) == 1
    assert "--exclude requires a value" in capsys.readouterr().err


def test_exclude_is_in_the_help():
    assert "--exclude <glob>" in HELP


def test_source_roots_and_exclusions_select_what_crapper_selects(tmp_path):
    ensure_crapper()
    import crapper.cli
    names = ["core.py", "build/helper.py", "testdata/fx.py", "test_dup.py", "gen/g.py"]
    for name in names:
        write_source(tmp_path, f"src/demo/{name}", "x = 1\n")
    scope = ["--root", str(tmp_path), "-s", "src", "--exclude", "src/demo/gen"]
    ours = select_files(parse_args(scope))
    assert ours == crapper.cli.select_files(crapper.cli.parse_args(scope))
    assert [path.relative_to(tmp_path).as_posix() for path in ours] == ["src/demo/core.py"]
    listed = select_files(parse_args(["--root", str(tmp_path), *(f"src/demo/{name}" for name in names[:4])]))
    assert len(listed) == 4


def _scope_tree(root: Path) -> None:
    for name in ("src/a.py", "src/x/c.py", "lib/b.py"):
        write_source(root, name, "x = 1\n")


def _chosen(root: Path, *args: str) -> list[str]:
    files = select_files(parse_args(["--root", str(root), *args]))
    return [path.relative_to(root.resolve()).as_posix() for path in files]


def test_source_roots_narrow_changed_files(tmp_path, capsys):
    git_repo(tmp_path)
    _scope_tree(tmp_path)
    assert _chosen(tmp_path, "-s", "src", "--changed") == ["src/a.py", "src/x/c.py"]
    assert _chosen(tmp_path, "--changed", "-s", "src/x", "-s", "lib") == ["lib/b.py", "src/x/c.py"]
    assert capsys.readouterr().err == ""


def test_a_named_file_outside_the_source_roots_is_skipped_with_a_message(tmp_path, capsys):
    _scope_tree(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-elsewhere.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    assert _chosen(tmp_path, "-s", "src", "lib/b.py", str(outside)) == []
    assert capsys.readouterr().err == (
        "Skipping lib/b.py; it is outside the source roots\n"
        f"Skipping {outside.resolve().as_posix()}; it is outside the source roots\n"
    )


def test_a_named_directory_keeps_only_files_under_the_source_roots(tmp_path, capsys):
    _scope_tree(tmp_path)
    assert _chosen(tmp_path, "-s", "src", ".") == ["src/a.py", "src/x/c.py"]
    assert _chosen(tmp_path, "-s", "src/x", "-s", "lib", "src") == ["src/x/c.py"]
    assert capsys.readouterr().err == ""


def test_a_named_file_inside_a_source_root_is_all_that_is_chosen(tmp_path, capsys):
    _scope_tree(tmp_path)
    assert _chosen(tmp_path, "-s", "src", "src/a.py") == ["src/a.py"]
    assert _chosen(tmp_path, "-s", "src/a.py", "src") == ["src/a.py"]
    assert capsys.readouterr().err == ""


def test_source_roots_alone_still_walk_the_roots_then_filter_and_exclude(tmp_path):
    _scope_tree(tmp_path)
    assert _chosen(tmp_path, "-s", "src") == ["src/a.py", "src/x/c.py"]
    assert _chosen(tmp_path, "-s", "src", "c.py") == ["src/x/c.py"]
    assert _chosen(tmp_path, "-s", "src", "--exclude", "src/x") == ["src/a.py"]
    assert _chosen(tmp_path, "-s", "src", "src", "--exclude", "src/x") == ["src/a.py"]


def test_help_says_source_roots_narrow_paths_and_changed():
    assert "outside the source roots" in HELP
