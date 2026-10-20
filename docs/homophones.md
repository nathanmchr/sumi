# Comparateur de mots de meme lecture

Acces : bibliotheque de vocabulaire > Comparer les homophones, ou depuis une fiche
pour ouvrir directement sa lecture. Route : `/study/vocabulary/homophones?q=...`.

## Donnees et API

`GET /api/v1/content/homophones?q=hashi&locale=fr&offset=0&limit=20`
requiert une session. Reponse : `groups[{reading, words}]`, `total`, `offset`, `limit`.
Recherche limitee a 100 caracteres, pages de 1 a 50 groupes, langues en/fr.
La recherche couvre kana, romaji, graphie et sens ; un resultat contient toujours
tous les membres du groupe, meme si un seul correspond au terme recherche.

Le service lit uniquement les champs necessaires du catalogue et les traductions
en requetes groupees. Aucune nouvelle table, migration ou generation audio.
Le regroupement en memoire est adapte au catalogue actuel (~8 400 mots) ; pour un
catalogue sensiblement plus grand, persister et indexer la lecture normalisee a
l'import avant de deplacer le regroupement en SQL.

- Normalisation Unicode NFKC, puis katakana vers hiragana. Longueurs de voyelles,
  petits kana et geminations sont conserves. Pas de lecture devinee depuis les kanjis.
- Lectures multiples, annotations et lectures invalides exclues, plutot que d'associer
  un audio a une prononciation incertaine.
- Doublons exacts graphie/lecture/sens source et traductions regroupes entre niveaux. Une fiche avec
  audio est preferee, puis le niveau le plus accessible. Les autres sens restent distincts.
- Groupes composes exclusivement de graphies d'un meme ensemble de sens exclus. Il s'agit
  de candidats a comparer, pas d'une classification lexicographique des homophones.
- Resolution audio identique aux fiches et aux seances, y compris les alias existants.
  Un fichier partage ne sert jamais de preuve pour fusionner deux mots.
- Traduction selon la langue de contenu, avec la langue effective exposee en cas de repli.

## Ecoute

Un seul lecteur par comparaison, sans lecture automatique a l'ouverture. Ecoute d'un
mot ou de tous les audios disponibles dans l'ordre affiche, avec 450 ms entre les mots.
Arret lors du changement de groupe, du filtrage ou de la navigation. Vitesse normale
ou 0,8x avec conservation de la hauteur via `preservesPitch` du navigateur.
Audios absents desactives et erreurs de chargement/lecture visibles. Les fichiers
qui ne demarrent pas ou restent en attente sont interrompus apres 15 secondes.
Les fichiers identiques entre fiches sont signales, sans pretendre detecter tous les
doublons sonores.

## Limite pedagogique

Les clips existants n'ont pas d'annotations d'accent tonal verifiees. Le comparateur
ne produit donc ni courbe d'accent artificielle, ni verdict automatique "meme accent"
ou "accent different". Il compare les sons fournis, pas une reference linguistique.
Une evolution fiable exigerait des enregistrements/annotations documentes par lexeme,
variete de japonais et contexte, avec provenance et droits d'utilisation.

L'interface propose un lien externe vers le [dictionnaire OJAD](https://www.gavo.t.u-tokyo.ac.jp/ojad/eng/pages/usage),
qui fournit types d'accent et exemples audio. Aucun audio OJAD n'est importe ni integre.

## Verification

Depuis `backend` : `.venv/bin/python -m unittest discover -s tests -p 'test_homophones.py'`.
Depuis `frontend` : `./node_modules/.bin/tsc --noEmit`.

Verification navigateur effectuee avec un compte temporaire sur l'API et les audios
reels : WebKit, vues 1440/768/390/320 px, clavier, FR/EN, navigation, pagination,
lecture successive, vitesse, interruptions et reprise apres erreur. Les cas reseau
et audio absent sont simules uniquement dans le navigateur de test. Compte supprime
apres verification ; aucune progression ou donnee pedagogique modifiee.
