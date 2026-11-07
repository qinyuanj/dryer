import sys
import threading
import time
from pathlib import Path

import pytest

from dryer import platform
from dryer.platform import MIN_WINDOWS_BUILD, platform_refusal, platform_warning, publish, read_source


# Declared platform/version fixtures: each row is a host dryer may run on.
@pytest.mark.parametrize(
    ("host", "build"),
    [
        ("linux", None),
        ("win32", 19045),  # Windows 10 22H2
        ("win32", 22000),  # Windows 11 21H2
        ("win32", 26220),  # Windows 11 (the acceptance host)
    ],
)
def test_supported_hosts_run(host, build):
    assert platform_refusal(host, build) is None


@pytest.mark.parametrize("build", [10240, 17763, 19041, 19044])
def test_older_windows_is_refused_naming_the_minimum_build(build):
    message = platform_refusal("win32", build)
    assert message == (
        f"dryer needs Windows 10 22H2 (build 19045) or later; this is build {build}. "
        "Update Windows, or run dryer inside WSL2; see the README."
    )


def test_the_minimum_build_is_windows_10_22h2():
    assert MIN_WINDOWS_BUILD == 19045


def test_the_cli_refuses_an_old_windows_build_before_scanning(tmp_path, monkeypatch, capsys):
    from dryer.cli import run

    monkeypatch.setattr("dryer.cli.sys.platform", "win32")
    monkeypatch.setattr("dryer.cli.windows_build", lambda: 19044)
    assert run(["--root", str(tmp_path)]) == 1
    assert "build 19045" in capsys.readouterr().err
    assert not (tmp_path / ".metrics").exists()


def test_the_cli_runs_on_a_supported_windows_build(tmp_path, monkeypatch, capsys):
    from dryer.cli import run

    monkeypatch.setattr("dryer.cli.sys.platform", "win32")
    monkeypatch.setattr("dryer.cli.windows_build", lambda: 19045)
    assert run(["--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "No source files to analyze.\n"
    assert captured.err == ""


def test_windows_drive_under_wsl_suggests_the_linux_filesystem():
    assert "under ~/" in platform_warning("linux", Path("/mnt/c/proj"))


def test_linux_filesystem_paths_are_quiet():
    assert platform_warning("linux", Path("/home/me/proj")) is None


def test_native_windows_paths_are_quiet():
    assert platform_warning("win32", Path("C:/Users/me/proj")) is None


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_source_is_read_with_universal_newlines(tmp_path, newline):
    path = tmp_path / "a.py"
    path.write_bytes(newline.join(["def a():", "    return 1", ""]).encode("utf-8"))
    assert read_source(path) == "def a():\n    return 1\n"


def test_publish_writes_lf_bytes(tmp_path):
    path = tmp_path / "dry.edn"
    publish(path, "{:candidates [\n]}\n")
    assert path.read_bytes() == b"{:candidates [\n]}\n"
    assert [p.name for p in tmp_path.iterdir()] == ["dry.edn"]


def _sharing_violation() -> OSError:
    error = PermissionError(13, "The process cannot access the file")
    error.winerror = 32
    return error


def test_publish_retries_a_transient_sharing_violation(tmp_path, monkeypatch):
    real = platform.os.replace
    failures = [_sharing_violation(), _sharing_violation()]

    def flaky(src, dst):
        if failures:
            raise failures.pop()
        real(src, dst)

    monkeypatch.setattr(platform.os, "replace", flaky)
    monkeypatch.setattr(platform.time, "sleep", lambda seconds: None)
    path = tmp_path / "dry.edn"
    publish(path, "new\n")
    assert path.read_bytes() == b"new\n"
    assert failures == []


def test_publish_gives_up_on_other_errors_and_leaves_no_temp_file(tmp_path, monkeypatch):
    def broken(src, dst):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(platform.os, "replace", broken)
    path = tmp_path / "dry.edn"
    with pytest.raises(PermissionError):
        publish(path, "new\n")
    assert list(tmp_path.iterdir()) == []


def test_publish_gives_up_when_the_sharing_violation_persists(tmp_path, monkeypatch):
    calls = []

    def stuck(src, dst):
        calls.append(dst)
        raise _sharing_violation()

    monkeypatch.setattr(platform.os, "replace", stuck)
    monkeypatch.setattr(platform.time, "sleep", lambda seconds: None)
    with pytest.raises(PermissionError):
        publish(tmp_path / "dry.edn", "new\n")
    assert len(calls) == platform.REPLACE_ATTEMPTS
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace a file another handle holds open")
def test_publish_waits_for_a_reader_holding_the_snapshot_open(tmp_path):
    path = tmp_path / "dry.edn"
    path.write_bytes(b"old\n")
    reader = open(path, "rb")
    threading.Thread(target=lambda: (time.sleep(0.2), reader.close()), daemon=True).start()
    publish(path, "new\n")
    assert path.read_bytes() == b"new\n"
