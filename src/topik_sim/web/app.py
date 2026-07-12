from __future__ import annotations

"""JSON API over the simulator core, independent of any HTTP plumbing.

``WebApp.handle(method, path, query, body)`` returns ``(status, payload)``
where the payload is a JSON-safe dict, or ``(bytes, content_type)`` for
audio. ``server.py`` bridges this to a stdlib HTTP server; tests drive
``handle`` directly, offline, with a stubbed synthesizer.

Design rules, mirroring the shell:

- Exams run through the same ``ExamSession`` state machine and attempt
  files, so web attempts resume in the CLI and vice versa.
- Question payloads never include the answer or the explanation; those
  arrive only in the answer response. Listening questions withhold the
  transcript while audio is available (``/transcript`` reveals it on
  request, exactly like the shell command).
- Typed practice grades server-side with the shell's rules: NFC normalize,
  whitespace-insensitive, digits rejected when the item says so, option
  numbers accepted for choice items, dictation by diff accuracy.
"""

import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

from .. import __version__

from ..activities import missed_question_ids
from ..attempts import save_attempt_to_dir
from ..content import ContentValidationError, ExamPack, load_pack
from ..grading import grade_question  # noqa: F401  (re-exported for tests)
from ..library import DEFAULT_LIBRARY_DIR, latest_packs, load_pack_ref
from ..session import ExamSession
from ..tts import (
    TTSConfig,
    collect_question_speech_texts,
    is_listening_question,
    transcript_text,
)

_SAFE_NAME = re.compile(r"^[\w.@-]+$")


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip()).replace(" ", "")


def _public_question(question: dict[str, Any], number: int, total: int,
                     audio_parts: int, show_transcript: bool) -> dict[str, Any]:
    listening = is_listening_question(question)
    hide = listening and audio_parts > 0 and not show_transcript
    payload = {
        "question_id": question.get("question_id"),
        "number": number,
        "total": total,
        "skill": question.get("skill"),
        "prompt": question.get("prompt", ""),
        "options": [
            {"id": option.get("id"), "text": option.get("text", "")}
            for option in question.get("options", []) or []
        ],
        "answer_type": (question.get("answer") or {}).get("type", ""),
        "points": question.get("points", 1),
        "listening": listening,
        "transcript_hidden": hide,
        "audio_parts": audio_parts,
    }
    if not hide:
        passage = transcript_text(question) if listening else str(question.get("passage", "") or "")
        if passage:
            payload["passage"] = passage
    return payload


class WebApp:
    def __init__(
        self,
        library_dir: str | Path = DEFAULT_LIBRARY_DIR,
        attempt_dir: str | Path = "data/attempts",
        tts_config: TTSConfig | None = None,
        audio_enabled: bool = True,
        show_transcript: bool = False,
        seed: int | None = None,
        synthesizer: Any = None,
    ) -> None:
        from ..compose import DEFAULT_COMPOSE_PATH
        from ..courses import DEFAULT_COURSES_PATH
        from ..facts import DEFAULT_FACTS_PATH

        self.library_dir = Path(library_dir)
        self.attempt_dir = Path(attempt_dir)
        self.tts_config = tts_config or TTSConfig()
        self.audio_enabled = audio_enabled
        self.show_transcript = show_transcript
        self.seed = seed
        self.courses_path = DEFAULT_COURSES_PATH
        self.facts_path = DEFAULT_FACTS_PATH
        self.compose_path = DEFAULT_COMPOSE_PATH
        self._synthesizer = synthesizer  # tests inject a fake; None = real TTS
        self._activities: dict[str, dict[str, Any]] = {}
        self._next_id = 0
        self._audio_failed = False
        # ThreadingHTTPServer runs requests concurrently; serialize state
        # mutations so a double-click can never submit an answer twice.
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------ plumbing

    def handle(self, method: str, path: str, query: dict[str, str] | None = None,
               body: dict[str, Any] | None = None) -> tuple[int, Any]:
        query = query or {}
        body = body or {}
        method = method.upper()
        try:
            if method == "POST":
                with self._write_lock:
                    return self._route(method, path.rstrip("/") or "/", query, body)
            return self._route(method, path.rstrip("/") or "/", query, body)
        except ApiError as exc:
            return exc.status, {"error": str(exc)}
        except (ValueError, KeyError, OSError, ContentValidationError) as exc:
            return 400, {"error": str(exc)}

    def _route(self, method: str, path: str, query: dict[str, str],
               body: dict[str, Any]) -> tuple[int, Any]:
        parts = [p for p in path.split("/") if p]
        if not parts or parts[0] != "api":
            raise ApiError(404, f"Unknown path: {path}")
        parts = parts[1:]

        if parts == ["state"] and method == "GET":
            return 200, self.state()
        if parts == ["packs"] and method == "GET":
            return 200, {"packs": self.packs()}
        if parts == ["attempts"] and method == "GET":
            return 200, {"attempts": self.attempts()}
        if parts == ["stats"] and method == "GET":
            from ..stats import collect_stats

            return 200, collect_stats(self.attempt_dir, self.library_dir)
        if parts == ["practice", "log"] and method == "GET":
            from ..practice_log import load_practice_log, practice_summary, weak_items

            log = load_practice_log(self.attempt_dir)
            return 200, {
                "runs": list(reversed(log["runs"][-30:])),
                "weak": weak_items(log),
                "summary": practice_summary(log),
            }
        if parts == ["doctor"] and method == "GET":
            from ..doctor import run_checks

            checks = run_checks(library_dir=self.library_dir)
            return 200, {"version": __version__,
                         "checks": [{"status": c[0], "name": c[1], "detail": c[2]} for c in checks]}
        if parts == ["report"] and method == "GET":
            return 200, {"markdown": self.report(query.get("file", ""))}
        if parts == ["tts"]:
            if method == "POST":
                self.update_tts(body)
            return 200, self.tts_state()
        if parts == ["say"] and method == "GET":
            return self._audio_response(query.get("text", ""), slow=query.get("slow") == "1")
        if parts == ["keyboard"] and method == "GET":
            from ..hangul import LAYOUT_ROWS

            rows = [[None if cell is None else {"key": cell[0], "jamo": cell[1], "shift": cell[2]}
                     for cell in row] for row in LAYOUT_ROWS]
            return 200, {"rows": rows}
        if parts == ["hangul"] and method == "GET":
            from ..hangul_guide import guide

            return 200, guide()
        if parts == ["numbers", "guide"] and method == "GET":
            from ..numbers import cheat_sheet

            return 200, cheat_sheet()
        if parts == ["lookup"] and method == "GET":
            from ..lookup import search_library

            return 200, search_library(query.get("q", ""), self.library_dir)

        if parts == ["exam", "start"] and method == "POST":
            return 200, self.start_exam(body)
        if parts == ["exam", "resume"] and method == "POST":
            return 200, self.resume_exam(str(body.get("file", "")))
        if parts == ["exam", "drill"] and method == "POST":
            return 200, self.start_drill_from_attempt(str(body.get("file", "")))
        if parts == ["exam", "review"] and method == "POST":
            return 200, self.start_review(str(body.get("pack", "")))
        if parts == ["exam", "course"] and method == "POST":
            return 200, self.start_course_exam(str(body.get("pack", "")), str(body.get("course_id", "")))
        if parts == ["review", "due"] and method == "GET":
            return 200, {"due": self.review_due()}

        if parts == ["drill", "start"] and method == "POST":
            return 200, self.start_practice(body)

        if parts == ["deck", "flashcards"] and method == "GET":
            from ..flashcards import build_deck

            pack = self._resolve_pack(query.get("pack", ""))
            return 200, {"cards": build_deck(pack, seed=self.seed), "title": pack.title}
        if parts == ["deck", "grammar"] and method == "GET":
            from ..grammar import build_grammar_cards

            pack = self._resolve_pack(query["pack"]) if query.get("pack") else None
            limit = int(query.get("count", 20))
            cards = build_grammar_cards(pack=pack, library_dir=None if pack else self.library_dir,
                                        seed=self.seed, limit=limit)
            return 200, {"cards": cards, "title": pack.title if pack else "every imported pack"}
        if parts == ["compose", "lessons"] and method == "GET":
            from ..compose import filter_lessons, lesson_sentences, load_lessons

            lessons = load_lessons(self.compose_path)
            if query.get("query"):
                lessons = filter_lessons(lessons, query["query"])
            return 200, {"lessons": [
                {"id": lesson.get("id"), "pattern": lesson.get("pattern"),
                 "meaning": lesson.get("meaning"), "example": lesson.get("example"),
                 "example_en": lesson.get("example_en", ""), "note": lesson.get("note", ""),
                 "level": lesson.get("level"), "sentences": lesson_sentences(lesson)}
                for lesson in lessons
            ]}
        if parts == ["facts"] and method == "GET":
            from ..facts import filter_facts, load_facts

            facts = load_facts(self.facts_path)
            if query.get("query"):
                facts = filter_facts(facts, query["query"])
            return 200, {"facts": facts}

        if parts == ["courses"] and method == "GET":
            return 200, {"packs": self.courses()}
        if len(parts) == 3 and parts[:2] == ["courses", "lesson"] and method == "GET":
            return 200, self.course_lesson(query.get("pack", ""), parts[2])

        if len(parts) >= 2 and parts[0] == "activity":
            return self._route_activity(method, parts[1], parts[2:], query, body)

        raise ApiError(404, f"Unknown API path: {path}")

    def _route_activity(self, method: str, activity_id: str, rest: list[str],
                        query: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
        activity = self._activities.get(activity_id)
        if activity is None:
            raise ApiError(404, f"No active session {activity_id}. It may have been paused.")
        if not rest and method == "GET":
            return 200, self.activity_view(activity_id)
        if rest == ["answer"] and method == "POST":
            return 200, self.answer(activity_id, str(body.get("value", "")))
        if rest == ["pause"] and method == "POST":
            return 200, self.pause(activity_id)
        if rest == ["transcript"] and method == "POST":
            return 200, self.reveal_transcript(activity_id)
        if rest == ["hint"] and method == "POST":
            return 200, self.exam_hint(activity_id)
        if rest == ["audio"] and method == "GET":
            return self.activity_audio(activity_id, int(query.get("part", 0)),
                                       slow=query.get("slow") == "1")
        if rest == ["say"] and method == "GET":
            return self.activity_say(activity_id)
        raise ApiError(404, f"Unknown activity action: {'/'.join(rest)}")

    # ------------------------------------------------------------- lookups

    def _resolve_pack(self, ref: str) -> ExamPack:
        if not ref:
            raise ApiError(400, "A pack reference is required.")
        path = Path(ref)
        if path.exists():
            return load_pack(path)
        return load_pack_ref(ref, self.library_dir)

    def _attempt_path(self, name: str) -> Path:
        if not name or not _SAFE_NAME.match(name):
            raise ApiError(400, f"Bad attempt file name: {name!r}")
        path = self.attempt_dir / name
        if not path.exists():
            raise ApiError(404, f"Attempt file not found: {name}")
        return path

    def _register(self, activity: dict[str, Any]) -> str:
        self._next_id += 1
        activity_id = f"a{self._next_id}"
        self._activities[activity_id] = activity
        activity["id"] = activity_id
        return activity_id

    # ------------------------------------------------------------ overview

    def state(self) -> dict[str, Any]:
        from .. import srs
        from ..practice_log import load_practice_log, practice_summary, weak_items

        queue = srs.load_queue(srs.queue_path_for(self.attempt_dir))
        log = load_practice_log(self.attempt_dir)
        return {
            "version": __version__,
            "packs": self.packs(),
            "attempts": self.attempts()[:10],
            "courses": self.courses(),
            "review_due": srs.due_counts_by_pack(queue),
            "practice": {"summary": practice_summary(log), "weak": weak_items(log, limit=10)},
            "tts": self.tts_state(),
        }

    def packs(self) -> list[dict[str, Any]]:
        from ..stats import pack_progress

        try:
            entries = latest_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            entries = []
        progress = pack_progress(self.attempt_dir)
        for entry in entries:
            note = progress.get(entry.get("pack_id"), {})
            entry["progress"] = note
        return entries

    def attempts(self) -> list[dict[str, Any]]:
        results = []
        if not self.attempt_dir.exists():
            return results
        for path in sorted(self.attempt_dir.glob("*.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or "attempt_id" not in data:
                continue  # queue/progress files share the directory
            answered = len(data.get("answers", []))
            total = len(data.get("question_ids", []))
            results.append({
                "file": path.name,
                "attempt_id": data.get("attempt_id"),
                "pack_id": data.get("pack_id"),
                "pack_version": data.get("pack_version"),
                "activity": data.get("activity", "exam"),
                "status": data.get("status"),
                "progress": [answered, total],
                "updated_at": data.get("updated_at"),
            })
        return results

    def tts_state(self) -> dict[str, Any]:
        return {
            "enabled": self.audio_enabled,
            "provider": self.tts_config.provider,
            "volume": self.tts_config.volume,
            "speed": self.tts_config.speed,
            "voice": self.tts_config.speaker_id,
            "failed": self._audio_failed,
        }

    def update_tts(self, body: dict[str, Any]) -> None:
        from dataclasses import replace

        if "enabled" in body:
            self.audio_enabled = bool(body["enabled"])
        changes: dict[str, Any] = {}
        if body.get("volume") is not None:
            volume = float(body["volume"])
            if volume <= 0:
                raise ApiError(400, "volume must be greater than 0")
            changes["volume"] = volume
        if body.get("speed") is not None:
            speed = float(body["speed"])
            if speed <= 0:
                raise ApiError(400, "speed must be greater than 0")
            changes["speed"] = speed
        if body.get("voice"):
            changes["speaker_id"] = str(body["voice"])
        if changes:
            self.tts_config = replace(self.tts_config, **changes)
        self._audio_failed = False  # settings changed; try again

    def report(self, name: str) -> str:
        from ..attempts import load_attempt
        from ..report import build_report

        attempt = load_attempt(self._attempt_path(name))
        pack = self._resolve_pack(f"{attempt['pack_id']}@{attempt['pack_version']}")
        return build_report(attempt, pack)

    # ---------------------------------------------------------------- exams

    def start_exam(self, body: dict[str, Any]) -> dict[str, Any]:
        pack = self._resolve_pack(str(body.get("pack", "")))
        limit = int(body["limit"]) if body.get("limit") else None
        session = ExamSession.start(
            pack, self.attempt_dir,
            section_id=str(body["section"]) if body.get("section") else None,
            limit=limit,
        )
        return self._exam_view(self._register({"kind": "exam", "session": session}))

    def resume_exam(self, name: str) -> dict[str, Any]:
        from ..attempts import load_attempt

        path = self._attempt_path(name)
        attempt = load_attempt(path)
        if attempt.get("status") == "completed":
            raise ApiError(400, "That attempt is already completed — drill it instead.")
        pack = self._resolve_pack(f"{attempt['pack_id']}@{attempt['pack_version']}")
        session = ExamSession.resume(path, pack)
        return self._exam_view(self._register({"kind": "exam", "session": session}))

    def start_drill_from_attempt(self, name: str) -> dict[str, Any]:
        from ..activities import create_drill_attempt
        from ..attempts import load_attempt

        source = load_attempt(self._attempt_path(name))
        pack = self._resolve_pack(f"{source['pack_id']}@{source['pack_version']}")
        attempt = create_drill_attempt(pack, source)
        attempt_path = save_attempt_to_dir(attempt, self.attempt_dir)
        session = ExamSession(pack, attempt, attempt_path)
        return self._exam_view(self._register({"kind": "exam", "session": session}))

    def start_review(self, pack_ref: str) -> dict[str, Any]:
        from .. import srs

        pack = self._resolve_pack(pack_ref)
        queue = srs.load_queue(srs.queue_path_for(self.attempt_dir))
        attempt = srs.create_review_attempt(pack, queue)
        attempt_path = save_attempt_to_dir(attempt, self.attempt_dir)
        session = ExamSession(pack, attempt, attempt_path)
        return self._exam_view(self._register({"kind": "exam", "session": session}))

    def start_course_exam(self, pack_ref: str, course_id: str) -> dict[str, Any]:
        from ..courses import courses_for

        pack = self._resolve_pack(pack_ref)
        course = next((c for c in courses_for(pack.pack_id, self.courses_path)
                       if str(c.get("id")) == course_id), None)
        if course is None:
            raise ApiError(404, f"No course {course_id!r} for {pack.pack_id}.")
        session = ExamSession.start(pack, self.attempt_dir,
                                    question_ids=course["question_ids"], activity="course")
        return self._exam_view(self._register({
            "kind": "exam", "session": session,
            "course": {"pack_id": pack.pack_id, "course_id": course_id},
        }))

    def review_due(self) -> dict[str, int]:
        from .. import srs

        queue = srs.load_queue(srs.queue_path_for(self.attempt_dir))
        return srs.due_counts_by_pack(queue)

    def _exam_view(self, activity_id: str) -> dict[str, Any]:
        activity = self._activities[activity_id]
        session: ExamSession = activity["session"]
        question = session.current_question()
        answered, total = session.progress()
        earned, available = session.running_score()
        view: dict[str, Any] = {
            "id": activity_id,
            "kind": "exam",
            "activity": session.activity,
            "pack_id": session.pack.pack_id,
            "pack_title": session.pack.title,
            "progress": [answered, total],
            "score": [earned, available],
            "remaining_seconds": session.remaining_seconds(),
            "done": question is None,
        }
        if question is not None:
            texts = self._question_speech_texts(question)
            audio_parts = len(texts) if self._audio_on() and is_listening_question(question) else 0
            view["question"] = _public_question(
                question, session.question_number(), total, audio_parts, self.show_transcript
            )
            if activity.get("presented_qid") != question.get("question_id"):
                session.mark_presented()
                activity["presented_qid"] = question.get("question_id")
                activity["hint_index"] = 0  # hints restart with each question
        return view

    def activity_view(self, activity_id: str) -> dict[str, Any]:
        activity = self._activities[activity_id]
        if activity["kind"] == "exam":
            return self._exam_view(activity_id)
        return self._drill_view(activity_id)

    def answer(self, activity_id: str, value: str) -> dict[str, Any]:
        activity = self._activities[activity_id]
        if activity["kind"] == "exam":
            return self._answer_exam(activity, value)
        return self._answer_drill(activity, value)

    def _answer_exam(self, activity: dict[str, Any], value: str) -> dict[str, Any]:
        session: ExamSession = activity["session"]
        question = session.current_question()
        if question is None:
            raise ApiError(400, "No question is awaiting an answer.")
        from ..report import describe_correct_answer

        result = session.submit(value)
        response: dict[str, Any] = {
            "correct": bool(result.get("correct")),
            "needs_review": bool(result.get("needs_review")),
            "points": [result.get("points_awarded", 0), result.get("max_points", 0)],
            "correct_answer": describe_correct_answer(question),
            "explanation": question.get("explanation", {}) or {},
            "finished": not session.has_remaining(),
        }
        correct_option = (question.get("answer") or {}).get("correct_option_id")
        if correct_option is not None:  # lets the client mark the option rows
            response["correct_option_id"] = str(correct_option)
        if is_listening_question(question):
            response["transcript"] = transcript_text(question)
        if response["finished"]:
            response["summary"] = self._finalize_exam(activity)
        return response

    def _finalize_exam(self, activity: dict[str, Any]) -> dict[str, Any]:
        from .. import srs

        session: ExamSession = activity["session"]
        attempt = session.finalize()
        queue_path = srs.queue_path_for(self.attempt_dir)
        queue = srs.load_queue(queue_path)
        if srs.record_attempt(queue, attempt):
            srs.save_queue(queue, queue_path)
        course = activity.get("course")
        if course:
            from ..courses import mark_done

            mark_done(self.attempt_dir, course["pack_id"], course["course_id"])
        earned, available = session.running_score()
        missed = missed_question_ids(attempt)
        self._activities.pop(activity["id"], None)
        result = attempt.get("result", {}) or {}
        return {
            "score": [earned, available],
            "total_points": result.get("total_points", available),
            "missed": len(missed),
            "attempt_file": session.attempt_path.name,
            "activity": session.activity,
            "course_completed": bool(course),
            "review_due": len(srs.due_items(queue)),
        }

    def exam_hint(self, activity_id: str) -> dict[str, Any]:
        """One vocabulary hint per call, like the shell's /hint."""
        activity = self._activities[activity_id]
        if activity["kind"] != "exam":
            raise ApiError(400, "Hints only apply to exam questions.")
        question = activity["session"].current_question()
        if question is None:
            raise ApiError(400, "No question is awaiting an answer.")
        vocabulary = (question.get("explanation") or {}).get("vocabulary", [])
        index = int(activity.get("hint_index", 0))
        if not vocabulary:
            return {"hint": None, "message": "No hints are available for this question."}
        if index >= len(vocabulary):
            return {"hint": None, "message": "No more hints — you have seen them all."}
        item = vocabulary[index]
        activity["hint_index"] = index + 1
        note = f" ({item['note']})" if item.get("note") else ""
        return {
            "hint": f"{item.get('ko', '?')} — {item.get('en', '?')}{note}",
            "shown": index + 1,
            "total": len(vocabulary),
        }

    def reveal_transcript(self, activity_id: str) -> dict[str, Any]:
        activity = self._activities[activity_id]
        if activity["kind"] == "exam":
            question = activity["session"].current_question()
            if question is None:
                raise ApiError(400, "No open question.")
            return {"transcript": transcript_text(question) or str(question.get("passage", ""))}
        item = self._current_item(activity)
        return {"transcript": str(item.get("answer", ""))}

    def pause(self, activity_id: str) -> dict[str, Any]:
        activity = self._activities.pop(activity_id, None) or {}
        if activity.get("kind") == "exam":
            # Attempt files save after every answer; nothing else to do.
            session: ExamSession = activity["session"]
            return {"paused": True, "attempt_file": session.attempt_path.name}
        done = activity.get("index", 0)
        if done:  # stopped-early runs still count as practice done today
            self._record_drill(activity, done=done)
        return {"paused": True, "completed_items": done,
                "hits": activity.get("hits", 0), "recorded": bool(done)}

    # ------------------------------------------------------------- practice

    def start_practice(self, body: dict[str, Any]) -> dict[str, Any]:
        mode = str(body.get("mode", ""))
        pack = self._resolve_pack(str(body["pack"])) if body.get("pack") else None
        count = int(body.get("count") or 0)
        meta: dict[str, Any] = {}

        if mode == "typing":
            from ..flashcards import gloss_map
            from ..typing_drill import build_typing_items

            targets = build_typing_items(
                seed=self.seed, pack=pack, count=count or 12,
                library_dir=None if pack else self.library_dir,
            )
            meanings = gloss_map(pack=pack, library_dir=None if pack else self.library_dir)
            items = []
            for target in targets:
                item = {"show": target, "accept": [target], "answer": target, "speech": target}
                if target in meanings:
                    item["meaning"] = meanings[target]
                items.append(item)
            label = "Typing practice"
        elif mode == "numbers":
            from ..numbers import build_number_items

            items = build_number_items(seed=self.seed, count=count or 10,
                                       category=body.get("category") or None)
            label = "Number practice"
        elif mode == "recall":
            from ..flashcards import build_recall_items

            items = build_recall_items(pack=pack, library_dir=None if pack else self.library_dir,
                                       seed=self.seed, count=count or 10)
            label = "Vocab recall"
        elif mode == "dictation":
            from ..dictation import collect_dictation_texts

            if pack is None:
                raise ApiError(400, "Dictation needs a pack.")
            texts = collect_dictation_texts(pack, limit=count or None)
            if not texts:
                raise ApiError(400, f"{pack.pack_id} has no listening transcripts.")
            items = [{
                "show": "Listen and type what you hear.",
                "accept": [text], "answer": text, "speech": text, "dictation": True,
            } for text in texts]
            label = "Dictation"
        elif mode == "misses":
            from ..flashcards import gloss_map
            from ..practice_log import load_practice_log, weak_items

            weak = weak_items(load_practice_log(self.attempt_dir), limit=count or 10)
            if not weak:
                raise ApiError(400, "No missed items recorded yet — practice first, then drill your misses.")
            glosses = gloss_map(library_dir=self.library_dir)
            items = []
            for entry in weak:
                word = entry["item"]
                if word in glosses:  # vocabulary: production from the gloss
                    items.append({"show": f"Type the Korean:  {glosses[word]}",
                                  "accept": [word], "answer": word, "speech": word,
                                  "meaning": f"{word} — {glosses[word]}"})
                else:  # anything else (numbers, phrases): rewrite it correctly
                    items.append({"show": f"Type it again:  {word}",
                                  "accept": [word], "answer": word, "speech": word})
            label = "Weak items"
        elif mode == "homework":
            from ..courses import courses_for
            from ..homework import build_homework

            if pack is None:
                raise ApiError(400, "Homework needs a pack.")
            course_id = str(body.get("course_id", ""))
            course = next((c for c in courses_for(pack.pack_id, self.courses_path)
                           if str(c.get("id")) == course_id), None)
            if course is None:
                raise ApiError(404, f"No course {course_id!r} for {pack.pack_id}.")
            items = build_homework(course, pack=pack, seed=self.seed)
            if not items:
                raise ApiError(400, "This lesson has no vocabulary or grammar to practice yet.")
            label = "Homework"
            meta = {"pack_id": pack.pack_id, "course_id": course_id,
                    "lesson_title": course.get("title", ""), "objectives": course.get("objectives", [])}
        else:
            raise ApiError(400, f"Unknown practice mode: {mode!r}")

        if not items:
            raise ApiError(400, "No practice items found. Import a pack first.")
        activity_id = self._register({
            "kind": "drill", "mode": mode, "label": label, "items": items,
            "index": 0, "hits": 0, "missed": [], "meta": meta,
        })
        return self._drill_view(activity_id)

    def _current_item(self, activity: dict[str, Any]) -> dict[str, Any]:
        items = activity["items"]
        index = activity["index"]
        if index >= len(items):
            raise ApiError(400, "This practice session is finished.")
        return items[index]

    def _drill_view(self, activity_id: str) -> dict[str, Any]:
        activity = self._activities[activity_id]
        items = activity["items"]
        index = activity["index"]
        view: dict[str, Any] = {
            "id": activity_id,
            "kind": "drill",
            "mode": activity["mode"],
            "label": activity["label"],
            "progress": [index, len(items)],
            "hits": activity["hits"],
            "meta": activity["meta"],
            "done": index >= len(items),
        }
        if index < len(items):
            item = items[index]
            audio_ok = self._audio_on() and bool(item.get("speech"))
            # Speaking an item whose speech IS the expected answer would give
            # it away — dictation is the exception (hearing it is the task).
            accepted = {_normalize(str(answer)) for answer in item["accept"]}
            spoils = not item.get("dictation") and _normalize(str(item.get("speech", ""))) in accepted
            show = item["show"]
            if item.get("dictation") and not audio_ok:
                show = f"Type this sentence:  {item['answer']}"  # no TTS: stay usable
            view["item"] = {
                "show": show,
                "index": index + 1,
                "total": len(items),
                "kind": item.get("kind", activity["mode"]),
                "options": item.get("options"),
                "dictation": bool(item.get("dictation")),
                "no_digits": bool(item.get("no_digits")),
                "audio": audio_ok and not spoils,
            }
        return view

    def _answer_drill(self, activity: dict[str, Any], value: str) -> dict[str, Any]:
        from ..dictation import accuracy, feedback_lines
        from ..hangul import keystroke_hint

        item = self._current_item(activity)
        if item.get("no_digits") and any(ch.isdigit() for ch in value):
            return {"retry": True,
                    "message": "Write the number in Korean letters (한글), not digits. Try again."}
        response: dict[str, Any] = {"retry": False}
        if item.get("dictation"):
            score = accuracy(item["answer"], value)
            correct = score >= 0.999
            response["accuracy"] = round(score, 3)
            response["feedback"] = feedback_lines(item["answer"], value)
        else:
            accepted = {_normalize(answer) for answer in item["accept"]}
            correct = _normalize(value) in accepted
        response["correct"] = correct
        response["expected"] = item.get("reveal") or " / ".join(item["accept"])
        if self._audio_on() and item.get("speech"):
            response["speech"] = item["speech"]  # hear the answer after grading
        if item.get("meaning"):
            response["meaning"] = item["meaning"]
        if not correct and not item.get("options"):
            response["keys"] = keystroke_hint(item["answer"])
        if correct:
            activity["hits"] += 1
        else:
            activity["missed"].append(item.get("miss_key") or item["answer"])
        activity["index"] += 1
        response["finished"] = activity["index"] >= len(activity["items"])
        if response["finished"]:
            response["summary"] = self._finish_drill(activity)
        return response

    def _finish_drill(self, activity: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "hits": activity["hits"],
            "total": len(activity["items"]),
            "missed": list(dict.fromkeys(activity["missed"])),
        }
        meta = activity["meta"]
        if activity["mode"] == "homework" and meta.get("pack_id"):
            from ..homework import record_homework

            entry = record_homework(self.attempt_dir, meta["pack_id"], meta["course_id"],
                                    activity["hits"], len(activity["items"]))
            summary["homework"] = entry
        self._record_drill(activity, done=len(activity["items"]))
        self._activities.pop(activity["id"], None)
        return summary

    def _record_drill(self, activity: dict[str, Any], done: int) -> None:
        if done <= 0:
            return
        from ..practice_log import record_practice

        record_practice(
            self.attempt_dir,
            mode=activity["mode"],
            label=activity["label"],
            hits=activity["hits"],
            total=done,
            missed=list(activity["missed"]),
            pack_id=activity["meta"].get("pack_id"),
        )

    # -------------------------------------------------------------- courses

    def courses(self) -> list[dict[str, Any]]:
        from ..courses import courses_for, load_progress
        from ..homework import homework_entry, load_homework_progress

        try:
            entries = latest_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            entries = []
        done_by_pack = load_progress(self.attempt_dir)
        hw_progress = load_homework_progress(self.attempt_dir)
        result = []
        for entry in entries:
            pack_id = str(entry.get("pack_id"))
            lessons = courses_for(pack_id, self.courses_path)
            if not lessons:
                continue
            done = set((done_by_pack.get(pack_id) or {}).keys())
            result.append({
                "pack_id": pack_id,
                "title": entry.get("title", pack_id),
                "lessons": [{
                    "id": lesson.get("id"),
                    "order": lesson.get("order"),
                    "title": lesson.get("title"),
                    "title_ko": lesson.get("title_ko", ""),
                    "objectives": lesson.get("objectives", []),
                    "counts": {
                        "vocabulary": len(lesson.get("new_vocabulary", [])),
                        "grammar": len(lesson.get("new_grammar", [])),
                        "questions": len(lesson.get("question_ids", [])),
                    },
                    "done": str(lesson.get("id")) in done,
                    "homework": homework_entry(hw_progress, pack_id, str(lesson.get("id"))),
                } for lesson in lessons],
            })
        return result

    def course_lesson(self, pack_ref: str, course_id: str) -> dict[str, Any]:
        from ..courses import courses_for

        pack = self._resolve_pack(pack_ref)
        course = next((c for c in courses_for(pack.pack_id, self.courses_path)
                       if str(c.get("id")) == course_id), None)
        if course is None:
            raise ApiError(404, f"No course {course_id!r} for {pack.pack_id}.")
        return {"pack_id": pack.pack_id, "lesson": course}

    # ---------------------------------------------------------------- audio

    def _audio_on(self) -> bool:
        return self.audio_enabled and not self._audio_failed

    def _question_speech_texts(self, question: dict[str, Any]) -> list[str]:
        if not is_listening_question(question):
            return []
        return collect_question_speech_texts(question, include_prompt=False)

    def _synthesize(self, text: str, slow: bool = False) -> Path:
        if not text.strip():
            raise ApiError(400, "Nothing to speak.")
        if not self._audio_on():
            raise ApiError(503, "TTS is disabled or unavailable.")
        from dataclasses import replace

        config = self.tts_config
        if slow:  # 'say that again, slowly' — 3/4 speed, cached separately
            config = replace(config, speed=max(0.4, config.speed * 0.75))
        try:
            if self._synthesizer is not None:
                return Path(self._synthesizer(text, config))
            from ..tts import synthesize_many

            return synthesize_many([text], config)[0]
        except ApiError:
            raise
        except Exception as exc:  # engine/model/subprocess failures
            self._audio_failed = True
            raise ApiError(503, f"TTS failed: {exc}") from exc

    def _audio_response(self, text: str, slow: bool = False) -> tuple[int, Any]:
        path = self._synthesize(text, slow=slow)
        return 200, (path.read_bytes(), "audio/wav")

    def activity_audio(self, activity_id: str, part: int, slow: bool = False) -> tuple[int, Any]:
        activity = self._activities[activity_id]
        if activity["kind"] == "exam":
            question = activity["session"].current_question()
            if question is None:
                raise ApiError(400, "No open question.")
            texts = self._question_speech_texts(question)
            if not texts or part >= len(texts):
                raise ApiError(404, "No audio for this question.")
            return self._audio_response(texts[part], slow=slow)
        item = self._current_item(activity)
        return self._audio_response(str(item.get("speech", "")), slow=slow)

    def activity_say(self, activity_id: str) -> tuple[int, Any]:
        return self.activity_audio(activity_id, 0)
