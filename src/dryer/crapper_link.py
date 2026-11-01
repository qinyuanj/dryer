"""Import crapper from the environment or the sibling checkout.

File selection and function names come from crapper, so dryer compares the
files crapper and mutator score and `.metrics/dry.edn` joins `.metrics/crap.edn`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _sibling_src() -> Path:
    project = Path(__file__).resolve().parents[2]
    return project.parent / "crapper" / "src"


# Added to crapper with --changed, --exclude, coverage reuse and source-root scoping.
_NEEDS = {"discover": ("changed_files", "exclusion_error", "excluded", "without_excluded", "under_roots")}


def _missing(crapper) -> list[str]:
    return [
        f"crapper.{module}.{name}"
        for module, names in _NEEDS.items()
        for name in names
        if not hasattr(getattr(crapper, module), name)
    ]


def ensure_crapper():
    try:
        import crapper
    except ImportError:
        sibling = _sibling_src()
        if not (sibling / "crapper").is_dir():
            raise ImportError(
                "crapper is not installed and was not found at "
                f"{sibling}. Clone github.com/unclebob/crapper next to dryer."
            ) from None
        sys.path.insert(0, str(sibling))
        import crapper
    import crapper.discover
    import crapper.languages
    import crapper.model

    missing = _missing(crapper)
    if missing:
        raise ImportError(
            f"crapper at {Path(crapper.__file__).parent} is too old for dryer: "
            f"it has no {', '.join(missing)}. Update that checkout."
        )
    return crapper
