from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content import SCHEMA_VERSION, ExamPack, load_pack


LIBRARY_SCHEMA_VERSION = "topik-sim.library.v1"
DEFAULT_LIBRARY_DIR = Path("content") / "library"


def import_pack(pack_path: str | Path, library_dir: str | Path = DEFAULT_LIBRARY_DIR, replace: bool = False) -> dict[str, Any]:
    pack = load_pack(pack_path)
    library_path = Path(library_dir)
    manifest = load_manifest(library_path)

    pack_id = pack.pack_id
    pack_version = str(pack.data["pack_version"])
    rel_path = Path("packs") / pack_id / f"{pack_version}.json"
    destination = library_path / rel_path
    # Defense in depth behind the contract's slug validation: never write
    # outside the library even if a hostile pack slips past validation.
    library_root = library_path.resolve()
    if not destination.resolve().is_relative_to(library_root):
        raise ValueError(f"Pack id/version {pack_id!r}@{pack_version!r} escapes the library directory.")

    existing = find_manifest_entry(manifest, pack_id, pack_version)
    if existing and not replace:
        raise ValueError(f"Pack {pack_id}@{pack_version} is already imported.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pack.path, destination)
    checksum = checksum_file(destination)
    entry = build_manifest_entry(pack, rel_path, checksum)

    manifest["packs"] = [
        item
        for item in manifest["packs"]
        if not (item["pack_id"] == pack_id and item["pack_version"] == pack_version)
    ]
    manifest["packs"].append(entry)
    manifest["packs"].sort(key=lambda item: (item["pack_id"], version_key(item["pack_version"])))
    write_manifest(library_path, manifest)
    return {**entry, "path": str(destination)}


def load_pack_ref(pack_ref: str, library_dir: str | Path = DEFAULT_LIBRARY_DIR) -> ExamPack:
    library_path = Path(library_dir)
    manifest = load_manifest(library_path)
    pack_id, pack_version = parse_pack_ref(pack_ref)
    matches = [item for item in manifest["packs"] if item["pack_id"] == pack_id]
    if pack_version:
        matches = [item for item in matches if item["pack_version"] == pack_version]
    if not matches:
        raise ValueError(f"Pack reference {pack_ref!r} was not found in the library.")

    entry = sorted(matches, key=lambda item: version_key(item["pack_version"]))[-1]
    return load_pack(library_path / entry["relative_path"])


def list_packs(library_dir: str | Path = DEFAULT_LIBRARY_DIR, include_hidden: bool = False) -> list[dict[str, Any]]:
    manifest = load_manifest(Path(library_dir))
    packs = list(manifest["packs"])
    if include_hidden:
        return packs
    return [entry for entry in packs if not entry.get("hidden")]


def latest_packs(library_dir: str | Path = DEFAULT_LIBRARY_DIR, include_hidden: bool = False) -> list[dict[str, Any]]:
    """One manifest entry per pack_id: the newest imported version."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in list_packs(library_dir, include_hidden=include_hidden):
        pack_id = str(entry.get("pack_id", ""))
        current = latest.get(pack_id)
        if current is None or version_key(str(entry.get("pack_version", ""))) >= version_key(str(current.get("pack_version", ""))):
            latest[pack_id] = entry
    return sorted(latest.values(), key=lambda entry: str(entry.get("pack_id", "")))


def set_pack_hidden(pack_id: str, hidden: bool, library_dir: str | Path = DEFAULT_LIBRARY_DIR) -> int:
    """Hide or unhide every version of a pack. Hidden packs vanish from
    pickers and practice pools but stay loadable by pinned ref."""
    library_path = Path(library_dir)
    manifest = load_manifest(library_path)
    changed = 0
    for entry in manifest["packs"]:
        if entry.get("pack_id") != pack_id:
            continue
        if hidden:
            entry["hidden"] = True
        else:
            entry.pop("hidden", None)
        changed += 1
    if changed == 0:
        raise ValueError(f"Pack {pack_id!r} was not found in the library.")
    write_manifest(library_path, manifest)
    return changed


def validate_library(library_dir: str | Path = DEFAULT_LIBRARY_DIR) -> list[str]:
    library_path = Path(library_dir)
    manifest = load_manifest(library_path)
    errors: list[str] = []
    if manifest.get("schema_version") != LIBRARY_SCHEMA_VERSION:
        errors.append(f"manifest.schema_version must be {LIBRARY_SCHEMA_VERSION!r}.")
    if not isinstance(manifest.get("packs"), list):
        return errors + ["manifest.packs must be an array."]

    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(manifest["packs"]):
        entry_path = f"packs[{index}]"
        for field in ["pack_id", "pack_version", "relative_path", "checksum_sha256"]:
            if field not in entry:
                errors.append(f"{entry_path}.{field} is required.")
        key = (str(entry.get("pack_id")), str(entry.get("pack_version")))
        if key in seen:
            errors.append(f"{entry_path} duplicates {key[0]}@{key[1]}.")
        seen.add(key)

        if "relative_path" not in entry:
            continue
        pack_path = library_path / entry["relative_path"]
        if not pack_path.exists():
            errors.append(f"{entry_path}.relative_path does not exist: {entry['relative_path']}")
            continue
        if checksum_file(pack_path) != entry.get("checksum_sha256"):
            errors.append(f"{entry_path}.checksum_sha256 does not match file contents.")
        try:
            pack = load_pack(pack_path)
        except Exception as exc:
            errors.append(f"{entry_path}.relative_path is not a valid content pack: {exc}")
            continue
        if pack.pack_id != entry.get("pack_id"):
            errors.append(f"{entry_path}.pack_id does not match imported pack.")
        if str(pack.data["pack_version"]) != entry.get("pack_version"):
            errors.append(f"{entry_path}.pack_version does not match imported pack.")

    return errors


def load_manifest(library_dir: Path) -> dict[str, Any]:
    manifest_path = library_dir / "manifest.json"
    if not manifest_path.exists():
        return {"schema_version": LIBRARY_SCHEMA_VERSION, "content_schema_version": SCHEMA_VERSION, "packs": []}
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest.setdefault("packs", [])
    return manifest


def write_manifest(library_dir: Path, manifest: dict[str, Any]) -> None:
    library_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = library_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def find_manifest_entry(manifest: dict[str, Any], pack_id: str, pack_version: str) -> dict[str, Any] | None:
    for entry in manifest["packs"]:
        if entry["pack_id"] == pack_id and entry["pack_version"] == pack_version:
            return entry
    return None


def build_manifest_entry(pack: ExamPack, relative_path: Path, checksum: str) -> dict[str, Any]:
    questions = pack.questions()
    entry = {
        "pack_id": pack.pack_id,
        "pack_version": str(pack.data["pack_version"]),
        "title": pack.title,
        "topik_level": str(pack.data["topik_level"]),
        "question_count": len(questions),
        "relative_path": relative_path.as_posix(),
        "checksum_sha256": checksum,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    difficulty = str(pack.data.get("difficulty", "") or "").strip()
    if difficulty:
        entry["difficulty"] = difficulty
    return entry


def parse_pack_ref(pack_ref: str) -> tuple[str, str | None]:
    if "@" not in pack_ref:
        return pack_ref, None
    pack_id, pack_version = pack_ref.rsplit("@", 1)
    return pack_id, pack_version


def version_key(version: str) -> tuple[Any, ...]:
    parts: list[Any] = []
    for part in version.replace("-", ".").split("."):
        parts.append(int(part) if part.isdigit() else part)
    return tuple(parts)


def checksum_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
