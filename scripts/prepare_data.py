import json

import pokenux.services.tyradex as tyradex

all_pokemon_json = tyradex.fetch_all_pokemon()
with open("src/pokenux/jsons/pokemon.json", "w") as f:
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

    f.write(json.dumps(all_pokemon_json))
