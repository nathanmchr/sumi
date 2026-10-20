# Nuances des graphies de vocabulaire — 9 septembre 2026

Sept notes françaises ajoutées au champ `Notes` du catalogue consolidé et à `vocabulary_translations.notes` pour les sept fiches historiques correspondantes. Elles sont déjà affichées sous la traduction dans la page individuelle. Aucune modification du composant, des traductions courtes, des lectures, du Yomigana, des niveaux, des identifiants, de l’ordre ou de la progression.

## Contenu et sources

Explications françaises rédigées et synthétisées à partir de 漢字ペディア, publié par la Japan Kanji Aptitude Testing Foundation, consulté le 9 septembre 2026. Les exemples courts sont accompagnés de leur sens en français. Les distinctions sont des usages, pas une règle universelle d’interchangeabilité ou de différence d’accent.

| Fiche | Nuance précisée | Sources |
|---|---|---|
| 初め/始め | Stade initial ou période / commencement d’une activité | [はじめ](https://www.kanjipedia.jp/sakuin/doukunigi/items/0005667300) |
| 伯母さん/叔母さん | Parenté du côté aîné / cadet, y compris le cas d’une tante par alliance | [おば](https://www.kanjipedia.jp/kotoba/0003194700) |
| 丸い/円い | Emploi large, sphérique ou arrondi / forme circulaire, sans exclusion absolue | [まるい](https://www.kanjipedia.jp/sakuin/doukunigi/items/0006571300) |
| 川/河 | Cours d’eau en général / particulièrement grand cours d’eau | [川](https://www.kanjipedia.jp/kotoba/0004034400), [河](https://www.kanjipedia.jp/kotoba/0000663300) |
| 伯父さん/叔父さん | Parenté du côté aîné / cadet, par alliance également ; distinguer l’appellation sans lien familial | [おじ](https://www.kanjipedia.jp/kotoba/0003194600), [小父さん](https://www.kanjipedia.jp/kotoba/0003332500) |
| 堅/硬/固い | Solidité et fiabilité / dureté et raideur / lien ou état ferme | [かたい](https://www.kanjipedia.jp/sakuin/doukunigi/items/0000957500) |
| 作る/造る | Faire et créer, emploi large / construction et fabrication, y compris saké et miso | [作る・造る](https://www.kanjipedia.jp/kotoba/0002564700) |

L’avertissement français sur rivière/fleuve est une précision pédagogique déduite des définitions japonaises : celles-ci ne distinguent pas le cours d’eau par son débouché dans la mer.

La fiche historique de おじさん a encore la surface `伯父/叔父`. Sa correspondance déjà auditée pointe vers `伯父さん/叔父さん` dans le catalogue. Cette intervention ajoute seulement la note, sans changer cette surface ni les fiches N2 séparées.

## Mise à jour ciblée et restauration

`backend/scripts/prepare_spelling_notes.py` utilise les sept identifiants canoniques explicites et le résolveur de correspondance historique existant. Il refuse les correspondances manquantes ou multiples, les notes sources vides et une note différente déjà présente. Il ne modifie que les notes françaises, conserve les autres colonnes, est idempotent et enregistre les valeurs originales avant toute écriture. Les opérations se font dans une transaction.

Sauvegardes locales, à conserver jusqu’à validation :

- `.local/content-notes-20260909/vocabulary-before.csv` : catalogue antérieur complet.
- `.local/content-notes-20260909/database-before.json` : sept traductions avant/après, accès limité au propriétaire.

Pour restaurer **uniquement les sept notes françaises en base**, depuis `backend` :

```sh
.venv/bin/python -m scripts.prepare_spelling_notes --restore ../.local/content-notes-20260909/database-before.json
```

La restauration refuse d’écraser une traduction modifiée depuis la sauvegarde. En cas d’échec, toute la transaction est annulée. Pour le catalogue, rétablir uniquement les sept champs Notes à partir de la sauvegarde après comparaison : ne pas remplacer aveuglément le fichier entier si d’autres modifications sont intervenues depuis.

## Compatibilité des leçons

Le compilateur N5 vérifie l’empreinte de l’intégralité du catalogue et inclut l’empreinte de rédaction dans le calcul des versions. Modifier cette dernière aurait créé de nouvelles versions alors que les leçons n’utilisent pas ces notes.

Le plan N5 conserve donc son empreinte de rédaction et autorise l’empreinte exacte de cette révision sous `compatible_source_sha256.vocabulary`. Une autre modification non validée reste refusée. Le test reconstruit les octets du catalogue antérieur, vérifie leur empreinte et compare intégralement les cours compilés avant/après : contenu, ordre, rapport et versions doivent être identiques. Aucun cours n’a été réimporté en base.

- Catalogue avant : `66bfb45716876d7d74c28c59aa973ce5dab6ca3fe8cf9c5792038b5dc0c67597`.
- Catalogue avec notes : `e9476dfc681b7f9ddf1790dd07e7e2ccd29619ec57bc3377af02b2fd7db51dce`.
- Manifeste audio servi, inchangé : `9621c2104f8e67cfdd414b532146d1b54245c618d4325ec9a8b3f63dfac53162`.

## Contrôles

- Catalogue : 8 038 lignes, exactement sept champs Notes modifiés, tous les autres champs et l’ordre identiques.
- Base : comparaison complète avant/après des 8 407 fiches et de leurs traductions, dans une transaction REPEATABLE READ ; seuls sept champs `notes` de langue française diffèrent.
- Tests ciblés : contenu des sept notes, refus des cas ambigus, sauvegarde préservée, idempotence, restauration, localisation, conservation de la progression et stabilité complète des leçons compilées.
- Résultat : sept tests ciblés réussis ; suite backend de 362 tests, 285 réussis et 77 optionnels ignorés. Seconde passe sur la base : aucun changement restant.
- Affichage WebKit : sept fiches à 1 440, 390 et 320 px, notes visibles sans débordement ; données récupérées auprès de l’API publique réelle, session simulée isolée pour contrôler le composant de détail sans modifier la session utilisateur. Capture mobile de la fiche tante inspectée, navigateur fermé. Ce contrôle ne prétend pas inspecter l’onglet Safari personnel de l’utilisateur.
- Aucun appel Google, aucun audio remplacé, aucun serveur relancé. Les sept candidats audio restent dans leur dossier séparé en attente de validation d’écoute.
