from __future__ import annotations

from enum import Enum
from typing import Sequence

from anki.cards import CardId
from anki.collection import OpChanges
from anki.consts import *
from anki.notes import Note, NoteId
from aqt import mw
from aqt.qt import *


class Morphemizer(Enum):
    SPACE_SEPARATED = "Space-separated"
    KANJI = "Kanji"


class KnownWordManagerException(Exception):
    def __init__(self, type: str, msg: str) -> None:
        self.type = type
        self.msg = msg
        super().__init__()


def is_kanji(char: str) -> bool:
    return ord(char) >= 0x4E00 and ord(char) < 0xA000


def get_unique_words(text: str, morphemizer: Morphemizer) -> set[str]:
    word_set = set()
    if morphemizer == Morphemizer.KANJI:
        for c in text:
            if is_kanji(c):
                word_set.add(c)
    else:
        word_set.update(text.split())
    return word_set


def summarize_note(note: Note) -> str:
    max_len = 50
    s = note.joined_fields()
    if len(s) < max_len:
        return s
    return s[:max_len] + "..."


def summarize_words(word: set[str], morphemizer: Morphemizer) -> str:
    if morphemizer == Morphemizer.SPACE_SEPARATED:
        return " ".join(sorted(word))
    s = "".join(sorted(word))
    max_len = 50
    if len(s) < max_len:
        return s
    return s[:max_len] + "[...%d more...]" % (len(s) - max_len)


def summarize_list(l: list) -> list[str]:
    maximum = 20
    if len(l) < maximum:
        return l
    l2 = l[:maximum]
    l2.append("[...%d more...]" % (len(l) - maximum))
    return l2


def get_deck_notes(deck_name: str, filt: str = "") -> Sequence[NoteId]:
    return mw.col.find_notes('deck:"%s" %s' % (deck_name, filt))


def get_deck_cards(deck_name: str) -> Sequence[CardId]:
    return mw.col.find_cards('deck:"%s"' % (deck_name,))


def get_known_words(
    deck_name: str, word_field: str, morphemizer: Morphemizer, match_all_words: bool
) -> set[str]:
    word_set = set()
    note_list = get_deck_notes(deck_name, "is:review" if not match_all_words else "")
    if not note_list:
        raise KnownWordManagerException(
            "critical",
            "Deck '%s' is empty or does not match your criteria." % deck_name,
        )
    for note_id in note_list:
        note = mw.col.get_note(note_id)
        if word_field in note:
            for k in get_unique_words(note[word_field], morphemizer):
                word_set.add(k)
    return word_set


def should_ignore_note(note: Note, morphemizer: Morphemizer) -> bool:
    joined_fields = note.joined_fields()
    if morphemizer == Morphemizer.KANJI and not any(is_kanji(k) for k in joined_fields):
        return True
    if morphemizer == Morphemizer.SPACE_SEPARATED and not joined_fields.strip():
        return True
    return False


class KnownWordChanges:
    def __init__(self, report: str, changes: OpChanges):
        self.report = report
        self.changes = changes


def update_managed_cards(
    sentences_deck: str,
    words_deck: str,
    word_field: str,
    morphemizer: Morphemizer,
    skip_known_sentences: bool,
    match_all_words: bool,
) -> KnownWordChanges:
    undo_entry = mw.col.add_custom_undo_entry("Update managed cards")

    known_words = get_known_words(words_deck, word_field, morphemizer, match_all_words)
    seen_words: set[str] = set()
    suspended_text = []
    unsuspended_text = []

    managed_cards = get_deck_cards(sentences_deck)
    if len(managed_cards) == 0:
        raise KnownWordManagerException(
            "warning",
            f'No sentence cards in the deck "{sentences_deck}" were found. Nothing will happen.',
        )

    suspend_cids = []
    unsuspend_cids = []
    for card_id in managed_cards:
        card = mw.col.get_card(card_id)
        note = card.note()
        if should_ignore_note(note, morphemizer):
            continue
        joined_fields = note.joined_fields()
        note_words = get_unique_words(joined_fields, morphemizer)
        if (
            any(k not in known_words for k in note_words)
            or skip_known_sentences
            and seen_words >= note_words
        ):
            if card.queue != QUEUE_TYPE_SUSPENDED:
                suspend_cids.append(card_id)
                suspended_text.append(
                    "%d (%s)" % (card_id, summarize_note(card.note()))
                )
        else:
            if card.queue == QUEUE_TYPE_SUSPENDED:
                unsuspend_cids.append(card_id)
                unsuspended_text.append(
                    "%d (%s)" % (card_id, summarize_note(card.note()))
                )
        seen_words.update(note_words)

    mw.col.sched.suspend_cards(suspend_cids)
    mw.col.sched.unsuspend_cards(unsuspend_cids)

    if len(suspended_text) == 0:
        suspended_text = ["None"]
    if len(unsuspended_text) == 0:
        unsuspended_text = ["None"]

    known_words_string = (
        "<b>Known Words:</b> " + summarize_words(known_words, morphemizer) + "<br><br>"
    )
    suspended_card_string = "<b>Suspended cards:</b><br>%s<br><br>" % "<br>".join(
        summarize_list(suspended_text)
    )
    unsuspended_card_string = "<b>Unsuspended cards:</b><br>%s<br>" % "<br>".join(
        summarize_list(unsuspended_text)
    )

    return KnownWordChanges(
        known_words_string + suspended_card_string + unsuspended_card_string,
        mw.col.merge_undo_entries(undo_entry),
    )
