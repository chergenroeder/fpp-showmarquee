"""The countdown message as two styled pieces.

Number first:  [number "8 Days"] [text "to Christmas"]   -> "8 Days to Christmas"
Number last:   [text "Christmas in"] [number "8 Days"]   -> "Christmas in 8 Days"

The number piece (number and unit) uses the number style; the text piece uses
the text style. The renderer puts one space, in the text font, between them.
"""

from dataclasses import dataclass
from typing import List, Tuple

from .timecalc import Display, Target

NUMBER = "number"
TEXT = "text"


@dataclass(frozen=True)
class Message:
    pieces: Tuple[Tuple[str, str], ...]   # ((role, text), ...) in display order

    @property
    def plain(self) -> str:
        return " ".join(text for _, text in self.pieces)

    @property
    def blank(self) -> bool:
        return not self.pieces


def build_message(display: Display, target: Target, layout: dict) -> Message:
    if display.kind == "blank" or not display.number_text:
        return Message(())

    name = target.name.strip()
    first = layout.get("number_position", "first") == "first"
    connector = str(layout.get("connector_first" if first else "connector_last",
                               "to" if first else "in")).strip()
    # Drop whichever word is empty rather than leave a double space
    words = [w for w in ((connector, name) if first else (name, connector)) if w]
    text = " ".join(words)

    pieces: List[Tuple[str, str]] = [(NUMBER, display.number_text)]
    if text:
        if first:
            pieces.append((TEXT, text))
        else:
            pieces.insert(0, (TEXT, text))
    return Message(tuple(pieces))
