"""Persistent euro-denominated game economy with official card metadata.

Prices, resale estimates and pull probabilities are game estimates. Physical
pack sizes and slots follow era profiles; official rarity/variant metadata
never comes from a hash or a randomly assigned rarity.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import random
import sqlite3
from threading import RLock
import time
from typing import cast, final
from urllib.parse import urlsplit, urlunsplit

from pokenux.services.localization import language, text
from pokenux.models.tcg.card import Card
from pokenux.models.tcg.serie import Serie
from pokenux.models.tcg.set import Set
from pokenux.services.games.booster_rules import (
    BoosterRules,
    RarityGroup,
    estimated_card_value,
    estimated_price,
    is_anniversary_pikachu,
    rarity_group,
    rules_for_set,
    supports_booster,
)


class SimulatorError(ValueError):
    """A recoverable gameplay or saved-game error, ready to show in the UI."""


def format_euros(cents: int) -> str:
    """Format integer cents without floating-point rounding."""
    sign = "−" if cents < 0 else ""
    euros, remainder = divmod(abs(cents), 100)
    whole = f"{euros:,}".replace(",", "\u202f")
    return (
        f"{sign}{whole},{remainder:02d} €"
        if language() == "fr"
        else f"€{sign}{euros:,}.{remainder:02d}"
    )


def finish_label(finish: str) -> str:
    """Translate presentation only; persisted finish keys remain unchanged."""
    return {
        "Normale": text("Normale", "Normal"),
        "Reverse": "Reverse",
        "Holographique": text("Holographique", "Holographic"),
    }.get(finish, finish)


def rarity_label(rarity: str) -> str:
    return text("Non vérifiée", "Unverified") if rarity == "Non vérifiée" else rarity


@dataclass(frozen=True)
class BoosterOffer:
    set_id: str
    name: str
    serie_name: str
    price: int
    available_cards: int
    card_count: int = 10
    composition: str = ""
    price_note: str = "Prix estimatif du jeu"


@dataclass(frozen=True)
class SimulatorState:
    balance: int
    work_level: int
    work_income: int
    upgrade_cost: int
    clicks: int
    boosters_opened: int
    cards_owned: int
    cards_sold: int
    collection_value: int
    work_ready_in: float = 0.0
    migration_notice: str = ""


@dataclass(frozen=True)
class WorkResult:
    earned: int
    state: SimulatorState


@dataclass(frozen=True)
class OwnedCard:
    card_id: str
    name: str
    image: str
    set_id: str
    set_name: str
    rarity: str
    value: int
    quantity: int
    finish: str = "Normale"
    source_card_id: str = ""


@dataclass(frozen=True)
class BoosterOpening:
    offer: BoosterOffer
    cards: tuple[OwnedCard, ...]
    state: SimulatorState


@dataclass(frozen=True)
class _Catalogue:
    card_set: Set
    serie_name: str
    rules: BoosterRules
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class _Pull:
    card: Card
    finish: str

    @property
    def key(self) -> str:
        suffix = {"Normale": "", "Reverse": "::reverse", "Holographique": "::holo"}
        return self.card.id + suffix[self.finish]


_SCHEMA_VERSION = 2
_WORK_DELAY = 2.0
_MAX_WORK_LEVEL = 10
_MIGRATION_NOTICE = "Ancienne sauvegarde convertie : 1 P$ = 0,01 €. Les anciennes raretés sont à vérifier."
_PREMIUM_GROUPS: tuple[RarityGroup, ...] = (
    "double",
    "ultra",
    "illustration",
    "special",
    "hyper",
)


def _image_url(image: str) -> str:
    if not image:
        return ""
    try:
        url = urlsplit(image)
    except ValueError:
        return ""
    path = url.path.rstrip("/")
    if not path.lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".gif")):
        path += "/high.png"
    return urlunsplit((url.scheme, url.netloc, path, url.query, url.fragment))


@final
class SimulatorService:
    """Serialize purchases, work, upgrades and sales in SQLite transactions.

    Currency is always integer cents. Saved card snapshots stay unchanged while
    display names follow the current catalogue. Normal, reverse and holographic copies have
    distinct sale keys but share a canonical source_card_id.
    """

    def __init__(
        self,
        series: list[Serie],
        db_path: str | Path | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if db_path is None:
            from pokenux.services import user_data

            db_path = user_data.path / "simulator.sqlite3"
        self.db_path: Path | str = (
            ":memory:" if db_path == ":memory:" else Path(db_path)
        )
        self._rng = rng if rng is not None else random.Random()
        self._clock = clock if clock is not None else time.time
        self._lock = RLock()
        self._closed = False
        self._migration_notice = ""
        self._catalogue = self._make_catalogue(series)
        self._offers: dict[str, BoosterOffer] = {}
        try:
            if isinstance(self.db_path, Path):
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                self.db_path, timeout=10, isolation_level=None, check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._initialize()
        except (OSError, sqlite3.Error, SimulatorError) as error:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise SimulatorError(
                text(
                    "Impossible d’ouvrir la sauvegarde du simulateur.",
                    "Could not open the simulator save.",
                )
            ) from error

    @staticmethod
    def _make_catalogue(series: list[Serie]) -> dict[str, _Catalogue]:
        catalogue: dict[str, _Catalogue] = {}
        for serie in series:
            for card_set in serie.sets:
                if not card_set.id or not supports_booster(card_set, serie.id):
                    continue
                cards = tuple(
                    {
                        card.id: card
                        for card in card_set.cards
                        if card.id and card.name.strip() and card.set_id == card_set.id
                    }.values()
                )
                if cards:
                    _ = catalogue.setdefault(
                        card_set.id,
                        _Catalogue(
                            replace(card_set, serie_id=serie.id),
                            serie.name,
                            rules_for_set(card_set, serie.id),
                            cards,
                        ),
                    )
        return catalogue

    def set_catalogue(self, series: list[Serie]) -> None:
        """Swap display/catalogue data without replacing the wallet or inventory."""
        updated = self._make_catalogue(series)
        previous, previous_offers = self._catalogue, self._offers
        try:
            with self._transaction() as connection:
                self._catalogue = updated
                self._offers = {}
                self._refresh_catalogue_offers(connection)
        except Exception:
            self._catalogue, self._offers = previous, previous_offers
            raise

    def display_card(self, owned: OwnedCard) -> OwnedCard:
        """Use the current catalogue's names while retaining saved identity/value."""
        entry = self._catalogue.get(owned.set_id)
        if entry is None:
            return owned
        source_id = owned.source_card_id or owned.card_id.split("::", 1)[0]
        card = next((card for card in entry.cards if card.id == source_id), None)
        if card is None:
            return owned
        return replace(
            owned,
            name=card.name,
            set_name=entry.card_set.name,
            image=_image_url(card.image) or owned.image,
            rarity=card.rarity or owned.rarity,
        )

    @property
    def extensions(self) -> list[BoosterOffer]:
        return sorted(
            (
                replace(
                    offer,
                    composition=self._catalogue[offer.set_id].rules.composition,
                    price_note=text("Prix estimatif du jeu", "Estimated game price"),
                )
                for offer in self._offers.values()
            ),
            key=lambda offer: (offer.price, offer.set_id),
        )

    @contextmanager
    def _transaction(
        self, *, read_only: bool = False
    ) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            if self._closed:
                raise SimulatorError(
                    text("Cette sauvegarde est fermée.", "This save is closed.")
                )
            try:
                _ = self._connection.execute(
                    "BEGIN" if read_only else "BEGIN IMMEDIATE"
                )
                yield self._connection
                _ = self._connection.execute("COMMIT")
            except BaseException as error:
                if self._connection.in_transaction:
                    _ = self._connection.execute("ROLLBACK")
                if isinstance(error, sqlite3.Error):
                    raise SimulatorError(
                        text(
                            "La sauvegarde est indisponible. Réessaie.",
                            "The save is unavailable. Please try again.",
                        )
                    ) from error
                raise

    def _initialize(self) -> None:
        with self._transaction() as connection:
            version = cast(int, connection.execute("PRAGMA user_version").fetchone()[0])
            if version > _SCHEMA_VERSION:
                raise SimulatorError(
                    text(
                        "Cette sauvegarde nécessite une version plus récente.",
                        "This save requires a newer application version.",
                    )
                )
            existed = (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='simulator_account'"
                ).fetchone()
                is not None
            )
            _ = connection.execute("""CREATE TABLE IF NOT EXISTS simulator_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance INTEGER NOT NULL CHECK (balance >= 0),
                work_level INTEGER NOT NULL DEFAULT 0 CHECK (work_level >= 0),
                clicks INTEGER NOT NULL DEFAULT 0 CHECK (clicks >= 0),
                boosters_opened INTEGER NOT NULL DEFAULT 0 CHECK (boosters_opened >= 0),
                cards_sold INTEGER NOT NULL DEFAULT 0 CHECK (cards_sold >= 0),
                work_next_at REAL NOT NULL DEFAULT 0
            )""")
            _ = connection.execute("""CREATE TABLE IF NOT EXISTS simulator_inventory (
                card_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                value INTEGER NOT NULL CHECK (value > 0),
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            )""")
            _ = connection.execute(
                "CREATE TABLE IF NOT EXISTS simulator_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            if version < _SCHEMA_VERSION:
                columns = {
                    cast(str, row["name"])
                    for row in cast(
                        list[sqlite3.Row],
                        connection.execute(
                            "PRAGMA table_info(simulator_account)"
                        ).fetchall(),
                    )
                }
                if "work_next_at" not in columns:
                    _ = connection.execute(
                        "ALTER TABLE simulator_account ADD COLUMN work_next_at REAL NOT NULL DEFAULT 0"
                    )
                _ = connection.execute(
                    "UPDATE simulator_account SET work_level = MIN(work_level, 10)"
                )
                _ = connection.execute("DROP TABLE IF EXISTS simulator_prices")
                _ = connection.execute("""CREATE TABLE simulator_prices (
                    set_id TEXT PRIMARY KEY, price INTEGER NOT NULL CHECK (price > 0),
                    pricing_version INTEGER NOT NULL DEFAULT 2
                )""")
                if existed:
                    rows = cast(
                        list[sqlite3.Row],
                        connection.execute(
                            "SELECT * FROM simulator_inventory"
                        ).fetchall(),
                    )
                    for row in rows:
                        owned = self._owned(row)
                        payload = {
                            "name": owned.name,
                            "image": owned.image,
                            "set_id": owned.set_id,
                            "set_name": owned.set_name,
                            "rarity": "Non vérifiée",
                            "finish": owned.finish,
                            "source_card_id": owned.source_card_id,
                            "legacy": True,
                        }
                        _ = connection.execute(
                            "UPDATE simulator_inventory SET payload = ?, value = 3 WHERE card_id = ?",
                            (json.dumps(payload, ensure_ascii=False), owned.card_id),
                        )
                    _ = connection.execute(
                        "INSERT OR REPLACE INTO simulator_meta (key, value) VALUES ('migration_notice', ?)",
                        (_MIGRATION_NOTICE,),
                    )
                _ = connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            _ = connection.execute(
                "INSERT OR IGNORE INTO simulator_account (id, balance) VALUES (1, 500)"
            )
            notice = cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT value FROM simulator_meta WHERE key='migration_notice'"
                ).fetchone(),
            )
            if notice is not None:
                self._migration_notice = cast(str, notice["value"])
            self._refresh_catalogue_offers(connection, revalue_legacy=True)

    def _refresh_catalogue_offers(
        self, connection: sqlite3.Connection, *, revalue_legacy: bool = False
    ) -> None:
        for set_id, entry in self._catalogue.items():
            price = estimated_price(entry.card_set, entry.card_set.serie_id)
            _ = connection.execute(
                "INSERT INTO simulator_prices (set_id, price) VALUES (?, ?) ON CONFLICT(set_id) DO NOTHING",
                (set_id, price),
            )
            saved = cast(
                sqlite3.Row,
                connection.execute(
                    "SELECT price FROM simulator_prices WHERE set_id = ?", (set_id,)
                ).fetchone(),
            )
            self._offers[set_id] = BoosterOffer(
                set_id,
                entry.card_set.name,
                entry.serie_name,
                cast(int, saved["price"]),
                len(entry.cards),
                entry.rules.card_count,
                entry.rules.composition,
            )
            if revalue_legacy:
                self._revalue_legacy(connection, set_id)

    def _now(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value) or value < 0:
            raise SimulatorError(
                text(
                    "L’horloge du simulateur est indisponible.",
                    "The simulator clock is unavailable.",
                )
            )
        return value

    def _state(
        self, connection: sqlite3.Connection, *, now: float | None = None
    ) -> SimulatorState:
        account = cast(
            sqlite3.Row,
            connection.execute(
                "SELECT * FROM simulator_account WHERE id = 1"
            ).fetchone(),
        )
        inventory = cast(
            sqlite3.Row,
            connection.execute("""SELECT
            COALESCE(SUM(quantity), 0) AS owned,
            COALESCE(SUM(quantity * value), 0) AS worth FROM simulator_inventory""").fetchone(),
        )
        level = cast(int, account["work_level"])
        return SimulatorState(
            balance=cast(int, account["balance"]),
            work_level=level,
            work_income=5 + min(level, _MAX_WORK_LEVEL),
            upgrade_cost=2500 * 2**level if level < _MAX_WORK_LEVEL else 0,
            clicks=cast(int, account["clicks"]),
            boosters_opened=cast(int, account["boosters_opened"]),
            cards_owned=cast(int, inventory["owned"]),
            cards_sold=cast(int, account["cards_sold"]),
            collection_value=cast(int, inventory["worth"]),
            work_ready_in=max(
                0.0,
                cast(float, account["work_next_at"])
                - (self._now() if now is None else now),
            ),
            migration_notice=text(
                _MIGRATION_NOTICE,
                "Old save converted: 1 P$ = €0.01. Previous rarities need verification.",
            )
            if self._migration_notice == _MIGRATION_NOTICE
            else self._migration_notice,
        )

    def snapshot(self) -> SimulatorState:
        with self._transaction(read_only=True) as connection:
            return self._state(connection)

    def work(self) -> WorkResult:
        with self._transaction() as connection:
            now = self._now()
            state = self._state(connection, now=now)
            if state.work_ready_in > 0:
                raise SimulatorError(
                    text(
                        f"Travail trop rapide : attends encore {state.work_ready_in:.1f} s.",
                        f"Too soon to work: wait another {state.work_ready_in:.1f} s.",
                    )
                )
            _ = connection.execute(
                "UPDATE simulator_account SET balance = balance + ?, clicks = clicks + 1, work_next_at = ? WHERE id = 1",
                (state.work_income, now + _WORK_DELAY),
            )
            return WorkResult(state.work_income, self._state(connection, now=now))

    def upgrade_work(self) -> SimulatorState:
        with self._transaction() as connection:
            state = self._state(connection)
            if state.work_level >= _MAX_WORK_LEVEL:
                raise SimulatorError(
                    text(
                        "Tu as atteint le niveau maximum de formation.",
                        "You have reached the maximum training level.",
                    )
                )
            if state.balance < state.upgrade_cost:
                raise SimulatorError(
                    text(
                        f"Il te manque {format_euros(state.upgrade_cost - state.balance)} pour la formation.",
                        f"You need {format_euros(state.upgrade_cost - state.balance)} more for training.",
                    )
                )
            _ = connection.execute(
                "UPDATE simulator_account SET balance = balance - ?, work_level = work_level + 1 WHERE id = 1",
                (state.upgrade_cost,),
            )
            return self._state(connection)

    def cards_for_set(self, set_id: str) -> list[Card]:
        with self._lock:
            entry = self._catalogue.get(set_id)
            if entry is None:
                raise SimulatorError(
                    text(
                        "Cette extension n’est pas disponible.",
                        "This set is unavailable.",
                    )
                )
            return [
                replace(card, variants=dict(card.variants), types=list(card.types))
                for card in entry.cards
            ]

    def set_cards(self, set_id: str, cards: list[Card]) -> None:
        with self._lock:
            previous = self._catalogue.get(set_id)
            if previous is None:
                raise SimulatorError(
                    text(
                        "Cette extension n’est pas disponible.",
                        "This set is unavailable.",
                    )
                )
            replacements = {card.id: card for card in cards}
            original_ids = {card.id for card in previous.cards}
            if any(
                card.set_id != set_id or card.id not in original_ids for card in cards
            ):
                raise SimulatorError(
                    text(
                        "Les métadonnées ne correspondent pas à cette extension.",
                        "The metadata does not match this set.",
                    )
                )
            self._catalogue[set_id] = replace(
                previous,
                cards=tuple(replacements.get(card.id, card) for card in previous.cards),
            )
            try:
                with self._transaction() as connection:
                    self._revalue_legacy(connection, set_id)
            except BaseException:
                self._catalogue[set_id] = previous
                raise

    @staticmethod
    def _normal_pull(card: Card, rules: BoosterRules) -> _Pull | None:
        group = rarity_group(card)
        if group is None:
            return None
        if rules.era == "anniversary":
            # Pokémon specifies an all-foil booster, whereas TCGdex explicitly
            # marks its common/rare cards normal-only. Override drawn finishes
            # for this product without rewriting the official metadata/cache.
            # https://www.pokemon.com/fr/news/jcc-pokemon-produits-30-anniversaire
            return _Pull(card, "Holographique")
        if rules.era == "anniversary_classic":
            return (
                _Pull(card, "Holographique")
                if card.variants.get("holo") is True
                else None
            )
        if group in {"rare", "holo", *_PREMIUM_GROUPS} and rules.era == "modern":
            if card.variants.get("holo") is True:
                return _Pull(card, "Holographique")
            if card.variants.get("holo") is False:
                return None
        if card.variants.get("normal") is True:
            return _Pull(card, "Normale")
        if card.variants.get("holo") is True:
            return _Pull(card, "Holographique")
        if card.variants and card.variants.get("normal") is False:
            return None
        if group in {"holo", *_PREMIUM_GROUPS}:
            return _Pull(card, "Holographique")
        if group == "rare":
            if rules.era == "vintage":
                return None
            return _Pull(card, "Holographique" if rules.era == "modern" else "Normale")
        return _Pull(card, "Normale")

    @staticmethod
    def _reverse_pull(card: Card) -> _Pull | None:
        if rarity_group(card) not in {"common", "uncommon", "rare", "holo"}:
            return None
        if card.variants.get("reverse") is False:
            return None
        return _Pull(card, "Reverse")

    def _pools(self, set_id: str) -> dict[RarityGroup, list[_Pull]]:
        entry = self._catalogue[set_id]
        pools: dict[RarityGroup, list[_Pull]] = {
            group: []
            for group in (
                "common",
                "uncommon",
                "rare",
                "holo",
                *_PREMIUM_GROUPS,
                "energy",
            )
        }
        for card in entry.cards:
            group = rarity_group(card)
            if not card.rarity.strip() or group is None:
                raise SimulatorError(
                    text(
                        "Les raretés officielles de cette extension doivent être chargées avant l’achat.",
                        "Load this set’s official rarities before buying a booster.",
                    )
                )
            pull = self._normal_pull(card, entry.rules)
            if pull is None:
                if (
                    group == "rare"
                    and entry.rules.era == "vintage"
                    and not card.variants
                ):
                    raise SimulatorError(
                        text(
                            "Les finitions officielles de cette extension ancienne doivent être chargées.",
                            "Load this vintage set’s official finishes first.",
                        )
                    )
                continue
            if group == "rare" and pull.finish == "Holographique":
                group = "holo"
            pools[group].append(pull)
            if (
                group == "rare"
                and card.variants.get("holo") is True
                and entry.rules.era != "modern"
            ):
                pools["holo"].append(_Pull(card, "Holographique"))
        if entry.rules.era == "anniversary":
            eligible = [
                pull
                for group, pool in pools.items()
                if group != "energy"
                for pull in pool
            ]
            pikachu = [pull for pull in eligible if is_anniversary_pikachu(pull.card)]
            if (
                not pikachu
                or len(eligible) - len(pikachu) < entry.rules.special_foil - 1
            ):
                raise SimulatorError(
                    text(
                        "Ce booster anniversaire nécessite un Pikachu et quatre autres cartes distinctes.",
                        "This anniversary booster requires a Pikachu and four other distinct cards.",
                    )
                )
            return pools
        if entry.rules.special_foil:
            eligible = [
                pull
                for group in ("rare", "holo", "common", "uncommon")
                for pull in pools[group]
                if pull.finish == "Holographique"
                or pull.card.variants.get("holo") is True
            ]
            if len(eligible) < entry.rules.special_foil or any(
                pools[group] for group in _PREMIUM_GROUPS
            ):
                raise SimulatorError(
                    text(
                        "Cette extension spéciale n’a pas de profil de booster compatible.",
                        "This special set has no compatible booster profile.",
                    )
                )
            return pools
        common_required = entry.rules.common
        if entry.rules.energy and len(pools["energy"]) < entry.rules.energy:
            common_required += entry.rules.energy
        if (
            len(pools["common"]) < common_required
            or len(pools["uncommon"]) < entry.rules.uncommon
            or not (pools["rare"] or pools["holo"])
        ):
            raise SimulatorError(
                text(
                    "Cette extension ne contient pas assez de cartes pour respecter les emplacements du booster.",
                    "This set has too few cards to fill the required booster slots.",
                )
            )
        reverse = [card for card in entry.cards if self._reverse_pull(card) is not None]
        if len(reverse) < entry.rules.reverse:
            raise SimulatorError(
                text(
                    "Les finitions Reverse disponibles sont insuffisantes pour ce booster.",
                    "There are not enough available Reverse finishes for this booster.",
                )
            )
        return pools

    def metadata_ready(self, set_id: str) -> bool:
        with self._lock:
            if set_id not in self._catalogue:
                return False
            try:
                _ = self._pools(set_id)
                return True
            except SimulatorError:
                return False

    def _weighted_pick(
        self, groups: list[tuple[list[_Pull], float]], used: set[str]
    ) -> _Pull:
        available = [
            ([pull for pull in pool if pull.key not in used], weight)
            for pool, weight in groups
        ]
        available = [
            (pool, weight) for pool, weight in available if pool and weight > 0
        ]
        if not available:
            raise SimulatorError(
                text(
                    "Le booster ne peut pas être complété sans doublon de finition.",
                    "This booster cannot be completed without a duplicate finish.",
                )
            )
        pool = self._rng.choices(
            [pool for pool, _ in available],
            weights=[weight for _, weight in available],
            k=1,
        )[0]
        pull = self._rng.choice(pool)
        used.add(pull.key)
        return pull

    def _draw(self, offer: BoosterOffer) -> list[_Pull]:
        entry = self._catalogue[offer.set_id]
        rules = entry.rules
        pools = self._pools(offer.set_id)
        used: set[str] = set()
        drawn: list[_Pull] = []
        if rules.era == "anniversary":
            pikachu = [
                pull for pull in pools["hyper"] if is_anniversary_pikachu(pull.card)
            ]
            other_hyper = [
                pull for pull in pools["hyper"] if not is_anniversary_pikachu(pull.card)
            ]
            # One guaranteed Pikachu plus four foil draws. These weights are
            # game estimates; this profile does not mix in the Classic subset.
            groups = [
                (pools["common"] + pools["uncommon"], 60),
                (pools["rare"] + pools["holo"], 25),
                (pools["double"], 8),
                (pools["ultra"], 3),
                (pools["illustration"], 3),
                (pools["special"], 0.8),
                (other_hyper, 0.2),
            ]
            drawn = [
                self._weighted_pick(groups, used) for _ in range(rules.special_foil - 1)
            ]
            drawn.append(self._weighted_pick([(pikachu, 1)], used))
            return drawn
        if rules.special_foil:
            pool = [
                replace(pull, finish="Holographique")
                for group in ("common", "uncommon", "rare", "holo")
                for pull in pools[group]
                if pull.finish == "Holographique"
                or pull.card.variants.get("holo") is True
            ]
            return [
                self._weighted_pick([(pool, 1)], used)
                for _ in range(rules.special_foil)
            ]
        common_slots = rules.common
        if rules.energy and len(pools["energy"]) < rules.energy:
            common_slots += rules.energy
        for group, count in (("common", common_slots), ("uncommon", rules.uncommon)):
            drawn.extend(
                self._weighted_pick([(pools[cast(RarityGroup, group)], 1)], used)
                for _ in range(count)
            )
        if rules.energy and common_slots == rules.common:
            drawn.extend(
                self._weighted_pick([(pools["energy"], 1)], used)
                for _ in range(rules.energy)
            )
        reverse_pools: dict[RarityGroup, list[_Pull]] = {
            group: [] for group in ("common", "uncommon", "rare", "holo")
        }
        for card in entry.cards:
            pull = self._reverse_pull(card)
            if pull is not None:
                reverse_pools[cast(RarityGroup, rarity_group(card))].append(pull)
        for _ in range(rules.reverse):
            groups = [
                (reverse_pools[group], weight)
                for group, weight in cast(
                    tuple[tuple[RarityGroup, float], ...],
                    (("common", 60), ("uncommon", 30), ("rare", 8), ("holo", 2)),
                )
            ]
            # Modern illustration cards occupy a foil slot, rather than
            # replacing one of the guaranteed common/uncommon slots.
            if rules.era == "modern":
                groups.append((pools["illustration"], 4))
            drawn.append(self._weighted_pick(groups, used))
        if rules.era == "modern":
            # One basic rare weight, irrespective of TCGdex using Rare or
            # Holo Rare labels. These percentages are game estimates, and
            # absent premium groups are omitted before normalization.
            drawn.append(
                self._weighted_pick(
                    [
                        (pools["rare"] + pools["holo"], 74.3),
                        (pools["double"], 18),
                        (pools["ultra"], 6),
                        (pools["special"], 1),
                        (pools["hyper"], 0.7),
                    ],
                    used,
                )
            )
            return drawn
        weights: dict[RarityGroup, float] = (
            {
                "rare": 70,
                "holo": 28,
                "double": 1,
                "ultra": 0.7,
                "illustration": 0.1,
                "special": 0.1,
                "hyper": 0.1,
            }
            if rules.era == "vintage"
            else {
                "rare": 65,
                "holo": 22,
                "double": 7,
                "ultra": 3,
                "illustration": 1.5,
                "special": 1,
                "hyper": 0.5,
            }
        )
        drawn.append(
            self._weighted_pick(
                [(pools[group], weight) for group, weight in weights.items()], used
            )
        )
        return drawn

    @staticmethod
    def _owned(row: sqlite3.Row, *, quantity: int | None = None) -> OwnedCard:
        try:
            raw = cast(object, json.loads(cast(str, row["payload"])))
            if not isinstance(raw, dict):
                raise ValueError("Invalid inventory payload")
            data = cast(dict[str, object], raw)
            fields = ("name", "image", "set_id", "set_name", "rarity")
            if any(not isinstance(data.get(field), str) for field in fields):
                raise ValueError("Invalid inventory metadata")
            card_id = cast(str, row["card_id"])
            finish = data.get("finish", "Normale")
            if finish not in {"Normale", "Reverse", "Holographique"}:
                raise ValueError("Invalid finish")
            source_id = data.get("source_card_id") or card_id.split("::", 1)[0]
            if not isinstance(source_id, str):
                raise ValueError("Invalid source ID")
            return OwnedCard(
                card_id,
                cast(str, data["name"]),
                cast(str, data["image"]),
                cast(str, data["set_id"]),
                cast(str, data["set_name"]),
                cast(str, data["rarity"]),
                cast(int, row["value"]),
                quantity if quantity is not None else cast(int, row["quantity"]),
                cast(str, finish),
                source_id,
            )
        except (ValueError, TypeError, KeyError) as error:
            raise SimulatorError(
                text(
                    "La collection sauvegardée est illisible.",
                    "The saved collection cannot be read.",
                )
            ) from error

    def _revalue_legacy(self, connection: sqlite3.Connection, set_id: str) -> None:
        entry = self._catalogue[set_id]
        cards = {card.id: card for card in entry.cards}
        rows = cast(
            list[sqlite3.Row],
            connection.execute("SELECT * FROM simulator_inventory").fetchall(),
        )
        for row in rows:
            raw = cast(object, json.loads(cast(str, row["payload"])))
            if not isinstance(raw, dict):
                raise SimulatorError(
                    text(
                        "La collection sauvegardée est illisible.",
                        "The saved collection cannot be read.",
                    )
                )
            data = cast(dict[str, object], raw)
            if not data.get("legacy") or data.get("set_id") != set_id:
                continue
            owned = self._owned(row)
            card = cards.get(owned.source_card_id)
            if card is None or not card.rarity.strip():
                continue
            pull = self._normal_pull(card, entry.rules)
            if pull is None:
                continue
            data.update(
                {
                    "rarity": card.rarity,
                    "finish": pull.finish,
                    "source_card_id": card.id,
                    "legacy": False,
                }
            )
            payload = json.dumps(data, ensure_ascii=False)
            value = estimated_card_value(card, pull.finish, entry.rules.era)
            if pull.key != owned.card_id:
                _ = connection.execute(
                    "DELETE FROM simulator_inventory WHERE card_id = ?",
                    (owned.card_id,),
                )
                _ = connection.execute(
                    "INSERT INTO simulator_inventory (card_id, payload, value, quantity) VALUES (?, ?, ?, ?) ON CONFLICT(card_id) DO UPDATE SET quantity = quantity + excluded.quantity",
                    (pull.key, payload, value, owned.quantity),
                )
            else:
                _ = connection.execute(
                    "UPDATE simulator_inventory SET payload = ?, value = ? WHERE card_id = ?",
                    (payload, value, owned.card_id),
                )

    def buy_and_open(self, set_id: str) -> BoosterOpening:
        offer = self._offers.get(set_id)
        if offer is None:
            raise SimulatorError(
                text(
                    "Cette extension n’est pas disponible.", "This set is unavailable."
                )
            )
        with self._lock:
            rng_state = self._rng.getstate()
            try:
                with self._transaction() as connection:
                    _ = self._pools(set_id)
                    state = self._state(connection)
                    if state.balance < offer.price:
                        raise SimulatorError(
                            text(
                                f"Fonds insuffisants : il te manque {format_euros(offer.price - state.balance)}.",
                                f"Insufficient funds: you need {format_euros(offer.price - state.balance)} more.",
                            )
                        )
                    pulls = self._draw(offer)
                    _ = connection.execute(
                        "UPDATE simulator_account SET balance = balance - ?, boosters_opened = boosters_opened + 1 WHERE id = 1",
                        (offer.price,),
                    )
                    drawn: list[OwnedCard] = []
                    for pull in pulls:
                        card = pull.card
                        payload = json.dumps(
                            {
                                "name": card.name,
                                "image": _image_url(card.image),
                                "set_id": offer.set_id,
                                "set_name": offer.name,
                                "rarity": card.rarity,
                                "finish": pull.finish,
                                "source_card_id": card.id,
                                "legacy": False,
                            },
                            ensure_ascii=False,
                        )
                        value = estimated_card_value(
                            card, pull.finish, self._catalogue[set_id].rules.era
                        )
                        _ = connection.execute(
                            "INSERT INTO simulator_inventory (card_id, payload, value, quantity) VALUES (?, ?, ?, 1) ON CONFLICT(card_id) DO UPDATE SET quantity = quantity + 1",
                            (pull.key, payload, value),
                        )
                        row = cast(
                            sqlite3.Row,
                            connection.execute(
                                "SELECT * FROM simulator_inventory WHERE card_id = ?",
                                (pull.key,),
                            ).fetchone(),
                        )
                        drawn.append(self._owned(row, quantity=1))
                    return BoosterOpening(offer, tuple(drawn), self._state(connection))
            except BaseException:
                self._rng.setstate(rng_state)
                raise

    def collection(self) -> list[OwnedCard]:
        with self._transaction(read_only=True) as connection:
            rows = cast(
                list[sqlite3.Row],
                connection.execute("SELECT * FROM simulator_inventory").fetchall(),
            )
            return sorted(
                (self.display_card(self._owned(row)) for row in rows),
                key=lambda card: (card.set_name, card.name, card.card_id),
            )

    def sell(self, card_id: str, quantity: int = 1) -> int:
        candidate = cast(object, quantity)
        if (
            isinstance(candidate, bool)
            or not isinstance(candidate, int)
            or candidate < 1
        ):
            raise SimulatorError(
                text(
                    "La quantité à vendre doit être un entier supérieur à zéro.",
                    "The sale quantity must be a positive whole number.",
                )
            )
        with self._transaction() as connection:
            row = cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM simulator_inventory WHERE card_id = ?", (card_id,)
                ).fetchone(),
            )
            if row is None or cast(int, row["quantity"]) < candidate:
                raise SimulatorError(
                    text(
                        "Tu ne possèdes pas assez d’exemplaires de cette carte.",
                        "You do not own enough copies of this card.",
                    )
                )
            gain = cast(int, row["value"]) * candidate
            if cast(int, row["quantity"]) == candidate:
                _ = connection.execute(
                    "DELETE FROM simulator_inventory WHERE card_id = ?", (card_id,)
                )
            else:
                _ = connection.execute(
                    "UPDATE simulator_inventory SET quantity = quantity - ? WHERE card_id = ?",
                    (candidate, card_id),
                )
            _ = connection.execute(
                "UPDATE simulator_account SET balance = balance + ?, cards_sold = cards_sold + ? WHERE id = 1",
                (gain, candidate),
            )
            return gain

    def sell_duplicates(self) -> int:
        with self._transaction() as connection:
            row = cast(
                sqlite3.Row,
                connection.execute("""SELECT
                COALESCE(SUM((quantity - 1) * value), 0) AS gain,
                COALESCE(SUM(quantity - 1), 0) AS sold FROM simulator_inventory WHERE quantity > 1""").fetchone(),
            )
            gain, sold = cast(int, row["gain"]), cast(int, row["sold"])
            _ = connection.execute(
                "UPDATE simulator_inventory SET quantity = 1 WHERE quantity > 1"
            )
            _ = connection.execute(
                "UPDATE simulator_account SET balance = balance + ?, cards_sold = cards_sold + ? WHERE id = 1",
                (gain, sold),
            )
            return gain

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._connection.close()
