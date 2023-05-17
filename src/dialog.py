from anki.collection import Collection
from aqt.deckchooser import DeckChooser
from aqt.main import AnkiQt
from aqt.operations import CollectionOp
from aqt.qt import *
from aqt.tagedit import TagEdit
from aqt.utils import showInfo

from . import consts
from .manager import (
    KnownWordChanges,
    KnownWordManagerException,
    Morphemizer,
    update_managed_cards,
)

if qtmajor > 5:
    from .forms.dialog_qt6 import Ui_Dialog
else:
    from .forms.dialog_qt5 import Ui_Dialog


class Dialog(QDialog):
    def __init__(self, mw: AnkiQt) -> None:
        super().__init__(mw)
        self.mw = mw
        self.config = mw.addonManager.getConfig(__name__)
        self.setup_ui()

    def setup_ui(self) -> None:
        self.form = Ui_Dialog()
        self.form.setupUi(self)
        self.setWindowTitle(consts.ADDON_NAME)
        self.tagedit = TagEdit(self)
        self.tagedit.setCol(self.mw.col)
        self.tagedit.setText(self.config["managed_sentences_tags"])
        self.form.formLayout.replaceWidget(self.form.managedTagWidget, self.tagedit)
        # FIXME: the on_deck_changed arg is not available in versions older than 2.1.50
        self.deck_chooser = DeckChooser(
            self.mw,
            self.form.wordsDeckWidget,
            label=False,
            starting_deck_id=self.mw.col.decks.id(self.config["words_deck_name"]),
            on_deck_changed=self.on_deck_changed,
        )
        self.update_fields()
        word_field = self.config["words_deck_field"].lower()
        for i in range(self.form.wordField.count()):
            field = self.form.wordField.itemText(i)
            if word_field == field.lower():
                self.form.wordField.setCurrentIndex(i)
                break
        self.form.morphemizer.addItems([m.value for m in list(Morphemizer)])
        morphemizer = self.config["morphemizer"]
        for i in range(self.form.morphemizer.count()):
            m = self.form.morphemizer.itemText(i)
            if morphemizer == m:
                self.form.morphemizer.setCurrentIndex(i)
                break
        skip_known_sentences = self.config["skip_known_sentences"]
        self.form.skipKnownSentences.setChecked(skip_known_sentences)
        match_all_words = self.config["match_all_words"]
        self.form.matchAllWords.setChecked(match_all_words)
        qconnect(self.form.processButton.clicked, self.on_process)

    def update_fields(self) -> None:
        # TODO: maybe simplify query
        fields = self.mw.col.db.list(
            "select distinct name from fields where ntid in (select id from notetypes where id in (select mid from notes where id in (select nid from cards where did = ?)))",
            self.deck_chooser.selected_deck_id,
        )
        self.form.wordField.clear()
        self.form.wordField.addItems(fields)

    def on_deck_changed(self, did: int) -> None:
        self.update_fields()

    def on_process(self) -> None:
        managed_tags = self.tagedit.text()
        words_deck = self.deck_chooser.deckName()
        word_field = self.form.wordField.currentText()
        morphemizer = list(Morphemizer)[self.form.morphemizer.currentIndex()]
        skip_known_sentences = self.form.skipKnownSentences.isChecked()
        match_all_words = self.form.matchAllWords.isChecked()

        self.config["managed_sentences_tags"] = managed_tags
        self.config["words_deck_name"] = words_deck
        self.config["words_deck_field"] = word_field
        self.config["morphemizer"] = morphemizer.value
        self.config["skip_known_sentences"] = skip_known_sentences
        self.config["match_all_words"] = match_all_words
        self.mw.addonManager.writeConfig(__name__, self.config)

        def op(col: Collection) -> KnownWordChanges:
            return update_managed_cards(
                managed_tags,
                words_deck,
                word_field,
                morphemizer,
                skip_known_sentences,
                match_all_words,
            )

        def on_success(changes: KnownWordChanges) -> None:
            self.accept()
            showInfo(changes.report)

        def on_failure(exc: Exception) -> None:
            if isinstance(exc, KnownWordManagerException):
                showInfo(exc.msg, title=consts.ADDON_NAME, type=exc.type)
            else:
                raise exc

        CollectionOp(self, op=op).success(on_success).failure(
            on_failure
        ).run_in_background()
