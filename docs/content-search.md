# Recherche par romaji

Les bibliothèques de vocabulaire, kanjis et grammaire ainsi que la recherche globale acceptent les romajis, en complément des graphies et traductions déjà recherchées.

Exemples : `kyou` → 今日, `mazu` → 不味い, `nichiyoubi` → 日曜日, `manabu` → 学 et `nakerebanaranai` → なければならない. La recherche ignore la casse, les espaces, les apostrophes et les marqueurs d’okurigana. Les correspondances exactes de lecture passent avant les correspondances partielles, notamment avant la limite de huit résultats par catégorie de la recherche globale.

## Données

Le champ interne `romaji_search` est ajouté aux trois tables de contenu par la migration `0005_romaji_search`. Il ne change pas les données affichées, les furigana, les audios ou la progression.

- Vocabulaire : priorité à la colonne `Romaji` du CSV. En son absence, romanisation des lectures kana enregistrées ; une graphie entièrement en kana peut aussi servir de lecture. Aucune lecture n’est inférée depuis les kanjis.
- Kanjis : romanisation de chaque lecture on/kun existante, en retirant les marqueurs de séparation des okurigana.
- Grammaire : normalisation du champ `structure`, qui contient les romajis importés.

La romanisation de secours utilise `jaconv`. Les variantes restent séparées dans la valeur de recherche, pour ne pas faire correspondre une requête à la fin d’une lecture suivie du début d’une autre. Les prochains imports recalculent le champ. Une écriture SQL directe des lectures nécessite de relancer la préparation.

Les recherches suivent les romajis des sources : par exemple `kyou` et `gakkou`, sans macrons. Il ne s’agit pas d’un système de correction orthographique ou de reconnaissance de toutes les conventions de romanisation.

## Installation et remplissage

Depuis `backend`, installer les dépendances verrouillées puis appliquer :

```sh
PYTHONPATH=. .venv/bin/alembic upgrade head
PYTHONPATH=. .venv/bin/python scripts/prepare_content_search.py --write
```

La préparation utilise les CSV du dossier `contenu csv` ; `--content-dir` permet d’en fournir un autre. Elle sauvegarde les lignes avant écriture, verrouille les lignes pendant la transaction et vérifie que tous les champs autres que `romaji_search`, y compris les dates de modification, restent identiques. Le chemin de sauvegarde est affiché.

Sans `--write`, la commande affiche uniquement les changements proposés. Une nouvelle exécution après remplissage doit proposer zéro changement.

## Vérification locale du 6 septembre 2026

Champs remplis pour 8 407 mots, 2 211 kanjis et 657 points de grammaire. 8 406 mots correspondent exactement aux romajis des CSV ; l’entrée restante est entièrement en kana et utilise cette graphie. Les autres champs ont été conservés. La prévisualisation suivante propose zéro changement.

Tests PostgreSQL isolés : recherche complète/partielle, priorité aux lectures exactes, variantes, casse/espaces, lectures des kanjis, grammaire, filtres JLPT, traductions, caractères littéraux et maintien du champ à l’import. Les tests sont activés avec `CONTENT_TEST_POSTGRES=1` et créent puis suppriment leur propre schéma.
