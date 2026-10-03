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

Open **TCG** from the **+** tab. Use `/` to search, `f` to browse series,
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

Open **Quiz** from the **+** tab, choose **Pokédex** or **TCG**, then a game.
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

* Expansion selection
* Variable pricing
* Booster opening flow (TUI)
* Sell duplicates

---

## ⚠️ Disclaimer

Pokémon and Pokémon TCG are trademarks of Nintendo / Game Freak / Creatures / The Pokémon Company.

This project is **strictly educational and non-commercial**.

No official assets are distributed with this project.

---

## 📜 License

MIT
