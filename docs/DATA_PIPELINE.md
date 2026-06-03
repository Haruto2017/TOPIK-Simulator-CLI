# Data Pipeline

The data pipeline is version-managed so software-building and content-authoring sessions can work independently.

## Source Pack

Content authors create JSON packs that follow `docs/CONTENT_CONTRACT.md`.

Each pack must have:

- `pack_id`: stable logical ID, such as `topik-i-mini-pack`
- `pack_version`: content version, such as `0.1.0`
- `schema_version`: currently `topik-sim.content.v1`

## Validate

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim validate-content examples/content/topik_i_mini_pack.json
```

## Import

```powershell
python -m topik_sim import-pack examples/content/topik_i_mini_pack.json
```

The default library is `content/library`.

Import creates:

- `manifest.json`
- `packs/<pack_id>/<pack_version>.json`
- SHA-256 checksum metadata

Runtime library data is ignored by Git. Source packs remain the editable content files.

## Validate Library

```powershell
python -m topik_sim validate-library
```

This verifies:

- Manifest shape.
- Referenced pack files exist.
- Checksums match.
- Imported packs still pass the content contract.

## Load

Users can take tests by source file path:

```powershell
python -m topik_sim take examples/content/topik_i_mini_pack.json
```

Or by imported library reference:

```powershell
python -m topik_sim take topik-i-mini-pack
python -m topik_sim take topik-i-mini-pack@0.1.0
```

