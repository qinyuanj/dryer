import sys
import threading
import time
from pathlib import Path

import pytest

from dryer import platform
from dryer.platform import platform_warning, publish, read_source


def test_the_cli_runs_when_the_host_is_windows(tmp_path, monkeypatch, capsys):
    """A Windows host runs, whatever its build: no build number is read at all.

    The body forces `sys.platform`, which is the decision the CLI makes, and
    touches no build, so this says the same thing on a Windows 11 host as on a
    Windows 10 one. It is not a statement about the machine running it.
    """

    from dryer.cli import run

    monkeypatch.setattr("dryer.cli.sys.platform", "win32")
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
