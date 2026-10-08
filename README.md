# Pokénux (TUI)

Pokénux is a **Terminal User Interface (TUI)** application written in **Python** using **Textual**.

This is a **fan-made project**, not affiliated with Nintendo, Game Freak, Creatures, or The Pokémon Company.

## ✨ Goal

Provide a terminal-based experience to:

* Browse a rich, filterable **Pokédex**
* Browse **Pokémon card collection**
* Play **quizzes** (Pokémon & cards)
* **Open boosters**, manage duplicates, and run an in-game economy

All directly from the terminal.

---

## 🧱 Tech Stack

* **Python 3.11+**
* **Textual** (modern TUI framework)
* **SQLite** (local storage)
* **PokeAPI** (Pokémon data)
* **Pokémon TCG API** (cards & expansions)

---

## 🧠 Planned Features

### Pokédex

* Filter by generation, type, evolution stage
* Search by name
* Sort by height / weight
* View cards linked to a Pokémon

### Cards

* Browse series and expansions in the TCG catalogue
* Combine name, HP (exact value or range), type, and illustrator filters
* Browse paginated results and open a card's artwork and details
* View personal collection
* Duplicate management

The TCG browser reads the installed catalogue. When older assets lack card
metadata, advanced searches and selected-card details load from TCGdex in the
background and are cached locally. Unavailable searches show a retry action.
Name searches and catalogue navigation work offline.

The **Accueil** tab is the main menu: choose **Pokédex**, **Cartes TCG**, **Quiz**,
or **Boosters** with the mouse, Tab/Enter, or keys **1–4**. Each activity opens in
its own tab. The menu switches to a single scrolling column in narrow terminals.

Open **Cartes TCG** from **Accueil**. Use `/` to search, `f` to browse series,
`Space` to expand a series, `Ctrl+F` for filters, `Enter` to open a card, and
`Escape` to return to the list. HP accepts `120` or an inclusive range such as
`50-100`. Filters apply within the selected series or expansion; **Effacer**
resets the entire search.

To prepare complete offline search assets, run
`python scripts/prepare_assets.py --tcg-only --tcg-card-details`. This opt-in
build makes an additional request for every card; the default asset build only
fetches card summaries. Generated files go to `src/pokenux/assets/data`; the app
reads installed files from `~/.local/share/pokenux/assets/data`.

### Quizzes

Open **Quiz** from **Accueil**, choose **Pokédex** or **TCG**, then a game.
Sessions contain 5, 10 or 20 questions, or run indefinitely for practice.
Every answer is typed: case, accents, spaces, hyphens and punctuation are
ignored. Pokémon names are accepted in French and English.

* Pokédex: list every Pokémon with a given initial, solve anagrams, complete
  names with a variable or chosen number of missing letters, name immediate
  evolutions/pre-evolutions (including branches), identify invented names,
  order Pokémon by height or weight, find their generation, and convert names
  to national Pokédex numbers or numbers to names.
* Image games: recognize a Pokémon from its image, blur, pixelation or silhouette.
* TCG: recognize a card from its cropped illustration, identify its expansion
  or series, solve card-name anagrams, and give HP, types, illustrator or rarity
  for a specific card edition.

Use **Enter** to submit, **Indice** for a hint, **Solution** to reveal an answer,
and **Escape** to return to the menu. Lists can be entered one name at a time or
separated by commas; rankings are entered in full, smallest/lightest first.
The session tracks successful questions, mistakes and hints, then displays a
result and a replay action. Revealing or skipping a playable question does not
award a point.

Image games download artwork in the background. An unavailable image can be
retried or skipped without affecting the score. Card metadata is fetched and
cached only when needed if the installed catalogue contains summaries; the
other text games work from the local catalogue.

### Boosters

Open **Boosters** from **Accueil**. The shop lists installed extensions with
prices in virtual euros. Modern packs are priced around €5.50–€8, with higher
estimates for sought-after and vintage sets. Prices depend on the extension
and its era instead of its position in the catalogue. They are estimates for
the game, not live market quotations. Search by extension or series, choose a
pack, then **Acheter & ouvrir**. Cards can be revealed one at a time or together.
Select a revealed card to see its artwork; press
Enter on a card row for a full-screen preview, then Escape to return.

The **Travail** tab is a clicker: a new account starts with €5.00 and each task
earns €0.05. Tasks are limited to one every two seconds across all tabs and
restarts; extra clicks earn nothing. Training starts at €25 and its cost doubles
at each level, adding €0.01 per task per level up to level ten (€0.15). `w` works
and `r` refreshes the account when typing outside a search field.

The **Collection** tab shows quantities and resale values. Sell one copy,
every copy of the selected card, or all duplicates while keeping one copy of
each card and finish. Normal, reverse and holographic versions are separate
entries. Modern bulk cards sell for a few cents, while some rare pulls can be
worth more than their pack. Sales immediately fund further purchases. Card and
extension searches ignore case, accents and punctuation.

Money, training, prices and inventory are saved in
`~/.local/share/pokenux/simulator.sqlite3`, shared by all booster tabs.
Cards enter the saved collection at purchase time, so closing an unopened or
partially revealed pack loses nothing. Purchases and sales are atomic. The
previous P$ save migrates automatically at 1 P$ = €0.01, keeping quantities
and progress. Money is stored as integer cents to avoid rounding errors.

Card rarity comes from TCGdex, never from a hash of the card ID. Missing
rarities are loaded in the background for the selected extension and cached
locally; a failed or incomplete catalogue blocks purchasing and offers a
retry without charging money. Once cached, opening works offline. Promotional
sets without ordinary boosters and special formats whose cross-set slots are
not modelled (such as Celebrations) are excluded. Duplicate cards of the same
finish are avoided within a pack.

Collation depends on the era: Base/Neo packs contain eleven cards, e-Card/EX
packs contain nine cards, later reverse-era packs contain ten cards with a
reverse slot, and standard Scarlet & Violet packs
contain four common, three uncommon and three foil slots. Special-hit
probabilities and resale prices remain estimates for the game, rather than
official pull rates or actual card valuations. The extra Energy and code
cards in modern physical packs are not part of the collectible simulation.

**30th Anniversary** uses its own five-card, all-foil profile with one guaranteed
Pikachu rare and four other distinct cards. **30th Anniversary Classic Collection**
is offered as a separate three-card foil booster. These profiles use estimated
draw distributions without mixing the two catalogues; the bonus basic Energy
is not simulated. The publisher specifies an all-foil anniversary booster, so
this profile uses foil finishes even where TCGdex marks a card as normal-only,
without changing its saved source metadata or rarity. The guaranteed Pikachu
slot has an estimated resale value of €0.50 in the game.

Composition references: [Pokémon's 30th Anniversary product showcase](https://www.pokemon.com/fr/news/jcc-pokemon-produits-30-anniversaire)
and [the UPC's separate three-card Classic booster](https://www.pokemon.com/fr/jcc-pokemon/galerie-produits/collections-ultra-premium-30-anniversaire-journee-et-soiree).

Reference points: [Smyths' €5.99 modern booster listing](https://www.smythstoys.com/fr/fr-fr/jouets/jeux-de-societe-et-puzzles/cartes-a-collectionner/c/SM13010611),
[Pokémon's booster composition](https://support.pokemon.com/hc/fr/articles/360000981613-Que-puis-je-trouver-dans-un-booster-du-Jeu-de-Cartes-%C3%A0-Collectionner-Pok%C3%A9mon),
and [TCGdex's rarity filtering](https://tcgdex.dev/rest/filtering-sorting-pagination).

---

## ⚠️ Disclaimer

Pokémon and Pokémon TCG are trademarks of Nintendo / Game Freak / Creatures / The Pokémon Company.

This project is **strictly educational and non-commercial**.

No official assets are distributed with this project.

---

## 📜 License

MIT
