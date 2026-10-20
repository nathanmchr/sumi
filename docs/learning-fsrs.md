# Apprentissage QCM et FSRS-6

## Mise en route

Depuis `backend/` :

```sh
uv sync
uv run python -m alembic upgrade head
uv run python -m app.services.grammar_exercise_import
uv run python -m uvicorn app.main:app --reload --port 8000
```

Utiliser l’environnement `backend/.venv` ou `uv run` : un ancien serveur lancé dans un autre environnement ne voit pas forcément la nouvelle dépendance FSRS. Ne pas relancer le seed global pour importer les exercices : l’import ciblé est idempotent et ne modifie ni les fiches, ni les fichiers audio, ni la progression.

## Comportement

- Vocabulaire et kanji : quatre significations dans `content_locale`. Grammaire : phrase à compléter avec quatre formes japonaises, consigne et correction localisées.
- Avant le premier QCM d’un nouveau mot de vocabulaire, une fiche de découverte présente sa signification localisée, sa lecture/furigana selon les préférences, son audio et son exemple lorsqu’ils existent. « Je suis prêt » ouvre ensuite les quatre choix et masque la signification. La phase est conservée côté serveur : recharger reprend la fiche ou la question, et les mots déjà évalués passent directement au QCM. Cette consultation ne change ni FSRS, ni les compteurs de séance.
- La première réponse valide est définitive. Les choix sont persistés et restent identiques au rechargement. La correction est renvoyée après la réponse : choix correct en vert, choix erroné en rouge, lecture/signification et exemple disponible.
- Le navigateur ne transmet que `option_id`. Le serveur calcule la réussite et enregistre la durée écoulée depuis l’ouverture du QCM (après la fiche de découverte pour un nouveau mot). Cette durée inclut les pauses et ne produit jamais une note Easy.
- FSRS Python 6.3.2, algorithme FSRS-6 à 21 paramètres, rétention souhaitée 90 %, sans fuzzing. Erreur → Again (1), réussite → Good (3).
- Acquisition initiale du vocabulaire et des kanji : **cinq bonnes réponses consécutives**, enregistrées côté serveur. La découverte ne compte pas comme réponse. Une erreur remet la barre à zéro et ajoute les rappels nécessaires à la séance. La sélection privilégie deux autres réponses entre les rappels. Si aucune autre question ne convient, la fiche pratiquée le moins récemment revient directement après la correction : aucune pause ni attente imposée, même dans une séance ciblée sur un seul mot. Les nouveautés restent limitées au budget de séance, sans ajouter des mots uniquement pour remplir un délai.
- Ces répétitions initiales sont enregistrées dans l’historique avec le planificateur `acquisition`, sans alimenter FSRS avec plusieurs rappels rapprochés. La cinquième réussite initialise FSRS une seule fois et programme la consolidation à quatre heures. Les révisions suivantes suivent FSRS ; un oubli d’un item établi déclenche dix minutes de réapprentissage, puis un retour à FSRS après réussite. La grammaire conserve ses exercices d’application et ses étapes FSRS (10 minutes → 4 heures).
- La correction affiche uniquement une barre de progression, sans date de révision, compteur de rappels ni phrase explicative. Pendant l’acquisition, elle représente les cinq réussites ; ensuite, elle représente la stabilité FSRS rapportée au seuil produit de 90 jours. Les libellés et valeurs restent accessibles aux lecteurs d’écran. Cette barre est un indicateur de progression, pas une probabilité de rappel.
- Les échéances FSRS futures sont exclues, y compris dans une séance ciblée. Les acquisitions incomplètes suivent leur espacement en séance. Les révisions dues passent avant les nouveautés de la plage choisie. Les nouveautés sont introduites par difficulté croissante (N5 vers N1) ; à niveau égal, les séances mixtes alternent les catégories.
- Les séances sont toujours enregistrées. Recharger leur URL reprend la question ou sa correction. Une question non répondue expire après 24 heures ; Continuer la remplace. Un changement de catégorie cible termine la séance précédente.

## Plages de niveaux

Chaque catégorie possède une borne minimale et une borne maximale de difficulté : N4–N2 comprend N4, N3 et N2. Les nouveaux contenus sont introduits dans cet ordre, y compris dans les séances mixtes. Les répétitions nécessaires à l’acquisition restent intercalées ; atteindre un nouveau niveau ne signifie pas que le précédent est définitivement mémorisé. Les fiches sans question exploitable sont ignorées selon les règles éditoriales existantes.

Retirer un niveau suspend ses contenus dans les séances, les acquisitions et la file de révision, sans supprimer ni modifier leur progression ou leur historique. Réintégrer ce niveau rétablit leur éligibilité avec les mêmes réussites d’acquisition, états FSRS et échéances ; une échéance encore future reste future. La file « À réviser » et son compteur filtrent les niveaux actifs, tandis que le total historique des éléments appris reste conservé. Une séance ciblée depuis une fiche respecte également la plage active. Un état mémoire vide, sans réponse antérieure ni acquisition en cours, reste une nouveauté et respecte donc les bornes.

La migration additive `0007_jlpt_level_ranges` ajoute `{category}_min_level_code` pour les trois catégories ; `{category}_level_code` reste la borne maximale. Les préférences existantes sont reprises comme plages d’un seul niveau, sans élargissement automatique. L’API refuse les bornes inversées ; un ancien client qui transmet uniquement un niveau conserve le comportement d’un niveau unique.

Les séances capturent les deux bornes. Enregistrer une nouvelle plage clôt les séances encore ouvertes des catégories concernées : les réponses déjà validées et leur historique restent intacts, mais les questions en attente ne peuvent plus être répondues. Une nouvelle séance utilise la plage enregistrée et reprend les acquisitions existantes. Une ancienne URL affiche le bilan, sans reproposer sa question. La sauvegarde et les réponses partagent le même verrou utilisateur pour éviter une réponse concurrente après retrait d’un niveau. Les réglages visuels et les plages des autres catégories ne clôturent pas une séance indépendante. Les anciennes séances sans borne minimale sont interprétées comme des plages d’un seul niveau ; une ancienne question hors plage est écartée sans créer de révision.

## État mémoire et migration

`LearningState.fsrs_card` conserve l’état FSRS, la difficulté, la stabilité, le dernier rappel et l’échéance. La probabilité de rappel est recalculée selon le temps écoulé. Les résultats récents (cinq maximum), le nombre de succès consécutifs et une révision monotone sont conservés séparément.

La migration `0003_fsrs_questions` est additive : aucune échéance ni entrée historique n’est réécrite. Les items existants migrent à leur prochaine réponse validée. Pour un ancien item établi, son intervalle donne une estimation initiale de stabilité (minimum un jour), avec une difficulté initiale neutre de 5. Ce n’est pas une reconstruction de son historique FSRS. Les anciens items en apprentissage reprennent les étapes courtes.

La migration additive `0004_initial_acquisition` ajoute le champ JSON nullable `LearningState.acquisition` : réussites initiales et position du dernier rappel dans la séance. Elle ne modifie aucune échéance existante. Les premières acquisitions FSRS encore dans une séance ouverte reprennent leur série de réussites (plafonnée à quatre) sans modifier l’échéance lors de la lecture ; leur prochaine réponse applique le nouveau parcours. Les items établis ou en réapprentissage ne recommencent pas l’acquisition initiale.

Les statuts ne sont plus des boutons :

| État | Règle |
| --- | --- |
| learning | Acquisition initiale en séance, puis étapes courtes FSRS |
| relearning | Étape de réapprentissage FSRS |
| fragile | Après acquisition : au moins deux erreurs parmi les cinq dernières réponses, ou rappel estimé inférieur à 80 % |
| known | Après acquisition : stabilité ≥ 7 jours et au moins trois succès consécutifs |
| master | Stabilité ≥ 90 jours, au moins cinq succès consécutifs, aucune erreur parmi les cinq dernières réponses |
| review | Consolidation entre acquisition et seuils ci-dessus |

Les seuils des libellés sont des choix du produit, distincts de l’algorithme FSRS. Les statuts learning/relearning ont priorité. `mastery` reste un indicateur d’affichage, pas une probabilité de rappel.

## Contrat API et cohérence

- `POST /learning/sessions` : `{category?, content_id?, only_due?, planned_items?}` ; budget demandé de 1 à 30 réponses. Les séances vocabulaire, kanji et mixtes prévoient au moins 15 réponses (trois nouvelles fiches × cinq rappels). La grammaire garde 12 réponses par défaut. Une séance ciblée prévoit les rappels d’acquisition restants, ou une seule réponse pour une révision établie. Le budget augmente si nécessaire pour terminer les acquisitions introduites, notamment après une erreur.
- `GET /learning/sessions/{id}` : reprendre la question/correction.
- `POST /learning/sessions/{id}/next` : obtenir directement la prochaine question ou le bilan. Le serveur organise l’alternance des rappels sans délai bloquant. Le contrat n’expose plus `retry_at` ; les anciennes séances enregistrées en pause reprennent automatiquement une question lors de leur chargement ou de leur reprise.
- `POST /learning/questions/{id}/begin` : terminer la découverte et ouvrir le QCM ; idempotent, sans réponse ni changement de progression.
- `POST /learning/questions/{id}/answer` : `{option_id}` uniquement. Les champs supplémentaires sont refusés.
- `POST /learning/reviews` : 410, anciennes notes manuelles supprimées.

Le verrou PostgreSQL sur l’utilisateur sérialise création de séance, émission de question et réponse. Une répétition réseau de la même réponse retourne le même résultat ; une autre réponse renvoie 409. Les questions étrangères, expirées et les révisions obsolètes sont rejetées. L’état, le compteur de séance, la correction et l’historique sont validés dans une transaction unique. L’historique conserve les options choisies pour une future analyse des confusions.

## Couverture et limites éditoriales

La banque initiale comprend **25 exercices de grammaire bilingues : 5 par niveau N5 à N1**, sur 657 fiches actuellement présentes. Les autres fiches restent consultables et n’affichent pas de bouton d’entraînement ; aucune question de signification n’est fabriquée pour elles. Le fichier `app/data/grammar_exercises.py` contient la banque, et l’import vérifie les correspondances exactes et uniques avec les fiches existantes.

Le corpus actuel de vocabulaire ne fournit aucune phrase d’exemple. Le parcours sait afficher les exemples localisés lorsqu’ils existent, mais indique explicitement leur absence après une erreur. Une banque d’exemples reste à enrichir ; les exemples de grammaire sont inclus dans les exercices.

Les distracteurs excluent les doublons, les sens partagés, les mêmes formes japonaises et un lexique bilingue de synonymes ; les contrôles portent aussi sur le sens anglais de référence. Ils privilégient la même nature grammaticale lorsqu’elle est renseignée, le même niveau ou un niveau adjacent, un nombre de sens et une longueur comparables. Les données de vocabulaire actuelles utilisent essentiellement `other` pour la nature grammaticale : ce critère ne peut donc pas discriminer ces fiches. La détection lexicale ne constitue pas une garantie exhaustive contre toute synonymie contextuelle : elle doit être enrichie à partir des erreurs éditoriales et des confusions observées. Les items sans quatre choix suffisamment distincts sont ignorés, sans changement de progression.

## Vérification

```sh
cd backend
uv run python -m unittest discover -s tests -v
QUIZ_TEST_POSTGRES=1 uv run python -m unittest discover -s tests -p test_quiz_postgres.py -v
uv run coverage run --source=app.services.quiz_service,app.services.quiz_choices,app.services.fsrs_service,app.services.acquisition_service -m unittest discover -s tests -p test_quiz.py
uv run coverage report -m
cd ../frontend
./node_modules/.bin/tsc --noEmit
```

Les tests PostgreSQL créent des schémas temporaires indépendants et les suppriment ensuite. Les migrations locales ont été comparées avant/après : cinq échéances pour `0003`, sept pour `0004`, aucune modification.

Références : [implémentation officielle py-fsrs](https://github.com/open-spaced-repetition/py-fsrs), [algorithme FSRS](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm), [étapes courtes recommandées par Anki](https://docs.ankiweb.net/deck-options.html).

Validation locale du 6 septembre 2026 : **71 tests réussis** avec PostgreSQL activé, TypeScript et Ruff valides. Les tests couvrent les cinq réussites sans avancer l’horloge, la remise à zéro après erreur, l’alternance de deux/trois fiches, l’erreur en fin de séance sans attente ni nouvelles fiches ajoutées, la reprise d’anciennes pauses, la distinction grammaire/kanji, l’initialisation unique de FSRS, les réponses concurrentes et les migrations. Le parcours navigateur authentifié avait confirmé trois nouveaux mots alternés, cinq réussites chacun et la barre seule sur desktop/mobile. Le contrôle après suppression des pauses confirme une séance ciblée continue en six réponses (une erreur puis cinq réussites), la correction conservée au rechargement, la barre seule et le bilan final ; aucun débordement sur mobile 390 px. Les comptes temporaires et leurs résultats ont été supprimés après contrôle.
