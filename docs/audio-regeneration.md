# Régénération Yomigana — 8 septembre 2026

Mise à jour du 9 septembre : lot terminé et intégrité des 8 038 fichiers vérifiée,
mais deux réponses quasi muettes identifiées ensuite à partir du signalement de
ええ. Le [diagnostic et les essais contrôlés](audio-short-words-diagnostic.md)
établissent un échec intermittent de synthèse. Le générateur rejette désormais
ces sorties, y compris en cache, et retente la même requête. Après confirmation
d'audibilité par l'utilisateur, les deux candidats de ええ et さん ont été publiés
le 9 septembre. Leurs liens sont versionnés par empreinte pour éviter de conserver
les anciennes réponses en cache. Les 8 038 fichiers passent désormais le contrôle
technique et de signal ; cela ne certifie pas leur justesse linguistique.

L’utilisateur a autorisé une nouvelle génération des 8 038 entrées consolidées.
Destination distincte : `audio/vocabulary-chirp3-yomigana/` ; les anciens audios de
`audio/vocabulary/` restent conservés. L'historique ci-dessous décrit le lancement
et la reprise du lot ; sa fin technique ne constitue pas une validation d'écoute.

## Reprise et comptage

Processus indépendant lancé pour ce lot : PID 49954. Journal :
`.local/audio-jobs/yomigana-20260908.log`. Les premières erreurs dans ce journal
concernent l’essai antérieur de `custom_pronunciations`, corrigé avant la reprise.
Vérifier les dernières lignes et la progression du manifeste, pas seulement
l’absence ou la présence d’un ancien message d’erreur.

Une fois le processus terminé (ne jamais lancer deux écrivains simultanément),
la commande suivante reprend uniquement les requêtes/fichiers manquants ou modifiés :

```bash
backend/.venv/bin/python -u backend/scripts/generate_vocab_audio_google.py --all
```

`--ids ID1 ID2` permet un lot ciblé en conservant l’ordre du catalogue. Les
signatures incluent la requête exacte et les paramètres ; ne pas utiliser `--force`
pour une simple reprise. Le manifeste contient une fiche par ID, pas par ancienne
ligne CSV. À la fin, attendre 8 038 références distinctes, 8 038 fichiers référencés
non vides, des empreintes concordantes et aucun fichier temporaire.

Trois premiers essais devenus non référencés après le changement d’encodage
ont été déplacés, sans suppression, vers `.local/audio-jobs/superseded-samples/`.
Ils ne font pas partie des 8 038 livrables. Pendant la génération, un WAV peut
précéder brièvement l’enregistrement atomique de son entrée dans le manifeste.
Ne déplacer aucun autre fichier non référencé tant que le processus écrit : le
nettoyage final doit comparer un manifeste et un dossier au repos.

## Encodage et coût

Google a accepté les premières lectures accentuées mais refusé la personnalisation
globale `太い / ふとい` (HTTP 400). Le même couple graphie/lecture a été accepté
avec `<phoneme alphabet="yomigana">` en SSML. Le générateur utilise désormais ce
format pour tous les mots : une balise par occurrence, lecture et accents de la
colonne Yomigana inchangés. Les 40 premiers mots ont été vérifiés via l’API avant
reprise. Aucun mot n’est ignoré pour masquer une erreur.

Les balises SSML sont comptées dans la facturation Google. Le corpus actuel totalise
544 011 caractères, soit 16,3203 USD hors gratuité à 30 USD/million. Le palier Chirp
est d’un million de caractères gratuits par mois ; son solde pour ce compte n’a
pas été vérifié. Les essais, répétitions ou autres usages s’ajoutent au lot.
[Tarification officielle](https://cloud.google.com/text-to-speech/pricing),
[SSML Chirp](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd),
[phonèmes japonais](https://docs.cloud.google.com/text-to-speech/docs/phonemes).

## Raccordement du site

Le service partagé `catalog_audio` résout les identités par graphie, lecture et sens
anglais via `vocabulary.csv` et `_audit/source-map.csv`. Cela couvre les 8 407 fiches
historiques, y compris leurs variantes fusionnées dans le catalogue. Les deux
anciennes notations de ミリ ont des correspondances explicites et gardées sous
conditions dans `vocabulary_audio_legacy_overrides.json`. Une ambiguïté reste sans
correspondance ; l’ID seul ou les kana seuls ne suffisent pas.

Chaque demande du site utilise un instantané cohérent du manifeste. La suivante
découvre les nouveaux fichiers. Lecture, yomigana, version, chemin et empreinte du
fichier sont contrôlés. En attendant, le repli vient du catalogue relu, et non d’un
ancien audio volontairement invalidé. Le mécanisme existant d’alias reste disponible
pour les fiches non présentes dans le catalogue.

Ce raccordement est partagé par les fiches vocabulaire, le vocabulaire associé aux
kanjis et les séances, y compris les questions déjà préparées. Les anciennes URL
restent servies. Aucun enregistrement audio n’est marqué validé à l’écoute.

## Correction minimale du contenu

41 lectures historiques ont été alignées sur le catalogue, avec mise à jour des
furigana, romaji affichés et index romaji. Identifiants, niveaux, traductions,
relations, ordre en base et progression sont conservés. La migration complète des
trois catalogues et de leurs fusions reste en attente de précision de l’utilisateur.

Sauvegarde réversible : `.local/audio-jobs/readings-before-yomigana.json` (privée).
Le script refuse d’écraser une sauvegarde et un retour arrière refuse d’écraser
une modification ultérieure. Depuis `backend` :

```bash
.venv/bin/python -m scripts.prepare_catalog_readings
.venv/bin/python -m scripts.prepare_catalog_readings --restore ../.local/audio-jobs/readings-before-yomigana.json
```

La première commande est une prévisualisation sans écriture. La seconde est un
retour arrière explicite, pas une étape normale de vérification. Ne pas réimporter
les quinze anciens CSV : cela réintroduirait les lectures désormais corrigées.

Vérifications : 268 tests backend (210 réussis, 58 optionnels ignorés), TypeScript
valide, relecture des 41 modifications idempotente, 10 états d’apprentissage et
44 historiques conservés. API réelle et WAV HTTP 200 contrôlés sur ごみ, 塵, 箸 et
音色 ; ごみ et 塵 partagent bien le nouvel audio, 音色 expose ねいろ.
