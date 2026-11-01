# Séances du jour — Déjà-vu

Un script récupère chaque matin les séances du jour d'une liste fixe de cinémas parisiens sur allocine.fr et écrit `data/showtimes.json`. L'app le lit via `raw.githubusercontent.com`. Usage personnel.

## Lancer en local

```sh
pip install -r requirements.txt
python scripts/fetch_showtimes.py --probe        # le wrapper PyPI « allocine » marche-t-il encore ?
python scripts/fetch_showtimes.py --only C0159   # test sur l'UGC Les Halles
TMDB_API_KEY=xxx python scripts/fetch_showtimes.py
```

`TMDB_API_KEY` est optionnelle. Elle sert seulement au repli de correspondance « titre original + année ». Sur GitHub, ajoutez-la dans *Settings → Secrets → Actions*.

## Ajouter un cinéma

1. Trouvez le cinéma sur allocine.fr. L'id est le code dans l'URL : `salle_gen_csalle=C0159` → `C0159`. Ou lancez `python scripts/fetch_showtimes.py --resolve`, qui propose des ids pour les entrées à `null`.
2. Ajoutez une ligne dans `data/cinemas.json` : `allocine_id`, `name` (affiché dans l'app), `brand` (`ugc`, `mk2`, `independant`), `lat` et `lng` (clic droit dans Google Maps), `logo` (chemin ou `null` pour les initiales).

## Correspondance TMDB ↔ Allociné

1. Wikidata : P1265 (id Allociné d'un film) vers P4947 (id TMDB).
2. Sinon, recherche TMDB titre original + année (±1). Accepté seulement s'il y a un seul résultat.
3. Sinon, le film va dans `unmatched` et est logué. Vous pouvez ajouter la paire à la main dans `data/id-map.json` (`"id_allocine": id_tmdb`).

## Ce qui casse si Allociné change son site

- **L'endpoint JSON** `/_/showtimes/theater-{id}/d-{date}/` est interne et non documenté. S'il change d'URL ou de format, chaque cinéma part en échec (`cinemas_failed`). Le script sort alors en erreur sans écraser le JSON de la veille. L'app affiche « Séances du jour pas encore publiées ».
- **Les champs lus** : `results[].movie.internalId/title/originalTitle/releases`, `showtimes.*[].startsAt/diffusionVersion/data.ticketing`. Un renommage casse `parse()`.
- **Anti-bot** : Allociné peut bloquer les IP de GitHub Actions (403/429). Dans ce cas, lancez le script depuis votre machine.
- **Ids de salles** : ils sont stables, mais une salle rachetée peut changer d'id (ex. MK2 Bibliothèque `C2954` vs `C0127`).
