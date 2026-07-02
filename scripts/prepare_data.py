import json

import pokenux.services.tyradex as tyradex

all_pokemon_json = tyradex.fetch_all_pokemon()
with open("src/pokenux/jsons/pokemon.json", "w") as f:
    f.write(json.dumps(all_pokemon_json))
