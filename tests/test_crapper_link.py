import sys
from pathlib import Path

import pytest

from dryer import crapper_link
from dryer.crapper_link import ensure_crapper


def test_the_sibling_checkout_is_next_to_dryer():
    dryer = Path(__file__).resolve().parents[1]
    assert crapper_link._sibling_src() == dryer.parent / "crapper" / "src"


def test_crapper_is_loaded_with_the_modules_dryer_uses():
    crapper = ensure_crapper()
    assert crapper.discover.changed_files
    assert crapper.languages.functions_in_file
    assert crapper.model.Function


def test_a_missing_crapper_names_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "crapper", None)
    monkeypatch.setattr(crapper_link, "_sibling_src", lambda: tmp_path / "src")
    with pytest.raises(ImportError) as raised:
        ensure_crapper()
    assert str(raised.value) == (
        f"crapper is not installed and was not found at {tmp_path / 'src'}. "
        "Clone github.com/unclebob/crapper next to dryer."
    )
    assert raised.value.__suppress_context__


def test_an_older_crapper_names_what_it_lacks(monkeypatch):
    crapper = ensure_crapper()
    monkeypatch.delattr(crapper.discover, "changed_files")
    monkeypatch.delattr(crapper.discover, "excluded")
    with pytest.raises(ImportError) as raised:
        ensure_crapper()
    assert str(raised.value) == (
        f"crapper at {Path(crapper.__file__).parent} is too old for dryer: it has no "
        "crapper.discover.changed_files, crapper.discover.excluded. Update that checkout."
    )


def test_a_crapper_without_source_root_scoping_is_too_old(monkeypatch):
    crapper = ensure_crapper()
    monkeypatch.delattr(crapper.discover, "under_roots", raising=False)
    with pytest.raises(ImportError) as raised:
        ensure_crapper()
    assert "it has no crapper.discover.under_roots." in str(raised.value)
