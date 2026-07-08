import json

from pokenux.services.api import tyradex
from pokenux.services.api import tcgdex

all_pokemon_json = tyradex.fetch_all_pokemon()
all_pokemon_json = [
    pokemon for pokemon in all_pokemon_json if pokemon["pokedex_id"] != 0
]
for pokemon in all_pokemon_json:
    del pokemon["name"]["jp"]

    for talent in pokemon["talents"]:
        talent["hidden"] = talent.pop("tc")

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

with open("src/pokenux/jsons/pokemon.json", "w") as f:
    f.write(json.dumps(all_pokemon_json))

languages = ["fr"]
for language in languages:
    fetched_series = tcgdex.fetch_all_series(language)
    fetched_series = [serie for serie in fetched_series if "logo" in serie]

    series = []

    for serie_resume in fetched_series:
        serie_details = tcgdex.fetch_serie_by_id(language, serie_resume["id"])

        serie = {
            "id": serie_details["id"],
            "name": serie_details["name"],
            "logo": serie_details["logo"],
            "release_date": serie_details["releaseDate"],
            "sets": [],
        }

        for set_resume in serie_details["sets"]:
            set_details = tcgdex.fetch_set_by_id(language, set_resume["id"])

            set = {
                "id": set_details["id"],
                "name": set_details["name"],
                "logo": None,
                "release_date": set_details["releaseDate"],
                "abbreviation": None,
                "symbol": None,
                "legal": set_details["legal"],
                "cards": [],
                "serie_id": serie["id"],
            }
            if "logo" in set_details:
                set["logo"] = set_details["logo"] + ".png"
            if "symbol" in set_details:
                set["symbol"] = set_details["symbol"] + ".png"
            if "abbreviation" in set_details:
                set["abbreviation"] = set_details["abbreviation"]["official"]

            for card_resume in set_details["cards"]:
                set["cards"].append(
                    {
                        "id": card_resume["id"],
                        "name": card_resume["name"],
                        "image": card_resume["image"]
                        if "image" in card_resume
                        else None,
                        "set_id": set["id"],
                    }
                )

            serie["sets"].append(set)

        series.append(serie)

    with open(f"src/pokenux/jsons/tcg_{language}.json", "w") as f:
        f.write(json.dumps(series))
