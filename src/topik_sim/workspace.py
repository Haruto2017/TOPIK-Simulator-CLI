"""First-run workspace setup: import the bundled exam packs.

The repo ships source packs under ``content/source``. ``setup_workspace``
imports each one into the versioned library exactly once: packs whose
id@version is already imported are skipped (never clobbered), and invalid
packs are reported instead of aborting the whole setup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .content import ContentValidationError, load_pack
from .library import DEFAULT_LIBRARY_DIR, find_manifest_entry, import_pack, load_manifest


DEFAULT_SOURCE_DIR = Path("content") / "source"


def bundled_pack_paths(source_dir: str | Path = DEFAULT_SOURCE_DIR) -> list[Path]:
    """The bundled pack files shipped with the workspace, in stable order."""
    directory = Path(source_dir)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def setup_workspace(
    library_dir: str | Path = DEFAULT_LIBRARY_DIR,
    source_dir: str | Path = DEFAULT_SOURCE_DIR,
) -> dict[str, Any]:
    """Import every bundled pack into the library, idempotently.

    Never raises for a bad pack: failures are collected with their errors so
    one broken file cannot block the rest of the onboarding.
    """
    imported: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, Any]] = []

    for path in bundled_pack_paths(source_dir):
        try:
            pack = load_pack(path)
            version = str(pack.data["pack_version"])
            ref = f"{pack.pack_id}@{version}"
            manifest = load_manifest(Path(library_dir))
            if find_manifest_entry(manifest, pack.pack_id, version):
                skipped.append(ref)
                continue
            import_pack(path, library_dir)
            imported.append(ref)
        except ContentValidationError as exc:
            failed.append({"path": str(path), "errors": list(exc.errors)})
        except (OSError, ValueError) as exc:  # also corrupt manifests and JSON decode errors
            failed.append({"path": str(path), "errors": [str(exc)]})

    return {
        "library_dir": str(library_dir),
        "source_dir": str(source_dir),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "counts": {
            "imported": len(imported),
            "skipped": len(skipped),
            "failed": len(failed),
            "total": len(imported) + len(skipped) + len(failed),
        },
    }


def format_setup_summary(result: dict[str, Any]) -> list[str]:
    """Human-readable lines for the CLI and the shell first-run prompt."""
    counts = result["counts"]
    if counts["total"] == 0:
        return [f"No bundled packs found under {result['source_dir']}."]

    lines: list[str] = []
    for ref in result["imported"]:
        lines.append(f"Imported {ref}")
    for ref in result["skipped"]:
        lines.append(f"Skipped {ref} (already imported)")
    for failure in result["failed"]:
        lines.append(f"Failed {failure['path']}:")
        lines.extend(f"  - {error}" for error in failure["errors"])
    lines.append(
        f"Setup: {counts['imported']} imported, {counts['skipped']} skipped,"
        f" {counts['failed']} failed -> library {result['library_dir']}"
    )
    return lines
