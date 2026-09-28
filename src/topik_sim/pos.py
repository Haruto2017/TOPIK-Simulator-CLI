"""Part-of-speech buckets for vocabulary practice.

Wordlists carry no grammatical class, so one is inferred mechanically from
what the list already has — the headword's shape and its English gloss —
never from reading exam text. The buckets follow the school grammar a TOPIK I
learner meets: 명사 (nouns — the 체언 bucket, so pronouns, numerals and
counters sit here too), 동사 (action verbs), 형용사 (descriptive verbs, i.e.
adjectives), 부사 (adverbs, including the 그리고/그래서 connectives). Polite
set phrases such as 안녕하세요 fall in no bucket.

The verb/adjective split reuses the conjugation engine's rule: a "to be …"
gloss marks a descriptive verb, anything else with a "to …" gloss is an
action verb. Adverbs come from a short curated list plus shape rules
(-히 always; -게/-이/-로 when the gloss reads like an adverb).
"""
from __future__ import annotations

import re
from typing import Iterable

WORD_CLASSES: tuple[str, ...] = ("noun", "verb", "adjective", "adverb")
CLASS_LABELS: dict[str, str] = {
    "noun": "Nouns · 명사",
    "verb": "Verbs · 동사",
    "adjective": "Adjectives · 형용사",
    "adverb": "Adverbs · 부사",
}
_ALIASES: dict[str, str] = {
    "n": "noun", "nouns": "noun", "명사": "noun",
    "v": "verb", "verbs": "verb", "동사": "verb",
    "a": "adjective", "adj": "adjective", "adjectives": "adjective", "형용사": "adjective",
    "adv": "adverb", "adverbs": "adverb", "부사": "adverb",
}

# Adverbs whose shape alone does not give them away.
ADVERBS: frozenset[str] = frozenset("""
아주 너무 정말 진짜 매우 조금 좀 많이 더 덜 가장 제일 다 모두 전부 같이 함께 다시 또 자주 항상 늘
보통 가끔 별로 전혀 아직 벌써 이미 곧 금방 먼저 나중에 일찍 빨리 천천히 잘 못 안 꼭 아마 혹시
특히 그냥 계속 갑자기 바로 방금 아까 자꾸 거의 약간 잠깐 잠시 이따가 미리 따로 서로 새로 스스로
오래 언제나 어서 얼른 훨씬 겨우 드디어 마침 역시 물론 또한 아무리 그래도 지금 왜 어떻게 얼마나
그리고 그래서 그런데 하지만 그러면 그렇지만 그러나 그러니까 왜냐하면 다 같이 곧바로 열심히
매일 매주 매달 매년 이제 마침내 우선 언제 잠깐만 참 꽤 조금도 대충 혼자 똑같이 반드시 또는 직접
""".split())

# A first gloss sense that is one of these reads as an adverb.
_ADVERB_GLOSSES: frozenset[str] = frozenset({
    "very", "too", "also", "again", "already", "still", "soon", "now", "often", "always",
    "usually", "sometimes", "never", "together", "all together", "well", "later", "early",
    "late", "really", "probably", "maybe", "perhaps", "just", "only", "almost", "mostly",
    "especially", "quickly", "slowly", "hard", "directly", "suddenly", "immediately",
    "right away", "a lot", "much", "more", "most", "less", "yet", "then", "so", "but",
    "however", "and", "therefore", "anyway", "of course", "certainly", "exactly", "first",
    "separately", "each other", "newly", "by oneself", "in advance", "at once", "a little",
    "for a long time", "diligently", "carefully", "quietly", "loudly", "far", "near",
    "like this", "like that", "in this way", "straight ahead", "as it is", "nearby",
    "late at night", "a while ago", "for a moment", "in total", "by any chance",
})
_ADVERB_SHAPES = ("게", "이", "로")   # adverb when the gloss agrees
# Polite sentence endings mark a set phrase, not a word (잠깐만요, 글쎄요, 가세요).
_EXPRESSION_SUFFIXES = ("세요", "습니까", "만요", "럼요", "쎄요", "합니다", "입니다")
_INTERJECTIONS: frozenset[str] = frozenset({"네", "예", "아니", "응", "아니요", "여보세요", "저기요", "때문이다"})
# Gloss-driven kinds the "to be …" rule gets wrong.
_DESCRIPTIVE_WORDS: frozenset[str] = frozenset({"아니다"})          # negative copula
_ACTION_WORDS: frozenset[str] = frozenset({"위하다", "대하다", "못하다"})  # "to be for/about/unable"
_ADJECTIVE_GLOSS = re.compile(r"^(?:\(?(?:to )?be\)? |is |being )")


def normalize_class(value: str | None) -> str | None:
    """Canonical class id for a user-typed name/alias, else None."""
    key = str(value or "").strip().lower()
    if key in WORD_CLASSES:
        return key
    return _ALIASES.get(key)


def _first_sense(en: str) -> str:
    sense = re.split(r"[,;/]|\bor\b", en.strip().lower(), maxsplit=1)[0].strip()
    return re.sub(r"\s*\(.*?\)\s*", " ", sense).strip()


def _reads_as_adverb(en: str) -> bool:
    sense = _first_sense(en)
    if not sense:
        return False
    if sense in _ADVERB_GLOSSES:
        return True
    head = sense.split()[0]
    return head.endswith("ly") and head not in {"family", "only", "early", "daily", "lovely", "friendly", "lonely", "ugly", "holy", "jelly", "belly", "fly", "reply", "supply", "apply", "rally", "ally", "bully", "tally", "lily"} or sense.endswith("ly")


def word_class(ko: str, en: str = "") -> str:
    """"noun", "verb", "adjective", "adverb", or "other" for a wordlist entry."""
    from .conjugation import ACTION_OVERRIDES, DESCRIPTIVE_OVERRIDES, _verb_kind

    ko = str(ko or "").strip()
    en = str(en or "").strip()
    if not ko:
        return "other"
    if ko in _INTERJECTIONS:
        return "other"
    if ko in ADVERBS:
        return "adverb"
    if ko in _DESCRIPTIVE_WORDS:
        return "adjective"
    if ko in _ACTION_WORDS:
        return "verb"
    if ko.endswith("다") and (en.lower().startswith("to ") or ko in ACTION_OVERRIDES | DESCRIPTIVE_OVERRIDES):
        kind = _verb_kind(ko, en)
        if kind == "descriptive":
            return "adjective"
        return "verb"          # action, or a "to be <participle>" passive
    if len(ko) > 1 and ko.endswith(_EXPRESSION_SUFFIXES):
        return "other"
    if ko.endswith("다") and _ADJECTIVE_GLOSS.match(en.lower()):
        return "adjective"     # "(be) big" style glosses
    if len(ko) > 1 and ko.endswith("히"):
        return "adverb"
    if len(ko) > 1 and ko.endswith(_ADVERB_SHAPES) and _reads_as_adverb(en):
        return "adverb"
    return "noun"


def words_in_class(words: Iterable[dict], word_class_id: str) -> list[dict]:
    """The entries of one class, in list order."""
    wanted = normalize_class(word_class_id)
    if wanted is None:
        return []
    return [word for word in words if word_class(word.get("ko", ""), word.get("en", "")) == wanted]


def class_counts(words: Iterable[dict]) -> dict[str, int]:
    """How many entries fall in each class (the four buckets only)."""
    counts = {name: 0 for name in WORD_CLASSES}
    for word in words:
        bucket = word_class(word.get("ko", ""), word.get("en", ""))
        if bucket in counts:
            counts[bucket] += 1
    return counts
