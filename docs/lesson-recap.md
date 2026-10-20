# Bilan cumulatif exhaustif

Chaque theme se termine par une lecon autonome « Bilan cumulatif », apres toutes ses sous-lecons et avant le theme suivant. Les sous-lecons n'integrent plus de bilan. Celui-ci est verrouille, dans la liste et dans l'API, tant que toutes les sous-lecons de son theme ne sont pas terminees par cet utilisateur.

Le bilan contient un exercice pour chaque mot, point de grammaire et kanji introduit dans le theme et dans les lecons precedentes terminees par cet utilisateur. Les lecons sautees, futures ou terminees par un autre utilisateur sont exclues. Les themes precedents ne doivent pas tous etre termines pour ouvrir ce bilan, mais leurs lecons deja terminees participent au cumul.

Il n'y a aucun echantillonnage ni plafond : dans le parcours N5 publie, le premier bilan de theme compte 85 questions ; le dernier en compte 838 (668 mots, 84 points de grammaire et 86 kanji) si toutes les sous-lecons sont terminees. Le test est organise en sections vocabulaire, grammaire et kanji. Un exercice couvre un element pedagogique, pas chacune de ses lectures ou chaque exemple. Le parcours compte 109 sous-lecons et 15 bilans, soit 124 entrees.

## Questions et correction

- Vocabulaire et grammaire : reutilisation des exercices existants et de leurs corrections bilingues ; priorite au QCM de reconnaissance pour le vocabulaire.
- Kanji : associer une signification a la bonne forme parmi quatre caracteres deja rencontres. Un corpus trop petit pour quatre caracteres utilise une saisie du caractere, sans inventer de distracteurs. Tous les kanji du N5 publie disposent de quatre choix.
- Correction serveur uniquement ; aucune solution ni regle d'acceptation n'est exposee avant reponse.
- Les erreurs sont enregistrees sans bloquer la suite. Un score distinct du bilan est affiche a la fin. Le bilan ne modifie pas les etats SRS.

## Persistance et compatibilite

Les bilans sont des lignes de `lessons` avec `content.kind = "theme_recap"`, des `prerequisite_ids` et une position apres la derniere sous-lecon du theme. Ils n'introduisent aucun nouvel item : leurs compteurs de contenu sont nuls pour ne pas doubler les totaux du theme. Les reimports republient ces bilans de facon idempotente.

`lesson_progress.recap_steps` contient un instantane bilingue des exercices et leurs donnees de correction, initialise au premier enregistrement de la lecon bilan. L'ordre du contenu initial reste dans `step_order`. Cursor, revisions, verrou de ligne et commande idempotente couvrent aussi le bilan.

Fermer une page ou changer de langue ne reinitialise pas le test. Terminer une autre lecon dans un autre onglet n'ajoute pas de nouvelles questions a un test deja fige. Les anciennes sous-lecons deja terminees restent terminees. Si une progression se trouvait dans un ancien bilan integre, son curseur revient a la fin du contenu initial et cette sous-lecon est terminee. Si elle etait encore dans le contenu, son curseur est conserve. Les questions et reponses des anciens bilans restent stockees pour historique, mais sont exclues du flux et du score de la sous-lecon. Le nouveau bilan du theme possede sa propre progression ; les anciennes reponses ne le valident pas automatiquement.

Migration depuis le dossier `backend` : `.venv/bin/python -m alembic upgrade head` (revision `0011_lesson_recap`). Ajout nullable, sans changement de contenu ni suppression de progression. Le downgrade refuse de supprimer des bilans sauvegardes.

Publication et transition des bilans integres : `.venv/bin/python scripts/publish_theme_recaps.py` previsualise le changement dans une transaction annulee ; ajouter `--apply` pour publier. Les positions sont reordonnees sans changer les IDs ni les versions des sous-lecons. Les reponses existantes ne sont pas supprimees. Cette transition a ete appliquee en developpement local.

La taille cumulee des instantanes croit avec les lecons terminees. Pour des parcours plus volumineux, envisager une banque de questions versionnee referencee par ID ; pour ce MVP, les instantanes evitent toute reinterpretation d'un test en cours lors d'une correction de contenu.

Tests : `python -m unittest discover -s tests -p 'test_*recap*.py'` depuis `backend`, et `frontend/tests/lesson-recap.browser.js` / `frontend/tests/lesson-unit-counts.browser.js` avec une page Playwright sur le serveur existant. Les tests n'ecrivent aucune progression utilisateur reelle.
