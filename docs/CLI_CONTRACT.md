# CLI Contract

All commands are run from the repository root.

If the package is not installed, set `PYTHONPATH=src` first.

## `validate-content`

Validates a content pack.

```powershell
python -m topik_sim validate-content <pack.json>
```

Exit behavior:

- `0`: pack is valid.
- Non-zero: pack is invalid; errors are printed.

## `inspect-content`

Prints pack metadata and section/question counts.

```powershell
python -m topik_sim inspect-content <pack.json>
```

## `simulate`

Runs an interactive exam simulation in the terminal.

```powershell
python -m topik_sim simulate <pack.json> [--section <section_id>] [--limit <n>] [--show-teaching]
```

Behavior:

- Presents questions in pack order.
- Prompts for an answer.
- Grades each answer.
- Prints a final score.
- Prints teaching notes for missed questions by default.
- `--show-teaching` also prints teaching notes for correct answers.

## `take`

Runs an interactive test and saves the attempt after each answer.

```powershell
python -m topik_sim take <pack.json-or-pack_ref> [--library <library_dir>] [--attempt-dir <attempt_dir>] [--section <section_id>] [--limit <n>] [--show-teaching]
```

Pack references:

- A direct JSON path, such as `examples/content/topik_i_mini_pack.json`.
- A library pack ID, such as `topik-i-mini-pack`.
- A pinned library pack ID and version, such as `topik-i-mini-pack@0.1.0`.

Default runtime locations:

- Library: `content/library`
- Attempts: `data/attempts`

## `review-attempt`

Prints the score and item-level feedback from a saved attempt.

```powershell
python -m topik_sim review-attempt data/attempts/<attempt_id>.json
```

## `grade`

Grades an answer file without interaction.

```powershell
python -m topik_sim grade <pack.json> <answers.json>
```

Accepted answer file shapes:

```json
{
  "answers": [
    { "question_id": "r-001", "response": "B" }
  ]
}
```

## `import-pack`

Validates and imports a content pack into the versioned library.

```powershell
python -m topik_sim import-pack <pack.json> [--library <library_dir>] [--replace]
```

Behavior:

- Copies the source pack to `packs/<pack_id>/<pack_version>.json`.
- Records metadata in `manifest.json`.
- Records a SHA-256 checksum for integrity checks.
- Rejects duplicate `pack_id@pack_version` imports unless `--replace` is used.

## `list-packs`

Lists packs currently imported into the content library.

```powershell
python -m topik_sim list-packs [--library <library_dir>]
```

## `validate-library`

Validates the library manifest, imported pack files, and recorded checksums.

```powershell
python -m topik_sim validate-library [--library <library_dir>]
```

or:

```json
{
  "r-001": "B"
}
```

Output shape:

```json
{
  "pack_id": "topik-i-mini",
  "score": 1,
  "max_score": 2,
  "results": [
    {
      "question_id": "r-001",
      "correct": true,
      "points_awarded": 1,
      "max_points": 1,
      "response": "B",
      "feedback": {
        "summary": "...",
        "teaching_points": []
      }
    }
  ]
}
```
