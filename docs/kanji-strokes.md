# Lecteur de traces des kanjis

La finalisation porte sur les 79 kanjis N5 du catalogue, avec preservation de
l'extension N1-N5 deja presente dans le projet.

## Comportement

- Vue complete au chargement, sans animation automatique ; numeros masques par defaut.
- Animer, Pause/Reprendre, Recommencer (retour au canevas vide), trait precedent/suivant.
- Vitesses 0,5x, 1x et 1,5x ; trait courant colore, silhouette discrete en fond.
- Cadence de reference : 1,5 trait/seconde a 1x (ancien 1,5x), soit 0,75 et
  2,25 traits/seconde aux deux autres vitesses. Le selecteur garde une cible de 44 px.
- Ordre et sens suivent les chemins KanjiVG. Les 18 % finaux de chaque intervalle
  constituent une courte pause avant le trait suivant.
- Avec la preference systeme de mouvements reduits, les traits apparaissent entiers,
  un par un ; le compteur et les etapes suivent les traits effectivement visibles.
- Animation arretee au changement de fiche ou lorsque l'onglet est masque.
- Donnees absentes, invalides ou chargement superieur a 10 secondes : caractere fixe,
  message explicite et bouton de nouvelle tentative. Le reste de la fiche reste accessible.

## Donnees et attribution

Source : [KanjiVG](https://kanjivg.tagaini.net/), revision
`55b5ba92a7cad78a62ef04db4be6f9562d949b7f`. Les SVG originaux et les JSON derives
sont distribues sous CC BY-SA 3.0, avec credits visibles dans le lecteur, NOTICE,
licence complete et empreintes SHA-256. Voir `frontend/public/kanji-strokes`.

Le navigateur charge uniquement le JSON de la fiche consultee, depuis le site local.
Il reconstruit les chemins SVG avec React, sans injection de SVG/HTML brut et sans
dependance reseau a KanjiVG. Les originaux restent dans `source/`, les fichiers derives
dans `n1/` a `n5/` et la provenance dans `manifest.json`.

Les controles garantissent la conservation des donnees source, pas une validation
linguistique independante de tous les ordres alternatifs possibles. Aucune progression,
base de donnees ou source pedagogique n'est modifiee par le lecteur.

## Import reproductible

Depuis la racine, uniquement si un reimport est voulu :

```sh
curl -fL -o /tmp/kanjivg.zip https://codeload.github.com/KanjiVG/kanjivg/zip/55b5ba92a7cad78a62ef04db4be6f9562d949b7f
backend/.venv/bin/python backend/scripts/import_kanjivg_n5.py --archive /tmp/kanjivg.zip --level N5
```

## Verification

Depuis `backend` :

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_kanji_strokes.py'
```

Depuis `frontend` :

```sh
./node_modules/.bin/tsc --noEmit
```

Le scenario `frontend/tests/kanji-strokes.browser.js` peut etre execute avec la
commande `run-code` de Playwright CLI dans une session de test deja connectee,
avec interface et contenu en francais. Il utilise les serveurs locaux 3000/8000,
ne modifie pas les preferences et simule les erreurs uniquement dans ce navigateur.
Il controle lecture, pause, reprise, vitesse, clavier, numeros, changement de fiche,
mouvements reduits, erreur/reprise et affichages 1440/768/390/320 px.

### Bilan du 2026-09-08

Les 11 tests de traces passent, ainsi que TypeScript. La suite backend complete
compte 151 tests reussis et 57 ignores optionnels. Le scenario WebKit passe sur
les quatre largeurs ; le delai de chargement, les donnees invalides et l'interface
anglaise ont aussi ete verifies. Les comptes temporaires ont ete supprimes.

Le selecteur a ensuite ete finalise : hauteur de 44 px, chevron SVG decoratif,
focus clavier et rendu creme. Le nouveau CSS est effectivement servi, sans
relance du serveur. La nouvelle reference 1x correspond a l'ancien 1,5x.
Le scenario `frontend/tests/kanji-stroke-speed.browser.js` controle les trois
cadences avec une horloge navigateur deterministe (session QA en anglais).

La fiche francaise a ete verifiee sans injection de style a 320/390/1440 px,
sans debordement. Un debordement distinct de la fiche anglaise reste observable
meme sans lecteur ; le test anglais contraint donc la largeur du lecteur pour
isoler ses controles, sans pretendre valider la mise en page complete en anglais.
