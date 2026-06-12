# Content Contract

Content packs are JSON files. The current schema version is:

```json
"topik-sim.content.v1"
```

## Pack Shape

```json
{
  "schema_version": "topik-sim.content.v1",
  "pack_id": "topik-i-reading-set-001",
  "pack_version": "0.1.0",
  "title": "TOPIK I Reading Set 001",
  "topik_level": "TOPIK_I",
  "language_pair": "ko-en",
  "source_type": "original",
  "sections": []
}
```

Required pack fields:

- `schema_version`
- `pack_id`: a slug of lowercase letters, digits, hyphens, or underscores (it becomes a directory name in the library)
- `pack_version`: semantic content version for import and reproducibility; letters, digits, dots, and hyphens only
- `title`
- `topik_level`: `TOPIK_I` or `TOPIK_II`
- `language_pair`
- `source_type`: `original`, `licensed`, `public_domain`, or `user_provided`
- `sections`

Optional pack fields:

- `difficulty`: a free-text label shown wherever packs are listed or picked, e.g. `"authentic"`, `"starter (English options)"`, `"level 3-4"`. Use it so learners can tell exam tiers apart at a glance; it is recorded in the library manifest at import.

## Section Shape

```json
{
  "section_id": "reading",
  "title": "Reading",
  "time_limit_minutes": 70,
  "questions": []
}
```

Required section fields:

- `section_id`
- `title`
- `questions`

Optional section fields:

- `time_limit_minutes`
- `instructions`

## Question Shape

```json
{
  "question_id": "r-001",
  "order": 1,
  "skill": "reading",
  "prompt": "Choose the best answer.",
  "passage": "오늘은 날씨가 좋습니다.",
  "options": [
    { "id": "A", "text": "It is raining today." },
    { "id": "B", "text": "The weather is good today." }
  ],
  "answer": {
    "type": "single_choice",
    "correct_option_id": "B"
  },
  "points": 1,
  "explanation": {
    "summary": "The sentence says the weather is good today.",
    "teaching_points": [
      "좋다 means to be good."
    ],
    "vocabulary": [
      { "ko": "날씨", "en": "weather" }
    ],
    "grammar": [
      {
        "pattern": "-습니다",
        "explanation": "Formal polite declarative ending.",
        "example": "날씨가 좋습니다."
      }
    ],
    "common_mistakes": [
      "Do not confuse 좋다 with 춥다."
    ]
  }
}
```

Required question fields:

- `question_id`
- `order`
- `skill`
- `prompt`
- `answer`
- `explanation`

Optional question fields:

- `passage`
- `audio_ref`
- `image_ref`
- `options`
- `points`
- `tags`
- `difficulty`

## Supported Answer Types

### Single Choice

```json
{
  "type": "single_choice",
  "correct_option_id": "B"
}
```

Requirements:

- `options` must be present.
- `correct_option_id` must match one option `id`.

### Short Answer

```json
{
  "type": "short_answer",
  "accepted_answers": ["학생", "student"]
}
```

The current grader accepts exact normalized matches. Later versions can add rubric-based grading.

### Multiple Select

```json
{
  "type": "multiple_select",
  "correct_option_ids": ["A", "C"]
}
```

Requirements:

- `options` must be present.
- Every entry in `correct_option_ids` must match an option `id`.
- Learners answer with all correct ids in any order, e.g. `A,C` or `c a`.

### Ordering

```json
{
  "type": "ordering",
  "correct_order": ["B", "C", "A"]
}
```

Requirements:

- At least two `options`.
- `correct_order` lists option ids in the right sequence without repeats.
- Learners answer with the sequence, e.g. `B,C,A`.

### Cloze

```json
{
  "type": "cloze",
  "blanks": [
    { "accepted_answers": ["에"] },
    { "accepted_answers": ["에서"] }
  ]
}
```

Requirements:

- One entry per blank, in passage order; each blank needs at least one accepted answer.
- Learners separate multiple blanks with `/` (also `;` or `|`), e.g. `에 / 에서`.
- Grading is all-or-nothing per question; use one blank per question for partial-credit granularity.

### Essay (manual review)

```json
{
  "type": "essay",
  "rubric": {
    "criteria": [
      { "name": "content", "max_points": 2 },
      { "name": "grammar", "max_points": 2 }
    ]
  }
}
```

Requirements:

- `rubric.criteria` is non-empty; each criterion has a `name` and a positive integer `max_points`.
- When the question sets `points`, it must equal the rubric total.
- Essays cannot be auto-graded: the attempt records the response with `needs_review`, awards 0 points, and `python -m topik_sim review-writing <attempt.json>` records per-criterion scores afterwards. An essay counts as correct at half marks or better.
- Essays are excluded from drills and the spaced-repetition queue.

`examples/content/topik_i_formats_pack.json` demonstrates every answer type.

## Authoring Rules

- Every `question_id` must be unique within a pack.
- Every question must include an explanation summary.
- Teaching notes should be useful even when the learner answered correctly.
- Use stable IDs because answer files and learner history depend on them.
