"""German and English words for the things people ask their memory about, so a word search in one language finds
a memory written in the other. The small embedder links "Schwester" to "sister" only weakly, and these words
(family, birthdays, doctors, bills, work) are most of what personal memory is about.

Parts of German compounds count: "Zahnarzttermin" also searches for "dentist" and "appointment".
"""

from __future__ import annotations

PAIRS = (
    ("schwester", "sister"), ("bruder", "brother"), ("mutter", "mother"), ("mama", "mom"), ("vater", "father"),
    ("papa", "dad"), ("tochter", "daughter"), ("sohn", "son"), ("kinder", "children"), ("eltern", "parents"),
    ("oma", "grandma"), ("opa", "grandpa"), ("ehefrau", "wife"), ("ehemann", "husband"), ("freundin", "girlfriend"),
    ("partnerin", "partner"), ("freund", "friend"), ("kollegin", "colleague"), ("kollege", "colleague"),
    ("chefin", "boss"), ("chef", "boss"), ("nachbar", "neighbour"), ("geburtstag", "birthday"),
    ("hochzeit", "wedding"), ("jahrestag", "anniversary"), ("zahnarzt", "dentist"), ("ärztin", "doctor"),
    ("arzt", "doctor"), ("termin", "appointment"), ("rechnung", "bill"), ("strom", "electricity"),
    ("miete", "rent"), ("vermieter", "landlord"), ("heizung", "heating"), ("versicherung", "insurance"),
    ("steuer", "tax"), ("fitnessstudio", "gym"), ("vertrag", "contract"), ("mitgliedschaft", "membership"),
    ("drucker", "printer"), ("büro", "office"), ("arbeit", "work"), ("firma", "company"), ("urlaub", "holiday"),
    ("flug", "flight"), ("reise", "trip"), ("auto", "car"), ("inspektion", "inspection"), ("allergie", "allergy"),
    ("allergisch", "allergic"), ("medikament", "medicine"), ("tee", "tea"), ("kaffee", "coffee"),
    ("katze", "cat"), ("hund", "dog"), ("telefonnummer", "phone"), ("handy", "phone"), ("adresse", "address"),
    ("wohnt", "lives"), ("schule", "school"), ("fußball", "football"), ("rezept", "recipe"),
    ("abendessen", "dinner"), ("buch", "book"), ("empfohlen", "recommended"), ("besprechung", "meeting"),
    ("treffen", "meeting"), ("tabelle", "table"), ("pflanzen", "plants"), ("gießen", "water"),
    ("nachmittag", "afternoon"), ("nachmittags", "afternoon"), ("morgens", "morning"), ("abends", "evening"),
    ("trinke", "drink"), ("trinken", "drink"), ("essen", "eat"),
)
_TO_ENGLISH: dict[str, list[str]] = {}
_TO_GERMAN: dict[str, list[str]] = {}
for _de, _en in PAIRS:
    _TO_ENGLISH.setdefault(_de, []).append(_en)
    _TO_GERMAN.setdefault(_en, []).append(_de)
_PARTS = sorted((de for de in _TO_ENGLISH if len(de) >= 5), key=len, reverse=True)
"""German words long enough to find inside a compound without matching by chance."""


def translations(word: str) -> list[str]:
    """The other language's words for `word` (lower case), and for the parts of a German compound."""
    found = [*_TO_ENGLISH.get(word, ()), *_TO_GERMAN.get(word, ())]
    if not found and len(word) > 6:
        found = [en for de in _PARTS if de in word for en in _TO_ENGLISH[de]]
    return list(dict.fromkeys(w for w in found if w != word))
