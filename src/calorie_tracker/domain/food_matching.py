"""Best-guess matching of a typed food name against the names in the catalogue.

The guess never decides anything by itself: it ranks candidates and says whether the top one is *confident*,
which only happens for spelling-level differences (case, accents, plural endings, word order, a one-letter
typo). Anything that could change what is actually eaten (a missing or extra word such as "skim", "boiled",
"2%") is only ever a suggestion, because it changes the nutrition.
"""

from __future__ import annotations

import difflib
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

CONFIDENT_SCORE = 0.9      # lowest score that may be pre-selected
CONFIDENT_MARGIN = 0.1     # how far ahead of the runner-up a confident guess must be
MIN_SCORE = 0.6            # below this a candidate is not worth suggesting
_FUZZY_CAP = 0.89          # plain text similarity can suggest but never be confident
_MIN_TYPO_WORD = 6         # shortest word where a one-letter typo is forgiven


@dataclass(frozen=True)
class FoodName:
    id: str
    name: str
    recently_used: bool = False


@dataclass(frozen=True)
class Suggestion:
    food_id: str
    name: str
    score: float
    confident: bool


def normalize_name(name: str) -> str:
    """Case-fold, drop punctuation, collapse spaces, and strip accents from Latin letters only.

    Accents are removed only from Latin letters so that, for example, Cyrillic ``й`` is not flattened to ``и``.
    """
    pieces: list[str] = []
    for char in unicodedata.normalize("NFC", name):
        decomposed = unicodedata.normalize("NFD", char)
        if len(decomposed) > 1 and unicodedata.name(decomposed[0], "").startswith("LATIN"):
            char = "".join(part for part in decomposed if not unicodedata.combining(part))
        pieces.append(char.casefold())
    text = "".join(pieces)
    text = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(text.split())


def _singular(word: str) -> str:
    """A deliberately small plural stripper for plain Latin words ("eggs" -> "egg", "potatoes" -> "potato")."""
    if not (word.isascii() and word.isalpha()) or len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes", "zes", "oes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _within_one_edit(first: str, second: str) -> bool:
    """True when the words differ by one substitution, insertion, deletion or adjacent swap."""
    if first == second:
        return True
    if abs(len(first) - len(second)) > 1:
        return False
    if len(first) == len(second):
        diffs = [i for i, (a, b) in enumerate(zip(first, second)) if a != b]
        if len(diffs) == 1:
            return True
        return (
            len(diffs) == 2 and diffs[1] == diffs[0] + 1
            and first[diffs[0]] == second[diffs[1]] and first[diffs[1]] == second[diffs[0]]
        )
    shorter, longer = (first, second) if len(first) < len(second) else (second, first)
    for index in range(len(longer)):
        if longer[:index] + longer[index + 1:] == shorter:
            return True
    return False


def _ratio(first: str, second: str) -> float:
    """Text similarity, skipping the slow exact calculation when cheap upper bounds already rule it out."""
    matcher = difflib.SequenceMatcher(None, first, second)
    if matcher.real_quick_ratio() < MIN_SCORE or matcher.quick_ratio() < MIN_SCORE:
        return 0.0
    return matcher.ratio()


def _score(typed: str, candidate: str) -> float:
    """How well ``candidate`` fits ``typed`` (both already normalised); 0 when it is not worth suggesting."""
    if typed == candidate:
        return 1.0
    typed_words = Counter(_singular(word) for word in typed.split())
    candidate_words = Counter(_singular(word) for word in candidate.split())
    if not typed_words or not candidate_words:
        return 0.0
    if typed_words == candidate_words:
        return 0.95
    typed_only = list((typed_words - candidate_words).elements())
    candidate_only = list((candidate_words - typed_words).elements())
    best = 0.0
    if (
        len(typed_only) == 1 and len(candidate_only) == 1
        and len(typed_only[0]) >= _MIN_TYPO_WORD and _within_one_edit(typed_only[0], candidate_only[0])
    ):
        best = 0.9
    if not typed_only or not candidate_only:
        extras = len(typed_only) + len(candidate_only)  # one side's words all appear in the other
        if extras <= 2:
            best = max(best, 0.8 - 0.05 * extras)
    typed_key = " ".join(sorted(typed_words.elements()))
    candidate_key = " ".join(sorted(candidate_words.elements()))
    ratio = max(_ratio(typed, candidate), _ratio(typed_key, candidate_key))
    return max(best, min(ratio, _FUZZY_CAP))


def suggest_foods(name: str, candidates: Sequence[FoodName], limit: int = 3) -> tuple[Suggestion, ...]:
    """Rank the catalogue foods that the typed ``name`` might mean, best first (at most ``limit``).

    Foods the person used recently only win ties; they can never lift a weak match.
    """
    typed = normalize_name(name)
    if not typed:
        return ()
    scored: list[tuple[float, bool, FoodName]] = []
    for candidate in candidates:
        score = _score(typed, normalize_name(candidate.name))
        if score >= MIN_SCORE:
            scored.append((round(score, 4), candidate.recently_used, candidate))
    scored.sort(key=lambda item: (-item[0], not item[1], item[2].name.casefold()))
    top = scored[:limit]
    results: list[Suggestion] = []
    for position, (score, _recent, food) in enumerate(top):
        confident = False
        if position == 0 and score >= CONFIDENT_SCORE:
            runner_up = top[1][0] if len(top) > 1 else None
            confident = runner_up is None or runner_up <= score - CONFIDENT_MARGIN
        results.append(Suggestion(food.id, food.name, score, confident))
    return tuple(results)
