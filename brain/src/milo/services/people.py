"""Who the user means: a name said to Milo, found in their address book, for a message or a call (ADR 0039).

"Text Anna", "call Mum", "ruf Papa an": the talker writes the name as the user said it. A number or an address said
outright is used as it is, without the address book. Otherwise the Contacts port finds everyone whose name, a word
of it or their nickname starts like it, and "Mum", "Mama" or "Papa" also asks for whom the user's own card names as
their mother or father. This picks the one meant: an exact name wins over a first name, a first name or nickname
over a name that only starts like it. People with different names left over are a question for the user ("Which
Anna: Anna Berg or Anna Kim?"), never a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from milo.core.ports import Contacts

from .connections import reach

RELATIONS = {
    "mum": "mother", "mom": "mother", "mummy": "mother", "mommy": "mother", "mother": "mother", "mama": "mother",
    "mami": "mother", "mutti": "mother", "mutter": "mother",
    "dad": "father", "daddy": "father", "father": "father", "papa": "father", "papi": "father", "vati": "father",
    "vater": "father",
    "sister": "sister", "schwester": "sister", "brother": "brother", "bruder": "brother",
    "son": "son", "sohn": "son", "daughter": "daughter", "tochter": "daughter",
    "wife": "wife", "frau": "wife", "husband": "husband", "mann": "husband", "partner": "partner",
    "partnerin": "partner", "freund": "partner", "freundin": "partner", "girlfriend": "partner",
    "boyfriend": "partner",
}
"""What the user calls family, in English and German, and the relation the address book keeps it under."""
_MY = re.compile(r"^(?:my|meine?|meiner|meinem|meinen)\s+", re.IGNORECASE)
_PHONE = re.compile(r"^\+?[\d\s\-()./]+$")
_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_MOBILE = re.compile(r"mobil|iphone|cell|handy", re.IGNORECASE)
MAX_NAMES = 3


@dataclass(frozen=True)
class Person:
    name: str
    """As the address book has it, or the number or address when it was said outright."""
    address: str
    """The phone number or address the message or call goes to."""
    said: str
    """What the user called them, without "my" ("Mum", "Anna")."""

    @property
    def nicknamed(self) -> bool:
        """The user called them something other than their name ("Mum" for Jane Doe)."""
        return self.name != self.address and not set(self.said.casefold().split()) <= set(self.name.casefold().split())

    @property
    def short(self) -> str:
        """How Milo names them in a line: what the user called them when it isn't their name ("Mum"), else the
        first name; a number or address as it was said."""
        if self.name == self.address:
            return self.said
        if self.nicknamed:
            return self.said[:1].upper() + self.said[1:]
        return self.name.split()[0]


class NoOne(Exception):
    """Nobody in the address book is called that."""


class Several(Exception):
    """People with different names match: Milo asks which."""

    def __init__(self, names: list[str]):
        super().__init__(", ".join(names))
        self.names = names


class NoAddress(Exception):
    """The one person found has no number and no address."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


def address_in(said: str) -> str:
    """The phone number or address `said` is, as it was said; "" when it is a name."""
    text = said.strip()
    if _EMAIL.match(text):
        return text
    if _PHONE.match(text) and sum(c.isdigit() for c in text) >= 3:
        return " ".join(text.split())
    return ""


def relation_of(said: str) -> str:
    """The relation "Mum", "my sister" or „meine Mama“ means, "" when it names no family."""
    return RELATIONS.get(_MY.sub("", said.strip()).casefold(), "")


async def find(contacts: Contacts, said: str, how: str) -> Person:
    """The one person `said` means, with the number or address for `how` ("message", "phone", "audio", "video").
    Raises NoOne, Several or NoAddress; ToolError when the address book can't be read."""
    relation = relation_of(said)
    wanted = _MY.sub("", said.strip()) if relation else " ".join(said.split())
    found = [c for c in await reach(contacts.find, wanted, relation) or [] if isinstance(c, dict) and c.get("name")]
    people = _merged(_best(found, wanted, relation))
    if not people:
        raise NoOne(said)
    if len(people) > 1:
        raise Several([str(p["name"]) for p in people[:MAX_NAMES]])
    one = people[0]
    address = pick_address(one, how)
    if not address:
        raise NoAddress(str(one["name"]))
    return Person(str(one["name"]), address, wanted)


def _best(found: list[dict], wanted: str, relation: str) -> list[dict]:
    """The closest matches: the relation, then the exact name, then a first name or nickname that is the word said,
    then everyone found."""
    if relation:
        family = [c for c in found if c.get("relation") == relation]
        if family:
            return family
    want = wanted.casefold().split()
    exact = [c for c in found if str(c["name"]).casefold().split() == want
             or str(c.get("nickname") or "").casefold().split() == want]
    if exact:
        return exact
    whole = [c for c in found if all(w in _words(c) for w in want)]
    return whole or found


def _words(contact: dict) -> set[str]:
    return set(f"{contact.get('name', '')} {contact.get('nickname', '')}".casefold().split())


def _merged(found: list[dict]) -> list[dict]:
    """One entry per name: the same person twice (two accounts' cards) is one to the user."""
    by_name: dict[str, dict] = {}
    for c in found:
        key = " ".join(str(c["name"]).casefold().split())
        if key in by_name:
            first = by_name[key]
            first["phones"] = [*first.get("phones", []), *c.get("phones", [])]
            first["emails"] = [*first.get("emails", []), *c.get("emails", [])]
        else:
            by_name[key] = {**c, "phones": list(c.get("phones") or []), "emails": list(c.get("emails") or [])}
    return list(by_name.values())


def pick_address(contact: dict, how: str) -> str:
    """The number or address to use: a mobile number first; then, except for a phone call, an address (messages and
    internet calls reach one); then any other number. A phone call to someone with only an address takes the address,
    and the call goes over the internet."""
    phones = [p for p in contact.get("phones") or [] if _value(p)]
    emails = [e for e in contact.get("emails") or [] if _value(e)]
    mobile = [p for p in phones if _MOBILE.search(str(_label(p)))]
    order = mobile + ([] if how == "phone" else emails) + phones + (emails if how == "phone" else [])
    return _value(order[0]) if order else ""


def _value(entry: Any) -> str:
    return str(entry.get("value") or "").strip() if isinstance(entry, dict) else str(entry or "").strip()


def _label(entry: Any) -> str:
    return str(entry.get("label") or "") if isinstance(entry, dict) else ""
