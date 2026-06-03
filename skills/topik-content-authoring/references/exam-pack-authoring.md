# Exam Pack Authoring

## Required Pack Fields

- `schema_version`: `topik-sim.content.v1`
- `pack_id`: stable ID, lower-case words separated by hyphens
- `pack_version`: semantic content version, such as `0.1.0`
- `title`: learner-facing title
- `topik_level`: `TOPIK_I` or `TOPIK_II`
- `language_pair`: usually `ko-en`
- `source_type`: `original`, `licensed`, `public_domain`, or `user_provided`
- `sections`: array of sections

## Section Guidance

Use `section_id` values such as:

- `reading`
- `listening`
- `writing`
- `grammar`
- `vocabulary`

Include `time_limit_minutes` when the section is meant to simulate timed exam conditions.

## Question Guidance

Each question needs:

- `question_id`: stable ID, such as `r-001`
- `order`: display order within the pack
- `skill`: reading, listening, writing, grammar, vocabulary, or mixed
- `prompt`: what the learner must do
- `passage`, `audio_ref`, or `image_ref` when relevant
- `answer`
- `points`
- `explanation`

## Supported Answer Types

Use `single_choice` for multiple choice:

```json
{
  "type": "single_choice",
  "correct_option_id": "B"
}
```

Use `short_answer` for exact-match answers:

```json
{
  "type": "short_answer",
  "accepted_answers": ["student", "learner"]
}
```

## Explanation Shape

Every question should include:

- `summary`: direct explanation of the correct answer
- `teaching_points`: short lesson notes
- `vocabulary`: objects with `ko` and `en`
- `grammar`: pattern, explanation, and optional example
- `common_mistakes`: likely learner traps

## Authoring Pattern

For each question, write in this order:

1. Decide the tested skill and learner level.
2. Write original Korean stimulus text or reference user-provided material.
3. Write one clearly correct answer.
4. Write plausible distractors that test real misunderstandings.
5. Add teaching notes that explain why the answer is correct.
6. Add vocabulary and grammar that a learner should review.
7. Validate the pack.

