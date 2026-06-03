# Software-Building Context

Goal: build a TOPIK simulation app that can administer practice exams, grade answers, and teach from submitted answers.

Current phase:

- Establish a stable CLI and content contract.
- Support saved user attempts and a versioned content-loading pipeline.
- Keep implementation dependency-light.
- Make the content workflow safe for a separate session dedicated to questions, answers, and teaching.

Near-term product shape:

- CLI first.
- Later: local web UI or desktop-style interface using the same content and grading APIs.
- Feedback should include correctness, score, explanation, vocabulary, grammar, and study guidance.
- Runtime data should be generated under ignored folders such as `data/` or `content/library/`.

Non-goals for this first phase:

- Real TOPIK copyrighted question import.
- Audio playback engine.
- User account system.
- Advanced natural-language grading.
