"""The memory search index: state/memory.sqlite. A cache of the logs; delete it and it is rebuilt.

Full-text search with SQLite FTS5 and vector search, merged by reciprocal rank fusion. Vectors are searched
with NumPy over a matrix held in memory (28 MB for a year of a busy Milo), or with the sqlite-vec extension,
which keeps them on disk but scans 5x slower (33 ms against 7 ms over 6,600 items, measured on the M3).
Blocking and not thread-safe: the brain uses it from its memory thread.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from collections.abc import Collection, Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

import numpy as np

from milo.core.memory import Episode, Fact, Hit, IndexItem
from milo.core.ports import Embedder

from .bilingual import translations
from .when import TIME_WORDS

log = logging.getLogger(__name__)

SCHEMA = 2
RRF_K = 60
CANDIDATES = 50
"""How many hits each of the two searches contributes before fusion."""
EMBED_BATCH = 64

_WORD = re.compile(r"\w+", re.UNICODE)
STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does for from had has have he her his how i if in is it its
me my of on or our she so that the their them then there they this to was we were what when where which who
why will with would you your about any just know tell remember again please milo hey hi ok okay
der die das den dem des ein eine einen einem einer und oder aber ist sind war waren hat habe haben hatte
ich du er sie es wir ihr mir mich dir dich uns euch mein meine dein deine sein seine was wann wo wer wie
warum welche welcher welches im in am an auf aus bei mit nach von vor zu zum zur für über um noch nochmal
mal schon auch nicht kein keine bitte doch denn dass ob wenn weißt weisst sag erinnerst erinnere
""".split())


class MonthlyEpisodes(Protocol):
    def files(self) -> list[Path]: ...
    def between(self, start: datetime, end: datetime) -> list[Episode]: ...


class FactSource(Protocol):
    def current(self) -> list[Fact]: ...


def terms(text: str) -> list[str]:
    """The words of `text` worth searching for: no stopwords, no single letters, each once."""
    return list(dict.fromkeys(w for w in _WORD.findall(text.lower())
                              if len(w) > 1 and w not in STOPWORDS and w not in TIME_WORDS))


def _stem(word: str) -> str:
    """A crude stem for a prefix search: "allergies" finds "allergic", "Geburtstag" finds "Geburtstage"."""
    return word[:max(5, len(word) - 3)] if len(word) >= 7 else word


ANCHORS = (
    "The user said: “What's the weather like?” Milo answered: “Sunny, 18 degrees.”",
    "The user said: “Wie spät ist es?” Milo answered: “Kurz nach drei.”",
    "Task: tidy up the Downloads folder. Result: done.",
    "Task: Finde die Rechnung im Ordner Dokumente. Result: erledigt.",
    "The user likes jazz.", "Der Nutzer fährt gern Fahrrad.", "The user's car is blue.",
    "Mia is the user's neighbour.", "Die Besprechung wurde auf Dienstag verschoben.",
    "The user said: “Tell me something funny.” Milo answered: “Why did the chicken cross the road?”",
    "Looked at Safari: a news page.", "The user prefers short answers.", "Der Nutzer arbeitet von zu Hause.",
    "The user said: “Thanks!” Milo answered: “Anytime.”", "Booked a table for two on Friday.",
    "The user said: “Spiel Musik.” Milo answered: “Das kann ich noch nicht.”",
)
"""Sentences of the kinds memory holds, about nothing in particular: the yardstick for Hit.background."""
ANCHORS_COUNTED = 4


class SqliteMemoryIndex:
    """MemoryIndex. `facts` and `episodes` are the logs it caches; refresh() catches up with them cheaply."""

    def __init__(self, path: Path, embedder: Embedder, facts: FactSource | None = None,
                 episodes: MonthlyEpisodes | None = None, *, vectors: str = "auto"):
        if vectors not in ("auto", "sqlite-vec", "numpy"):
            raise ValueError("vectors must be auto, sqlite-vec or numpy")
        self.path = path
        self.embedder = embedder
        self._facts = facts
        self._episodes = episodes
        self._want_vectors = vectors
        self._db: sqlite3.Connection | None = None
        self.vectors = ""
        """"sqlite-vec" or "numpy", once open."""
        self._matrix: _Matrix | None = None
        self._last_query: tuple[str, np.ndarray] | None = None
        self._anchors: np.ndarray | None = None

    # ---- MemoryIndex

    def upsert(self, items: Sequence[IndexItem]) -> None:
        """Add or replace items. Only text that changed is embedded again."""
        if not items:
            return
        db = self._open()
        known = {id: (n, th) for n, id, th in
                 _chunked_select(db, "SELECT n, id, text_hash FROM items WHERE id IN", [i.id for i in items])}
        fresh = [i for i in items if known.get(i.id, (0, ""))[1] != _text_hash(i)]
        embedded = dict(zip((i.id for i in fresh), self._embed([i.text for i in fresh])))
        with db:
            for item in items:
                vector = embedded.get(item.id)
                if vector is None:
                    vector = self._stored_vector(db, known[item.id][0])
                self._put(db, item, vector)
        if self._matrix is not None:
            self._matrix.stale = True

    def remove(self, ids: Collection[str]) -> None:
        if not ids:
            return
        db = self._open()
        with db:
            for (n,) in _chunked_select(db, "SELECT n FROM items WHERE id IN", list(ids)):
                self._delete(db, n)
        if self._matrix is not None:
            self._matrix.stale = True

    def search(self, query: str, *, kinds: Collection[str] = (), since: datetime | None = None,
               until: datetime | None = None, limit: int = 20) -> list[Hit]:
        db = self._open()
        text = self._text_ranks(db, query, kinds, since, until)
        vector = self._vector_ranks(db, query, kinds, since, until)
        scores: dict[int, float] = {}
        for ranks in (text, vector):
            for rank, n in enumerate(ranks):
                scores[n] = scores.get(n, 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(scores, key=lambda n: -scores[n])[:limit]
        rows = {row[0]: row for row in _chunked_select(db, f"SELECT {_ITEM_COLUMNS} FROM items WHERE n IN", best)}
        text_rank = {n: r for r, n in enumerate(text)}
        vector_rank = {n: (r, s) for r, (n, s) in enumerate(vector.items())}
        background = self._background(query) if vector else 0.0
        hits = []
        for n in best:
            if n not in rows:
                continue
            vr = vector_rank.get(n)
            hits.append(Hit(_item(rows[n]), scores[n], text_rank.get(n), vr[0] if vr else None, vr[1] if vr else 0.0,
                            background))
        return hits

    def rebuild(self) -> None:
        """Start over from the logs: drop every table and index everything again."""
        self.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)
        self.refresh()

    # ---- keeping up with the logs

    def refresh(self, limit: int | None = None) -> int:
        """Index what changed in the logs since last time, at most `limit` items per call (so a search can get in
        between). Returns how many items changed: 0 means the index is up to date. Cheap when nothing changed."""
        db = self._open()
        budget = limit if limit is not None else 1 << 62
        changed = 0
        if self._facts is not None:
            facts = [IndexItem.of_fact(f) for f in self._facts.current()]
            changed += self._sync(db, "kind = 'fact'", (), facts, budget)
        if self._episodes is not None:
            for path in self._episodes.files():
                if changed >= budget:
                    break
                st = path.stat()
                stamp = f"{st.st_size}:{st.st_mtime_ns}"
                key = f"log:{path.name}"
                if self._meta(db, key) == stamp:
                    continue
                start = datetime.strptime(path.stem, "%Y-%m")
                end = datetime(start.year + start.month // 12, start.month % 12 + 1, 1)
                episodes = [IndexItem.of_episode(e) for e in self._episodes.between(start, end)]
                done = self._sync(db, "kind = 'episode' AND at >= ? AND at < ?",
                                  (start.timestamp(), end.timestamp()), episodes, budget - changed)
                changed += done
                if changed < budget:
                    self._set_meta(db, key, stamp)  # all of this month is in
        return changed

    def count(self, kind: str | None = None) -> int:
        db = self._open()
        if kind is None:
            return db.execute("SELECT count(*) FROM items").fetchone()[0]
        return db.execute("SELECT count(*) FROM items WHERE kind=?", (kind,)).fetchone()[0]

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._matrix = None

    def _sync(self, db: sqlite3.Connection, where: str, args: tuple, items: list[IndexItem], limit: int) -> int:
        have = {row[0]: row[1] for row in db.execute(f"SELECT id, hash FROM items WHERE {where}", args)}
        want = {i.id for i in items}
        gone = [id for id in have if id not in want][:limit]
        new = [i for i in items if have.get(i.id) != _hash(i)][:max(0, limit - len(gone))]
        self.remove(gone)
        self.upsert(new)
        return len(gone) + len(new)

    # ---- storage

    def _open(self) -> sqlite3.Connection:
        if self._db is not None:
            return self._db
        try:
            self._db = self._connect()
        except sqlite3.DatabaseError as e:
            log.warning("the memory index was unreadable (%s); building it again", e)
            for suffix in ("", "-wal", "-shm"):
                Path(str(self.path) + suffix).unlink(missing_ok=True)
            self._db = self._connect()
        return self._db

    def _connect(self) -> sqlite3.Connection:
        """Open the database, starting a fresh one if it was built with another layout or embedder.
        It holds what Milo remembers, so its files are the user's only."""
        old = os.umask(0o077)
        try:
            return self._connect_private()
        finally:
            os.umask(old)

    def _connect_private(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        try:
            self.vectors = self._load_vectors(db)
            layout = f"{SCHEMA}:{self.vectors}:{self.embedder.key}:{self.embedder.dimensions}"
            has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
            stored = db.execute("SELECT value FROM meta WHERE key='layout'").fetchone() if has_meta else None
            empty = db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0
            if not empty and (stored is None or stored[0] != layout):
                log.info("memory index was built for %s, now %s: building it again", stored and stored[0], layout)
                db.close()
                for suffix in ("", "-wal", "-shm"):
                    Path(str(self.path) + suffix).unlink(missing_ok=True)
                db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
                self._load_vectors(db)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS items (
                    n INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
                    at REAL NOT NULL, people TEXT NOT NULL, apps TEXT NOT NULL, trusted INTEGER NOT NULL,
                    topic TEXT NOT NULL, source TEXT NOT NULL, hash TEXT NOT NULL, text_hash TEXT NOT NULL,
                    vector BLOB);
                CREATE INDEX IF NOT EXISTS items_kind_at ON items (kind, at);
                CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                    text, people, apps, content='items', content_rowid='n',
                    tokenize="unicode61 remove_diacritics 2", prefix='3');
            """)
            if self.vectors == "sqlite-vec":
                db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS items_vec USING vec0("
                           f"embedding float[{self.embedder.dimensions}] distance_metric=cosine, kind text, at float)")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('layout', ?)", (layout,))
            for suffix in ("", "-wal", "-shm"):
                if Path(str(self.path) + suffix).exists():
                    os.chmod(str(self.path) + suffix, 0o600)
        except Exception:
            db.close()
            raise
        return db

    def _load_vectors(self, db: sqlite3.Connection) -> str:
        if self._want_vectors == "numpy":
            return "numpy"
        import sqlite_vec

        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        return "sqlite-vec"

    def _put(self, db: sqlite3.Connection, item: IndexItem, vector: np.ndarray) -> None:
        old = db.execute("SELECT n FROM items WHERE id=?", (item.id,)).fetchone()
        if old is not None:
            self._delete(db, old[0])
        blob = np.asarray(vector, dtype=np.float32).tobytes()
        cur = db.execute(
            "INSERT INTO items (id, kind, text, at, people, apps, trusted, topic, source, hash, text_hash, vector) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item.id, item.kind, item.text, item.at.timestamp(), _join(item.people), _join(item.apps),
             int(item.trusted), item.topic, item.source, _hash(item), _text_hash(item),
             blob if self.vectors == "numpy" else None))
        n = cur.lastrowid
        db.execute("INSERT INTO items_fts (rowid, text, people, apps) VALUES (?, ?, ?, ?)",
                   (n, item.text, _join(item.people), _join(item.apps)))
        if self.vectors == "sqlite-vec":
            db.execute("INSERT INTO items_vec (rowid, embedding, kind, at) VALUES (?, ?, ?, ?)",
                       (n, blob, item.kind, item.at.timestamp()))

    def _delete(self, db: sqlite3.Connection, n: int) -> None:
        row = db.execute("SELECT text, people, apps FROM items WHERE n=?", (n,)).fetchone()
        if row is None:
            return
        db.execute("INSERT INTO items_fts (items_fts, rowid, text, people, apps) VALUES ('delete', ?, ?, ?, ?)", (n, *row))
        if self.vectors == "sqlite-vec":
            db.execute("DELETE FROM items_vec WHERE rowid=?", (n,))
        db.execute("DELETE FROM items WHERE n=?", (n,))

    def _stored_vector(self, db: sqlite3.Connection, n: int) -> np.ndarray:
        table = "items_vec" if self.vectors == "sqlite-vec" else "items"
        column = "embedding" if self.vectors == "sqlite-vec" else "vector"
        row = db.execute(f"SELECT {column} FROM {table} WHERE rowid=?", (n,)).fetchone()
        return np.frombuffer(row[0], dtype=np.float32)

    def _meta(self, db: sqlite3.Connection, key: str) -> str | None:
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, db: sqlite3.Connection, key: str, value: str) -> None:
        db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def _embed(self, texts: list[str]) -> np.ndarray:
        parts = [self.embedder.embed(texts[i:i + EMBED_BATCH]) for i in range(0, len(texts), EMBED_BATCH)]
        return np.concatenate(parts) if parts else np.zeros((0, self.embedder.dimensions), dtype=np.float32)

    # ---- the two searches

    def _text_ranks(self, db: sqlite3.Connection, query: str, kinds: Collection[str], since: datetime | None,
                    until: datetime | None) -> list[int]:
        words = terms(query)
        if not words:
            return []
        words = list(dict.fromkeys([*words, *(t for w in words for t in translations(w))]))
        match = " OR ".join(f'"{_stem(w)}"*' if len(w) >= 4 else f'"{w}"' for w in words)
        sql = ("SELECT items.n FROM items_fts JOIN items ON items.n = items_fts.rowid "
               "WHERE items_fts MATCH ?" + _filters(kinds, since, until) + " ORDER BY bm25(items_fts) LIMIT ?")
        return [n for (n,) in db.execute(sql, (match, *_filter_args(kinds, since, until), CANDIDATES))]

    def _vector_ranks(self, db: sqlite3.Connection, query: str, kinds: Collection[str],
                      since: datetime | None, until: datetime | None) -> dict[int, float]:
        """Row -> cosine similarity, best first."""
        if not query.strip():
            return {}
        q = self._query_vector(query)
        if self.vectors == "sqlite-vec":
            kind_list = list(kinds)
            where = ""
            args: list = [q.tobytes(), CANDIDATES]
            if len(kind_list) == 1:
                where += " AND kind = ?"
                args.append(kind_list[0])
            if since is not None:
                where += " AND at >= ?"
                args.append(since.timestamp())
            if until is not None:
                where += " AND at < ?"
                args.append(until.timestamp())
            rows = db.execute(f"SELECT rowid, distance FROM items_vec WHERE embedding MATCH ? AND k = ?{where} "
                              "ORDER BY distance", args).fetchall()
            if len(kind_list) > 1:
                allowed = {n for (n,) in _chunked_select(db, f"SELECT n FROM items WHERE kind IN ({','.join('?' * len(kind_list))}) AND n IN",
                                                          [r[0] for r in rows], prefix_args=kind_list)}
                rows = [r for r in rows if r[0] in allowed]
            return {n: 1.0 - float(d) for n, d in rows}
        matrix = self._numpy(db)
        if not len(matrix.rows):
            return {}
        mask = np.ones(len(matrix.rows), dtype=bool)
        if kinds:
            mask &= np.isin(matrix.kinds, list(kinds))
        if since is not None:
            mask &= matrix.at >= since.timestamp()
        if until is not None:
            mask &= matrix.at < until.timestamp()
        sims = matrix.vectors @ q
        sims[~mask] = -2.0
        top = np.argsort(-sims)[:CANDIDATES]
        return {int(matrix.rows[i]): float(sims[i]) for i in top if sims[i] > -2.0}

    def _query_vector(self, query: str) -> np.ndarray:
        """The query's vector. A turn often searches twice (everything, then its time window): embed it once."""
        if self._last_query is None or self._last_query[0] != query:
            self._last_query = (query, self.embedder.embed([query], query=True)[0].astype(np.float32))
        return self._last_query[1]

    def _background(self, query: str) -> float:
        """How similar the query is to text that has nothing to do with it: the mean of its best few matches among
        ANCHORS. A short "Erzähl mir einen Witz." sits at 0.83 against everything, a question about Anna at 0.74."""
        if self._anchors is None:
            self._anchors = self.embedder.embed(ANCHORS).astype(np.float32)
        sims = np.sort(self._anchors @ self._query_vector(query))
        return float(sims[-ANCHORS_COUNTED:].mean())

    def _numpy(self, db: sqlite3.Connection) -> _Matrix:
        if self._matrix is None or self._matrix.stale:
            self._matrix = _Matrix.load(db, self.embedder.dimensions)
        return self._matrix


class _Matrix:
    """Every vector in memory, for the NumPy search: 10k items of 384 floats are 15 MB and a 2 ms product."""

    def __init__(self, rows: np.ndarray, kinds: np.ndarray, at: np.ndarray, vectors: np.ndarray):
        self.rows, self.kinds, self.at, self.vectors = rows, kinds, at, vectors
        self.stale = False

    @classmethod
    def load(cls, db: sqlite3.Connection, dims: int) -> _Matrix:
        data = db.execute("SELECT n, kind, at, vector FROM items WHERE vector IS NOT NULL").fetchall()
        if not data:
            return cls(np.zeros(0, dtype=np.int64), np.zeros(0, dtype=object), np.zeros(0), np.zeros((0, dims), dtype=np.float32))
        rows, kinds, at, blobs = zip(*data)
        vectors = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(rows), dims)
        return cls(np.array(rows), np.array(kinds, dtype=object), np.array(at), vectors)


_ITEM_COLUMNS = "n, id, kind, text, at, people, apps, trusted, topic, source"


def _item(row: tuple) -> IndexItem:
    _, id, kind, text, at, people, apps, trusted, topic, source = row
    return IndexItem(id, kind, text, datetime.fromtimestamp(at), _split(people), _split(apps), bool(trusted), topic,
                     source)


def _filters(kinds: Collection[str], since: datetime | None, until: datetime | None) -> str:
    sql = ""
    if kinds:
        sql += f" AND items.kind IN ({','.join('?' * len(kinds))})"
    if since is not None:
        sql += " AND items.at >= ?"
    if until is not None:
        sql += " AND items.at < ?"
    return sql


def _filter_args(kinds: Collection[str], since: datetime | None, until: datetime | None) -> list:
    return [*kinds, *([since.timestamp()] if since is not None else []), *([until.timestamp()] if until is not None else [])]


def _chunked_select(db: sqlite3.Connection, sql: str, values: list, *, prefix_args: Iterable = ()) -> Iterable[tuple]:
    """`sql` ends in "IN"; runs it over `values` in chunks below SQLite's variable limit."""
    prefix = list(prefix_args)
    for start in range(0, len(values), 500):
        chunk = values[start:start + 500]
        yield from db.execute(f"{sql} ({','.join('?' * len(chunk))})", (*prefix, *chunk))


def _join(values: tuple[str, ...]) -> str:
    return "\n".join(values)


def _split(value: str) -> tuple[str, ...]:
    return tuple(v for v in value.split("\n") if v)


def _hash(item: IndexItem) -> str:
    data = [item.kind, item.text, item.at.isoformat(), item.people, item.apps, item.trusted, item.topic, item.source]
    return hashlib.blake2b(json.dumps(data, default=list).encode(), digest_size=12).hexdigest()


def _text_hash(item: IndexItem) -> str:
    return hashlib.blake2b(item.text.encode(), digest_size=12).hexdigest()


