# Tutorial Authoring

Tutorial content currently lives inside question explanations and teaching notes. Keep tutorials small, reusable, and tied to learner mistakes until the simulator gains a dedicated tutorial schema.

## Tutorial Unit Pattern

For each teaching unit, include:

- Concept name: the grammar pattern, vocabulary family, reading skill, or exam strategy.
- Plain explanation: one or two learner-friendly sentences.
- Example: a Korean example with English meaning when useful.
- Recognition cue: how the learner notices the form in a question.
- Common mistake: what learners often confuse it with.
- Practice bridge: what kind of next question would reinforce it.

## Where To Put Tutorial Material

Use these content fields:

- `explanation.summary`: concise answer rationale.
- `explanation.teaching_points`: mini tutorial bullets.
- `explanation.vocabulary`: focused word list.
- `explanation.grammar`: structured grammar tutorial.
- `explanation.common_mistakes`: diagnostic feedback.
- `tags`: optional concepts for later review features.

## Tone

- Teach directly and kindly.
- Keep explanations short enough for post-question review.
- Prefer concrete examples over abstract terminology.
- Explain distractors when they reveal a useful misconception.

## Future-Proofing

When adding a tutorial-rich pack, add useful `tags` such as:

- `grammar:n-eseo`
- `ending:seumnida`
- `vocab:places`
- `strategy:main-idea`

These tags can later drive review lists, spaced repetition, or tutorial pages without rewriting content.

