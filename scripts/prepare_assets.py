import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from pokenux.services.api import tcgdex, tyradex


def prepare_pokemon_json():
    all_pokemon_json = [
        pokemon for pokemon in tyradex.fetch_all_pokemon() if pokemon["pokedex_id"] != 0
    ]

    types = {
        pokemon_type["fr"]: pokemon_type["en"]
        for pokemon_type in get_pokemon_types_json()
    }

    for pokemon in all_pokemon_json:
        del pokemon["name"]["jp"]

        for talent in pokemon["talents"]:
            talent["hidden"] = talent.pop("tc")

        pokemon["types"] = {
            "fr": [t["name"] for t in pokemon["types"]],
            "en": [types[t["name"]] for t in pokemon["types"]],
        }
        pokemon["stats"]["attack"] = pokemon["stats"].pop("atk")
        pokemon["stats"]["defense"] = pokemon["stats"].pop("def")
        pokemon["stats"]["special_attack"] = pokemon["stats"].pop("spe_atk")
        pokemon["stats"]["special_defense"] = pokemon["stats"].pop("spe_def")
        pokemon["stats"]["speed"] = pokemon["stats"].pop("vit")

        if pokemon["evolution"] is None:
            pokemon["evolution"] = {"pre": None, "next": [], "mega": None}

        pokemon["sex"] = pokemon.pop("sexe")

        del pokemon["level_100"]
        del pokemon["formes"]

        if "next" in pokemon:
            del pokemon["next"]

    with open("src/pokenux/assets/data/pokemon.json", "w") as f:
        f.write(json.dumps(all_pokemon_json))


def prepare_pokemon_generations_json():
    all_generations_json = tyradex.fetch_all_generations()

    generations = []
    for generation in all_generations_json:
        generations.append(str(generation["generation"]))

    with open("src/pokenux/assets/data/generations.json", "w") as f:
        f.write(json.dumps(generations))


def get_pokemon_types_json() -> list[dict[str, str]]:
    types = []

    for pokemon_type in tyradex.fetch_all_types():
        types.append(
            {"fr": pokemon_type["name"]["fr"], "en": pokemon_type["name"]["en"]}
        )

    return types


def prepare_pokemon_types_json():
    with open("src/pokenux/assets/data/types.json", "w") as f:
        f.write(json.dumps(get_pokemon_types_json()))


def prepare_tcg_json(
    languages: tuple[str, ...] = ("fr", "en"),
    *,
    include_card_details: bool = False,
    output_dir: Path = Path("src/pokenux/assets/data"),
):
    """Build TCG catalogues, optionally fetching every card's search metadata.

    Set responses only contain card summaries. A complete offline index needs
    one extra API request per card, enabled explicitly with --tcg-card-details.
    Existing metadata in summaries is retained without these extra requests.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for language in languages:
        series = []

        for serie_resume in tcgdex.fetch_all_series(language):
            serie_details = tcgdex.fetch_serie_by_id(language, serie_resume["id"])

            serie: dict[str, Any] = {
                "id": serie_details["id"],
                "name": serie_details["name"],
                "logo": serie_details.get("logo"),
                "release_date": serie_details.get("releaseDate", ""),
                "sets": [],
            }

            for set_resume in serie_details.get("sets", []):
                set_details = tcgdex.fetch_set_by_id(language, set_resume["id"])

                card_set: dict[str, Any] = {
                    "id": set_details["id"],
                    "name": set_details["name"],
                    "logo": None,
                    "release_date": set_details.get("releaseDate", ""),
                    "abbreviation": None,
                    "symbol": None,
                    "legal": {
                        "standard": False,
                        "expanded": False,
                        **(set_details.get("legal") or {}),
                    },
                    "cards": [],
                    "serie_id": serie["id"],
                }

                if set_details.get("logo"):
                    card_set["logo"] = set_details["logo"] + ".png"
                if set_details.get("symbol"):
                    card_set["symbol"] = set_details["symbol"] + ".png"
                abbreviation = set_details.get("abbreviation") or {}
                card_set["abbreviation"] = abbreviation.get("official")

                for card_resume in set_details.get("cards", []):
                    card_details = dict(card_resume)
                    if include_card_details:
                        card_details.update(
                            tcgdex.fetch_card_by_id(language, card_resume["id"])
                        )
                    card_set["cards"].append(
                        {
                            "id": card_details["id"],
                            "name": card_details["name"],
                            "image": card_details.get("image"),
                            "set_id": card_set["id"],
                            "hp": card_details.get("hp"),
                            "types": card_details.get("types") or [],
                            "illustrator": card_details.get("illustrator") or "",
                            "rarity": card_details.get("rarity") or "",
                            "category": card_details.get("category") or "",
                            "local_id": card_details.get("local_id")
                            or card_details.get("localId")
                            or "",
                            "details_loaded": include_card_details
                            or bool(card_details.get("details_loaded"))
                            or all(
                                field in card_details
                                for field in ("hp", "types", "illustrator")
                            ),
                        }
                    )

                serie["sets"].append(card_set)

            series.append(serie)

        with (output_dir / f"tcg_{language}.json").open("w", encoding="utf-8") as f:
            json.dump(series, f, ensure_ascii=False)


def prepare_pokemon_images():
    from pokenux.services import pokedex

    if not Path("src/pokenux/assets/images/pokemon").exists():
        Path("src/pokenux/assets/images/pokemon").mkdir(parents=True, exist_ok=True)

    for pokemon in pokedex.all_pokemon:
        if not Path(
            f"src/pokenux/assets/images/pokemon/{pokemon.pokedex_id}.png"
        ).exists():
            urlretrieve(
                pokemon.sprites.regular,
                f"src/pokenux/assets/images/pokemon/{pokemon.pokedex_id}.png",
            )


def main():
    parser = argparse.ArgumentParser(description="Prepare Pokénux asset files.")
    parser.add_argument(
        "--tcg-only", action="store_true", help="Only prepare TCG catalogues."
    )
    parser.add_argument(
        "--tcg-card-details",
        action="store_true",
        help=(
            "Include HP, types and illustrator for offline search. Makes one "
            "additional request per card (potentially tens of thousands)."
        ),
    )
    args = parser.parse_args()
    Path("src/pokenux/assets/data").mkdir(parents=True, exist_ok=True)
    if not args.tcg_only:
        prepare_pokemon_json()
    prepare_tcg_json(include_card_details=args.tcg_card_details)
    if not args.tcg_only:
        prepare_pokemon_images()
        prepare_pokemon_generations_json()
        prepare_pokemon_types_json()


if __name__ == "__main__":
    main()
