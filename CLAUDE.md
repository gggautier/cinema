# Déjà-vu — instructions projet

Journal de films personnel (mobile, 402 px de large, interface en français).
En ligne sur https://gggautier.github.io/cinema/ (GitHub Pages, branche `main`, racine).

## Architecture

- `index.html` : l'application (format Claude Design `.dc.html`, rendu par `support.js`).
- `support.js` : moteur d'affichage Claude Design. Ne pas modifier.
- `ds-base.js` + `_ds/…/` : design system Déjà-vu (composants `DJVuDesignSystem_438449.*`, tokens CSS).
- `.nojekyll` : obligatoire, sinon GitHub Pages ignore `_ds/`. Ne jamais le supprimer.
- `assets/logos/` : logos des cinémas.
- `data/` + `scripts/fetch_showtimes.py` + `.github/workflows/` : séances du jour (Allociné), mises à jour chaque matin par GitHub Actions.

## Données

- Supabase (table `movies`) : films vus, envies, likes.
- TMDB : affiches, réalisateurs, recommandations.
- Les URL et clés sont dans les props de `index.html` (`supabaseUrl`, `supabaseKey`, `tmdbApiKey`, `showtimesBase`).

## Règles

- Doublons en base : ne jamais supprimer ni fusionner une ligne sans l'autorisation explicite de l'utilisateur, ligne par ligne ou lot par lot (lister les ids concernés).
- Doublon = même titre + même réalisateur + même année de sortie. Les homonymes sont des films différents et sont conservés. On garde la ligne dont l'année de visionnage est la plus récente.
- Respecter le design system : couleurs, typo (Space Grotesk / Inter), espacements et ton du README de `_ds/`.
- Interface en français, libellés courts, sans phrases.
- Après chaque modification validée, fusionner dans `main` pour mettre à jour le site.
