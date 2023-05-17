from __future__ import annotations

from anki.consts import *
from aqt import mw
from aqt.qt import *

from . import consts
from .dialog import Dialog


def on_action() -> None:
    dialog = Dialog(mw)
    dialog.exec()


action = QAction(consts.ADDON_NAME, mw)
action.triggered.connect(on_action)
mw.form.menuTools.addAction(action)
