"""Czech word forms for search: each word in a speech is tagged with its lemma.

A search for "důchod" should also find "důchodu" and "důchody". The ingest job
tags every stored speech with MorphoDiTa and the MorfFlex CZ 2.1 / PDT-C 2.0
model (ÚFAL MFF UK, CC BY-NC-SA 4.0). The tagger chooses one lemma per word from
its sentence, which keeps homonyms apart: stát-1 (state) and stát-3 (stand, cost).

Lemma lexemes are stored with a "~" prefix next to the exact word lexemes in the
speech's search vector, so exact phrases never match a lemma by accident.

Only ingest loads the model (about 400 MB in memory). Web requests expand query
words through the word_form table that ingest fills, and need no model.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MODEL = "czech-morfflex2.1-pdtc2.0-250909"
PREFIX = "~"  # the text-search parser never starts a word lexeme with "~"
MAX_POSITION = 16383  # PostgreSQL tsvector limits
MAX_POSITIONS = 256

_LEMMA = re.compile(r"(?P<raw>.+?)(?P<sense>-\d+)?(?=_|$)")
_POSSESSIVE = re.compile(r"\^\(\*(?P<cut>\d+)(?P<add>[^\W\d_]*)\)")
_UNSAFE = re.compile(r"[^\w-]+")


class MorphologyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Token:
    form: str  # as written
    key: str  # lemma key, see lemma_key()


class Analyzer(Protocol):
    name: str

    def tokens(self, text: str) -> list[Token]: ...


def model_path(data_dir: Path) -> Path:
    return data_dir / "models" / MODEL / f"{MODEL}.tagger"


def lemma_key(lemma: str, tag: str) -> str | None:
    """The search key of a MorfFlex lemma: the lemma with its sense number, lowercase.

    Comments are dropped (``stát-1_^(státní_útvar)`` → ``stát-1``). A possessive
    adjective leads to its noun (``Fialův_;Y_^(*2a)`` → ``fiala``), so a search for
    Fiala finds "Fialova vláda". MorfFlex records negation in the tag, not the lemma;
    negated forms keep a "ne" key of their own, so "státní" does not find "nestátní".
    Punctuation and numerals written in digits get no key.
    """
    if tag[:1] == "Z" or tag[:2] == "C=":
        return None
    match = _LEMMA.match(lemma)
    if not match:
        return None
    key = match.group("raw") + (match.group("sense") or "")
    if tag[:2] == "AU" and (derived := _POSSESSIVE.search(lemma)):
        cut = int(derived.group("cut"))
        if 0 < cut < len(match.group("raw")):
            key = match.group("raw")[:-cut] + derived.group("add")
    if tag[10:11] == "N":
        key = "ne" + key
    return safe_key(key)


def safe_key(key: str) -> str | None:
    """Lowercase letters, digits and hyphens only, so keys are safe in tsvector/tsquery text."""
    key = _UNSAFE.sub("", key.lower())[:100]
    return key or None


def forms_vector(tokens: Sequence[Token]) -> str:
    """tsvector text for the lemma keys of a speech, positions counted in words."""
    positions: dict[str, list[int]] = {}
    for n, token in enumerate(tokens, start=1):
        found = positions.setdefault(token.key, [])
        position = min(n, MAX_POSITION)
        if len(found) < MAX_POSITIONS and (not found or found[-1] != position):
            found.append(position)
    return " ".join(
        f"'{PREFIX}{key}':{','.join(map(str, found))}" for key, found in positions.items()
    )


def lemma_query(keys: Iterable[str]) -> str:
    """tsquery text matching any of these lemma keys."""
    safe = [k for k in (safe_key(key) for key in keys) if k]
    return " | ".join(f"'{PREFIX}{k}'" for k in dict.fromkeys(safe))


class Lemmatizer:
    """MorphoDiTa's tokenizer and tagger. Not thread-safe; one per process."""

    name = MODEL

    def __init__(self, path: Path):
        try:
            from ufal.morphodita import Forms, TaggedLemmas, Tagger, TokenRanges
        except ImportError as error:  # a source build can fail; see dev-environment notes
            raise MorphologyUnavailable(f"ufal.morphodita cannot be imported: {error}") from error
        if not path.is_file():
            raise MorphologyUnavailable(
                f"Czech morphology model not found at {path}; "
                "run `uv run python scripts/fetch_morphology.py`."
            )
        tagger = Tagger.load(str(path))
        if tagger is None:
            raise MorphologyUnavailable(f"Cannot load the tagger model {path}")
        self._tagger = tagger
        self._tokenizer = tagger.newTokenizer()
        self._forms, self._lemmas, self._ranges = Forms(), TaggedLemmas(), TokenRanges()

    def tokens(self, text: str) -> list[Token]:
        out = []
        self._tokenizer.setText(text)
        while self._tokenizer.nextSentence(self._forms, self._ranges):
            self._tagger.tag(self._forms, self._lemmas)
            for form, lemma in zip(self._forms, self._lemmas, strict=True):
                key = lemma_key(lemma.lemma, lemma.tag)
                if key and any(ch.isalpha() for ch in form):
                    out.append(Token(form, key))
        return out
