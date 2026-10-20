# Supplément de 323 kanjis

Les caractères absents du catalogue ont été ajoutés à partir de l'audit corrigé
`output/kanji-coverage-2026-09-08/audit.json`. Ce rapport est conservé comme état
**avant** intégration. Les 2 211 anciennes lignes restent identiques, avec leurs
ID et positions d'origine ; 323 lignes sont ajoutées en fin de `kanji.csv`.
Le catalogue compte désormais **2 534 caractères uniques**.

| Niveau pédagogique | Ajouts |
|---|---:|
| N5 | 7 |
| N4 | 5 |
| N3 | 51 |
| N2 | 88 |
| N1 | 172 |

Le niveau retenu est le plus facile des **KanjiLevel** des mots contenant le
caractère dans le vocabulaire consolidé corrigé. Level n'est jamais utilisé
comme repli. Ce classement sert le parcours de l'application, il n'est pas
présenté comme une liste officielle JLPT.

## Sources et adaptations

- KANJIDIC2 officiel : https://www.edrdg.org/kanjidic/kanjidic2.xml.gz
- Documentation : https://www.edrdg.org/wiki/KANJIDIC_Project.html
- Copyright Jim Breen et EDRDG ; licence : https://www.edrdg.org/edrdg/licence.html
- Les données dérivées et traductions de ce supplément sont sous
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

`backend/app/data/kanji_supplement.json` conserve la version 2026-251 du
8 septembre 2026, les SHA-256 du téléchargement et du XML, les sens source,
les lectures japonaises typées, les radicaux classiques et les nombres de traits.
Les lectures chinoises/coréennes, les nanori (noms propres), les codes SKIP et
les index de dictionnaires ne sont pas importés.

KANJIDIC2 couvre les lectures japonaises et l'anglais des 323 fiches, mais
seulement 35 ont aussi des sens français dans cette source. Les 323 traductions
françaises sont des adaptations éditoriales relues à partir de ces sens,
conservées dans `kanji_supplement_french.json`, pas des traductions toutes
retrouvées telles quelles dans un dictionnaire français. Une relecture par un
lexicographe reste souhaitable avant publication commerciale.

Quatre précisions bilingues documentées dans `kanji_supplement_overrides.json`
complètent les gloses trop courtes : 身 (corps/soi), 璧 (disque de jade),
芯 (cœur/centre/mèche/mine) et 鹸 (alcali). Les références consultées sont
enregistrées avec chaque adaptation. Les sens sont ceux du caractère ; ils ne
se confondent pas systématiquement avec ceux d'un mot composé comme 味噌 ou 箪笥.

Les 323 animations supplémentaires proviennent de KanjiVG, révision
`55b5ba92a7cad78a62ef04db4be6f9562d949b7f`, comme les animations existantes.
Chaque JSON conserve le SHA-256 de son SVG d'origine. Les SVG et leur licence
CC BY-SA 3.0 restent distribués séparément dans `frontend/public/kanji-strokes`.
La notice bilingue du dictionnaire est accessible depuis les fiches kanji :
`frontend/public/data-sources/kanji.md`.

## Import local ciblé

Depuis `backend`, avec l'environnement virtuel et PostgreSQL local configurés :

```sh
python -m scripts.kanji_supplement database
python -m scripts.kanji_supplement database --write
```

Sans `--write`, la transaction est annulée. L'import ajoute seulement les
nouvelles fiches, leurs deux traductions et les relations avec les graphies
réellement présentes en base. Il ne modifie ni les anciens kanjis, ni le
vocabulaire, ni les comptes, ni les progressions. Une réexécution identique ne
fait rien ; un conflit avec une donnée éditée provoque une erreur, pas un
écrasement. Les ID UUIDv5 dépendent du caractère, pas de sa traduction.

Depuis l’adoption du catalogue le 9 septembre 2026, les 323 ajouts font partie de
`consolidated/kanji.csv`. Utiliser `python -m scripts.sync_catalog` pour simuler la
synchronisation du site, puis `--apply --backup ...` pour publier. `seed_db` est
un alias de cette commande, plus un import historique suivi du supplément.
Le mode `database` ci-dessus décrit l’import ciblé initial ; pour de nouveaux
ajouts, mettre d’abord à jour le catalogue puis synchroniser le site.

## Reproduction et mise à jour

Télécharger l'archive officielle, puis depuis `backend` :

```sh
python -m scripts.kanji_supplement prepare --archive /chemin/kanjidic2.xml.gz
python -m scripts.kanji_supplement prepare --archive /chemin/kanjidic2.xml.gz --write
python -m scripts.kanji_supplement catalog --write
python -m scripts.kanji_supplement strokes --archive /chemin/kanjivg-55b5ba92a7cad78a62ef04db4be6f9562d949b7f.zip --write
```

Le mode `prepare --write` régénère le manifeste local, pas la base. Conserver
et relire le diff avant toute mise à jour des traductions. Les commandes catalog
et database refusent volontairement de remplacer une valeur existante : une
future correction nécessite une migration éditoriale explicite préservant les
ID. Vérifier périodiquement les mises à jour KANJIDIC2, au moins mensuellement
selon la notice EDRDG, puis mettre à jour les références de version publiées.

La CLI `consolidate_content_csv.py` inclut ce supplément après la reconstruction
historique ; `build_catalog()` seul reste la reconstruction historique utilisée
par les audits antérieurs. Le supplément ne change pas leurs fichiers source.

## Vérification

```sh
python -m unittest discover -s tests -p 'test_kanji*.py'
python -m unittest discover -s tests
```

Les tests couvrent le classement KanjiLevel, la couverture bilingue, l'intégrité
des 2 211 lignes initiales, les adaptations sourcées, les tracés, l'idempotence,
le rollback et le refus d'écraser une fiche existante. Les radicaux sont des
radicaux classiques normalisés Unicode, pas une décomposition graphique inventée.

## Résultat local vérifié

Intégration terminée le 9 septembre 2026 (Tokyo) : 323 kanjis, 646 traductions
et 594 liens vocabulaire ajoutés. Toutes les lignes préexistantes sont restées
identiques, y compris les 10 états d'apprentissage et 44 révisions. Une seconde
simulation ne prévoit aucun changement. Le rapport de transaction est conservé
dans `output/kanji-coverage-2026-09-08/integration-result.json`.

L'audit après ajout dans `output/kanji-coverage-after-addition-2026-09-09`
couvre les 2 091 kanjis distincts des mots consolidés, sans absence. L'API
renvoie les 323 nouvelles fiches correctement dans chacune des deux langues.
28 tests kanji réussissent ; la suite complète comporte 227 tests réussis et
58 tests opt-in ignorés. TypeScript passe sans erreur.

La recherche, la fiche 飴, ses lectures et tracés, le changement EN/FR et les
liens kanji ↔ vocabulaire ont été vérifiés dans WebKit sur desktop/mobile.
Le compte temporaire de contrôle a été supprimé. Aucun serveur frontend/backend
n'a été arrêté ou relancé pour cette opération.
