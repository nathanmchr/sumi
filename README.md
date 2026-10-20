# Sumi 墨

Plateforme web d’apprentissage du japonais pensée comme un vrai produit éducatif: niveaux JLPT séparés par catégorie, furigana configurable, fiches kanji détaillées, et révision espacée simple à maintenir.

> **Contenu non inclus.** Le catalogue de cours (CSV consolidés, leçons, exercices,
> compléments et audits dans `contenu csv/`, `backend/app/data/` et `docs/*.json|csv`)
> ainsi que les audios générés restent privés et ne sont pas publiés dans ce dépôt.
> Le code est fourni tel quel ; `backend/seed/` contient quelques lignes d’exemple.

## Architecture générale

- `backend/` : API FastAPI, SQLAlchemy, PostgreSQL, auth JWT via cookies, logique SRS, import CSV, endpoints REST documentés.
- `frontend/` : Next.js App Router, TypeScript, SWR pour les données, UI sobre et premium, écrans d’étude et de navigation.
- `backend/alembic/` : migrations.
- `backend/seed/` : exemples CSV importables.

## Entités principales

- `users`
- `user_settings`
- `jlpt_levels`
- `vocabulary_items`
- `kanji_items`
- `grammar_items`
- `example_sentences`
- `vocabulary_kanji_links`
- `learning_states`
- `review_history`
- `study_sessions`
- `refresh_tokens`
- `lessons`
- `lesson_progress`

## Leçons N5

Le menu **Leçons** ouvre `/study/lessons` : 15 unités, 109 leçons guidées, 668 mots, 84 points de grammaire et 86 kanjis du catalogue N5 corrigé. Chaque leçon possède une barre de progression, des exercices corrigés côté serveur et une reprise enregistrée par utilisateur. Les réglages FR/EN, furigana et romaji sont conservés.

Depuis `backend/`, avec son environnement virtuel activé :

```bash
python -m alembic upgrade head
python scripts/import_n5_lessons.py              # audit, sans écriture
python scripts/import_n5_lessons.py --import-db  # import transactionnel et réexécutable
```

L'import ne remplace pas les catalogues ni les révisions existantes. Une leçon ayant déjà une progression ne peut pas être remplacée par une version différente. Voir [la conception, les sources et les limites du parcours](docs/n5-lessons.md).

## Arborescence

```txt
backend/
  app/
    api/
    core/
    models/
    repositories/
    routers/
    schemas/
    services/
    utils/
  alembic/
  seed/
  scripts/
frontend/
  app/
  components/
  lib/
  styles/
```

## Choix techniques

- FastAPI + SQLAlchemy pour un backend clair, typé, extensible.
- JWT en cookies `HttpOnly` pour garder un front simple tout en réduisant l’exposition au token.
- PostgreSQL pour les relations, les contraintes, et les upserts.
- App Router Next.js pour séparer proprement dashboards, écrans d’étude, auth, et admin.
- SWR pour le fetch client et la déduplication.
- `ruby` HTML + segments structurés pour un affichage furigana configurable.
- SRS volontairement simple: intervalle, répétitions, ease factor, statut connu/fragile/master.

## Lancement local

### 1. PostgreSQL

```bash
brew install postgresql@15
./scripts/local-db.sh setup
```

Le projet utilise un cluster PostgreSQL natif isolé dans `.local/postgres/`, sans Docker. Il écoute sur `localhost:5433` pour ne pas entrer en conflit avec les autres bases locales et utilise le rôle applicatif `apprentissage_app`.

Pour les lancements suivants:

```bash
./scripts/local-db.sh start
./scripts/local-db.sh status
./scripts/local-db.sh stop
```

### 2. Backend

Un seul environnement Python, `backend/.venv`, regroupe le serveur, FSRS et les
outils audio Kokoro/Chirp. Les dépendances sont déclarées dans
`backend/pyproject.toml` et verrouillées dans `backend/uv.lock`.
Depuis la racine du projet :

```bash
uv sync --project backend --locked
source backend/.venv/bin/activate
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Pour relancer sans activer l’environnement, utiliser
`backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000`.

Sur une installation neuve, installer aussi le dictionnaire japonais utilisé par
les deux générateurs audio :

```bash
backend/.venv/bin/python -m unidic download
```

Après migration depuis l’ancien environnement racine, ouvrir un nouveau terminal
ou exécuter `deactivate` puis `source backend/.venv/bin/activate`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Le serveur de développement écrit dans `frontend/.next-dev/`. Les commandes `npm run build` et `npm run start` utilisent `frontend/.next/`, afin qu’un build de vérification ne perturbe pas le site local en cours d’exécution.

## Variables d’environnement

Copier `.env.example` puis ajuster:

- `DATABASE_URL`
- `SECRET_KEY`
- `NEXT_PUBLIC_API_URL`

## Langues

Chaque utilisateur peut choisir séparément la langue de l’interface et celle des traductions pédagogiques depuis les paramètres. Les locales disponibles sont `en` et `fr`.

Les contenus japonais restent canoniques. Le vocabulaire, les significations de kanji, la grammaire et les exemples utilisent des tables de traduction dédiées. L’API accepte `?locale=en|fr` et retombe sur l’anglais lorsqu’une traduction manque; `translation_locale` indique la langue réellement retournée.

## Import CSV

Le catalogue de référence du site se trouve dans
`contenu csv/consolidated/` : `vocabulary.csv`, `grammar.csv` et `kanji.csv`.
Les niveaux sont à gauche (`Level`, puis `KanjiLevel` pour le vocabulaire), sans
`KanaLevel`. L’ordre pédagogique N5 → N1 et l’ordre des lignes d’origine sont
conservés ; les fusions restent à leur première apparition.

Depuis le 9 septembre 2026, la base sert **8 038 mots, 661 points de grammaire et
2 534 kanjis**, synchronisés avec ces CSV. `catalog_id` conserve leur ID éditorial ;
les clés internes et les alias préservent les anciennes URL et la progression.
Les fichiers par niveau sont des archives, plus une source d’import du site.
Les cas de sens ou de graphie incertains restent séparés dans le catalogue.

Pour vérifier la préparation sans écrire de fichiers :

```bash
backend/.venv/bin/python backend/scripts/consolidate_content_csv.py
```

Le script de préparation refuse d’écraser un dossier de destination existant.
Il sert à cette consolidation initiale : après adoption du catalogue, conserver
les IDs inscrits dans les CSV lors des modifications éditoriales.

Depuis le dossier `backend`, avec l’environnement virtuel activé :

```bash
python -m alembic upgrade head
python -m scripts.sync_catalog
python -m scripts.sync_catalog --apply --backup /chemin/prive/sauvegarde-inutilisee.json
```

Sans `--apply`, la simulation complète est annulée. L’application est atomique,
refuse les ambiguïtés et les collisions de progression, puis vérifie les invariants.
`seed_db` redirige désormais vers cette même commande ; il ne relit plus les quinze
CSV historiques. L’ancien import admin est refusé dès l’adoption du catalogue pour
éviter de recréer les doublons. Procédure, niveaux, sauvegardes et restauration :
[catalogue du site](docs/consolidated-site-catalog.md).

## Génération audio du vocabulaire avec Chirp 3 HD

### Audio partagé entre variantes kana et kanji

Depuis le 8 septembre 2026, le site utilise en priorité le manifeste
`audio/vocabulary-chirp3-yomigana/manifest.json`. Les nouvelles générations deviennent
accessibles au fil du lot, sur les fiches, le vocabulaire associé et les séances.
Les correspondances avec l’ancienne base sont contrôlées par graphie, lecture et
sens depuis le catalogue et son journal de provenance, jamais par lecture seule.
Les fichiers sont vérifiés par empreinte ; l’audio du catalogue reste le repli
tant que le nouveau n’est pas disponible. Un audio volontairement vidé lors des
corrections n’est pas rétabli depuis l’ancienne base. Voir
[le raccordement et la reprise](docs/audio-regeneration.md).

Les fiches kana réutilisent l’audio de la fiche kanji du **même mot**, tous niveaux
confondus : `はし` (baguettes, N5) utilise ainsi l’audio de `箸` (N2), pas celui
de `橋` (pont). L’écriture affichée et le niveau restent inchangés.

Le mécanisme historique de repli est audité dans
`backend/app/data/vocabulary_audio_aliases.csv`. Une cible vide signifie que les
homophones présents ne sont pas une variante appropriée. Il ne faut jamais
déduire une association à partir de la lecture seule. Lors de l’ajout de mots,
compléter cette table après vérification des significations japonaises, anglaises
et françaises ; le test de couverture signale les nouvelles paires à examiner.

La résolution est commune aux fiches, au vocabulaire associé et aux séances
(y compris les questions déjà préparées). Si la fiche kanji ou son URL audio
manque, l’audio propre au mot est conservé. Aucun WAV ni manifeste n’est modifié,
et aucune régénération n’est nécessaire.

### Génération

Le générateur Google est séparé du générateur Kokoro et écrit par défaut dans
`audio/vocabulary-chirp3-yomigana/`. Il ne remplace donc ni les WAV ni les manifestes
de `audio/vocabulary/` ou `audio/vocabulary-chirp3/`.

Il lit maintenant `contenu csv/consolidated/vocabulary.csv`, en conservant les ID
et l’ordre du catalogue corrigé. L’ancien format reste accessible avec
`--input-dir "contenu csv"`. La colonne `Yomigana`, lorsqu’elle est renseignée,
fournit directement la lecture et ses marqueurs d’accent `^` / `!` ; sinon le script
impose `Kana` sans inventer d’accent. Une lecture différente de `Kana` ou des marqueurs
invalides provoquent une erreur avant tout appel Google. Les lectures multiples sont
conservées dans l’ordre avec un phonème SSML par occurrence.

Les accents, leur provenance et les limites des données sont décrits dans
[la documentation de prononciation](docs/japanese-pronunciation.md).

Les dépendances audio font partie de l’environnement backend unique. Pour les synchroniser :

```bash
uv sync --project backend --locked
```

Après avoir créé un projet Google Cloud, activé Cloud Text-to-Speech et associé
un compte de facturation, exporter une clé API autorisée pour Cloud Text-to-Speech:

```bash
export GOOGLE_TTS_API_KEY="votre-cle-api"
```

Le script lit cette variable dans son environnement (il ne charge pas de fichier
`.env` automatiquement). Une clé non vide est prioritaire sur les identifiants ADC.
Si elle est refusée par Google, l’erreur est remontée sans basculer vers un autre
compte. Garder la clé hors du code et des fichiers versionnés.

Sans clé, ou avec une variable vide, le script utilise les identifiants ADC:

```bash
gcloud init
gcloud auth application-default login
gcloud auth application-default set-quota-project VOTRE_PROJECT_ID
```

Contrôler d’abord les mots sélectionnés sans appeler l’API ni créer de fichier:

```bash
backend/.venv/bin/python backend/scripts/generate_vocab_audio_google.py --dry-run
```

Générer tous les WAV du vocabulaire avec la voix japonaise Chirp 3 HD Aoede:

```bash
backend/.venv/bin/python backend/scripts/generate_vocab_audio_google.py
```

Le script reprend uniquement les fichiers associés à la même requête, la même voix,
la même vitesse et au même format, avec une empreinte du fichier concordante.
Il conserve le manifeste existant lors d’une sélection limitée et refuse un ancien
manifeste incompatible : choisir alors une destination distincte, sans supprimer les
anciens fichiers. Le manifeste conserve ID, yomigana, requête exacte, paramètres,
date et empreinte ; une génération n’est jamais marquée comme validée à l’écoute.
Ne pas lancer deux générations simultanées dans la même destination.

Le débit reste limité volontairement à 180 requêtes par minute. Le nombre de caractères
de texte/SSML et le coût indicatif sont affichés ; ce n’est pas une facture ni une
vérification du traitement tarifaire des prononciations personnalisées.
Tout le vocabulaire est sélectionné par défaut;
`--all` reste accepté pour compatibilité. Pour un essai de 20 mots mélangés,
utiliser `--limit 20 --shuffle`. `--all` et `--limit` ne se combinent pas.

Le générateur Kokoro utilise le même environnement :

```bash
backend/.venv/bin/python backend/scripts/generate_vocab_audio.py --limit 20
```

## MVP couvert

- inscription / connexion
- réglages JLPT séparés
- dashboard
- vocabulaire
- kanji
- grammaire
- furigana
- recherche
- import CSV
- SRS basique avec historique

## Apprentissage adaptatif

Le parcours de séances utilise des QCM validés côté serveur et FSRS-6. Voir [le fonctionnement, la migration et la couverture des exercices](docs/learning-fsrs.md). Après mise à jour, synchroniser les dépendances backend et appliquer la migration Alembic avant de relancer le serveur.

## Recherche par romaji

Les bibliothèques et la recherche globale acceptent les romajis complets ou partiels (`kyou`, `mazu`, `manabu`…). Voir [les sources, la migration et le remplissage des champs de recherche](docs/content-search.md).

## Affichage des romaji

Dans **Paramètres > Furigana > Afficher les romaji**, activez la lecture en alphabet latin sous les mots du catalogue et des fiches vocabulaire. Cette préférence est enregistrée par compte, désactivée par défaut et indépendante des furigana. La lecture hiragana en double sous le mot n'est plus affichée. Une lecture romaji absente ne produit aucune ligne vide.

Le champ `vocabulary_items.romaji` conserve le format des CSV (espaces et apostrophes inclus), séparément de l'index `romaji_search`. Les imports suivants conservent la valeur fournie dans la colonne `romaji` ; une valeur absente ne remplace pas une lecture existante. Pour enrichir une ancienne base sans réimporter les mots, depuis `backend` :

```sh
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m scripts.prepare_vocabulary_romaji
.venv/bin/python -m scripts.prepare_vocabulary_romaji --write
```

Le script associe exactement mot et lecture dans `contenu csv/* Vocab.csv`, refuse les sources contradictoires et ne remplit que les romaji manquants. Il préserve tous les autres champs, identifiants, dates et données de progression. Aucun romaji n'est inventé en cas de correspondance absente.
