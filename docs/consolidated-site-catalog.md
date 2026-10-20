# Le catalogue consolidé alimente le site

## Source et identités

Les fichiers `contenu csv/consolidated/{vocabulary,grammar,kanji}.csv` sont la
référence éditoriale. Le 9 septembre 2026, leur synchronisation donne :

| Catégorie | Base avant | Base après | Fiches absorbées | Fiches rétablies |
|---|---:|---:|---:|---:|
| Vocabulaire | 8 407 | 8 038 | 369 | 0 |
| Grammaire | 657 | 661 | 4 | 8 |
| Kanjis | 2 534 | 2 534 | 0 | 0 |

Les UUID internes restent des clés techniques stables. La colonne `catalog_id`,
unique par catégorie, contient l’ID du CSV. Les API de détail et le démarrage des
révisions acceptent également cet ID. Les anciens ID et slugs des fiches absorbées
sont conservés dans `content_aliases`, sans chaîne de redirections.

Les listes, résultats de même pertinence et nouvelles découvertes suivent
`source_order`, l’ordre exact du CSV. Le vocabulaire conserve séparément
`jlpt_level_code` (Level) et `kanji_level_code` (KanjiLevel), exposés par l’API.
La première introduction du mot et celle de son écriture ne sont pas confondues.
La grammaire compose son titre depuis Kanji/Kana et reprend le Romaji source à la
place du champ de lecture de l’import historique ; la syntaxe rédigée est conservée.

## Données préservées

- Correspondances vocabulaire contrôlées par graphie, lecture et sens avec la
  provenance auditée, jamais sur un kana seul. Kanji par caractère exact.
- Grammaire par titre et sens, avec trois anciennes notations explicitement
  documentées dans l’import. Les usages distincts de も, のに, etc. ne sont pas fusionnés.
- États FSRS, dates, maîtrise, compteurs et historique conservés ; seule une
  référence à une fiche absorbée change. Deux états d’un même utilisateur qui
  entreraient en collision bloquent l’import : aucune moyenne de progression.
- Questions déjà préparées, choix, réponses et résultats historiques inchangés ;
  seule leur référence et celle du périmètre d’une séance sont remappées.
- Exemples, traductions d’exemples, exercices, nuances, notes et mnémotechniques
  conservés. Les traductions et champs lexicaux présents dans le CSV sont autoritatifs.
- Aucun réimport des leçons, aucune modification de leurs versions ou progressions.
- Liens vocabulaire–kanji reconstruits depuis les écritures consolidées.

Les 25 exercices rédigés disposent de correspondances explicites dans
`backend/app/data/grammar_exercise_catalog.json`, pour ne pas dépendre d’un titre
ou d’un niveau susceptible d’être corrigé. Les nouveaux exercices doivent ajouter
une correspondance contrôlée vers le bon usage grammatical.

Les furigana de graphies alternatives à lecture unique sont validés séparément
pour chaque graphie (伯父さん/叔父さん → おじさん). Les véritables lectures multiples,
par exemple 何 avec なん/なに, restent distinctes et ordonnées.

## Audio

Le manifeste de référence reste `audio/vocabulary-chirp3-yomigana/manifest.json`.
Aucun WAV ni manifeste n’a été régénéré ou remplacé par la migration. Les 8 038
entrées retrouvent une URL ; les audios validés gardent leurs empreintes et leur
paramètre de version. Empreinte du manifeste au moment de la migration :
`781b08cc66ae40f1d4e00cb4ddb242d60ee45bf9014583267c2df3c0238ffae7`.

## Mise à jour

Depuis `backend`, avec l’environnement backend unique activé :

```sh
python -m alembic upgrade head
python -m scripts.sync_catalog
python -m scripts.sync_catalog --apply --backup /chemin/prive/nouvelle-sauvegarde.json
```

Le dossier de sauvegarde doit exister. Le fichier doit être nouveau, créé avec
les permissions 0600. Sans `--apply`, l’ensemble de l’import et des vérifications
est exécuté puis annulé. Une réexécution après publication doit annoncer
`changed: false`. Les écritures concurrentes sur les tables concernées sont
verrouillées pendant la transaction ; le délai d’attente d’un verrou est limité.
Toute erreur annule l’ensemble. Les empreintes des sources et du manifeste sont
contrôlées avant/après. Les autres tâches doivent éviter une modification des
leçons pendant ce contrôle, qui vérifie leur conservation intégrale.

Conserver les ID du CSV lors des corrections. Un ID supprimé ou un contenu
historique non reconnu bloque la synchronisation : une nouvelle fusion demande
une correspondance auditée, pas un rapprochement approximatif. Les anciens imports
CSV par slug sont bloqués après adoption ; `seed_db` appelle le même synchroniseur.
Sur une nouvelle installation, initialiser les niveaux de référence comme au
démarrage du backend avant la première synchronisation.

## Sauvegarde et restauration

Sauvegardes de cette publication, privées et hors données servies :

- `.local/catalog-site-20260909/before-schema.dump` : archive PostgreSQL complète
  prise avant la migration additive 0012, dont le sommaire a été vérifié.
- `.local/catalog-site-20260909/published-before-content.json` : valeurs originales
  des tables concernées, correspondances et empreinte de l’état publié.
- `.local/catalog-site-20260909/link-positions-before.json` : état avant l’alignement
  final des positions de caractères sur la convention de l’API (première position 1).
  Cette dernière passe ne change aucune fiche ni progression. Les deux sauvegardes
  forment une chaîne dont les empreintes intermédiaires ont été vérifiées.
- `before-content.json` dans le même dossier est la sauvegarde d’une première
  tentative annulée ; elle ne représente pas une publication et n’est pas à restaurer.

```sh
python -m scripts.sync_catalog --restore /chemin/prive/link-positions-before.json
python -m scripts.sync_catalog --restore /chemin/prive/published-before-content.json
```

Cette restauration atomique refuse toute modification ultérieure des tables
concernées, notamment de progression. Dans ce cas, ne pas forcer : reconstruire
une restauration ciblée après examen des nouvelles données. Les utilisateurs,
sessions de connexion et leçons ne sont pas restaurés par ce script. Ne pas
restaurer aveuglément l’archive PostgreSQL complète sur une base ayant évolué.
La suppression du schéma 0012 est refusée tant que des identités ou alias sont actifs.

## Limites éditoriales

La migration applique les décisions du catalogue, sans nouvelle fusion de sens.
Elle corrige donc l’ancienne fiche du grand-père en お祖父さん / おじいさん et garde
伯父さん/叔父さん / おじさん pour l’oncle. Les recouvrements entre les entrées N5
« tante/oncle » et certaines entrées N2 existent aussi dans le catalogue : ils ne
disparaissent pas par ce seul branchement et nécessitent une décision éditoriale.

## Vérification

Simulation complète, deuxième passe sans changement, conservation intégrale des
valeurs protégées et annulation exacte vérifiées sur la base réelle avant publication.
Tests de sauvegarde/restauration, conflits, anciens liens, ordre et sens distincts
en SQLite avec clés étrangères et en schémas PostgreSQL temporaires. Recherche,
sessions, révisions et leçons testées également sur PostgreSQL. Aucun redémarrage
manuel des serveurs ni changement de session utilisateur.

Après publication : les listes HTTP correspondent intégralement aux ID, niveaux
et ordre des trois CSV ; graphies, lectures et traductions françaises de vocabulaire
comparées également. Les 373 anciens liens absorbés répondent via les routes de
détail avec une authentification de test isolée. WebKit : cinq fiches (trois mots de
parenté, un usage grammatical rétabli et un kanji) à 1 440, 390 et 320 px, sans
débordement ni erreur console ; session simulée avec les données publiques réelles,
capture mobile inspectée. La dernière synchronisation annonce `changed: false`.
