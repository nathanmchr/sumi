# Graphies alternatives et lectures multiples

Correction du 9 septembre 2026. Les sept audios ont été validés à l’écoute
par l’utilisateur et publiés sur le site : おばさん d’abord, puis les six autres.
Le dossier d’essais a été nettoyé. L’historique ci-dessous décrit la préparation
initiale et les deux publications successives.

## Publication des six derniers audios

Après validation « tout est bon », les six WAV de はじめ, まるい, かわ, おじさん,
かたい et つくる ont été copiés dans le dossier servi. Le manifeste a été remplacé
atomiquement après comparaison : exactement six entrées modifiées sur 8 038,
identifiants et ordre conservés, les 8 032 autres entrées inchangées, dont おばさん.

Contrôle des sept fiches via l’API réelle : URL versionnée attendue, HTTP 200 et
empreinte identique au fichier approuvé pour chacune. Aucune nouvelle génération,
aucune modification de base, de catalogue ou de progression, aucun redémarrage.
Les nouvelles validations d’écoute ne sont pas une certification experte de l’accent.

Sauvegardes : `.local/audio-jobs/before-six-spellings-20260909/`.
Manifeste final : `781b08cc66ae40f1d4e00cb4ddb242d60ee45bf9014583267c2df3c0238ffae7`.
Les anciens WAV restent disponibles pour les liens historiques et le retour arrière.

Le dossier `output/audio-spelling-variants-20260909`, qui contenait les six doublons
WAV et leur manifeste d’essais, a été déplacé dans la corbeille sous
`audio-spelling-variants-20260909-validated`. Il reste récupérable. Aucun candidat
de ce lot ne reste à valider.

## Publication validée de おばさん

Le site sert désormais `4b37819ad832af7f137febcb.wav?v=ead471c9396d3608` pour
la fiche 伯母さん/叔母さん. API réelle, réponse HTTP 200 et empreinte du WAV
vérifiées après remplacement atomique du manifeste. Une seule entrée modifiée,
les 8 037 autres et leur ordre restent identiques. Aucune génération Google,
aucune modification du catalogue ou de la base, aucun serveur relancé.

Le champ `listening_validation` enregistre l’accord utilisateur sur une occurrence
unique de おばさん, sans répétition. `pronunciation_verified` reste faux : cet accord
n’est pas une certification experte de l’accent.

Sauvegarde des manifestes avant publication : `.local/audio-jobs/before-obasan-20260909/`.
Ancien WAV conservé pour les anciennes URL et un éventuel retour arrière.
Le seul doublon de test validé a été déplacé dans la corbeille sous
`obasan-validated-20260909-4b37819ad832af7f137febcb.wav` et retiré du manifeste
de candidats, qui référence désormais six fichiers présents et vérifiés.

Empreinte du manifeste servi après publication :
`394e5cf8c2f1e803c44fb921a4d7a00a228c4ec7921e6f62925d2dec7dc34c28`.

## Règle

Lorsqu'une graphie contient `/` ou `／` mais qu'une seule lecture est renseignée,
le texte à l'intérieur de la balise phoneme est cette lecture kana une seule fois.
L'attribut Yomigana, y compris ses éventuels marqueurs d'accent, reste inchangé.
La graphie d'affichage n'est pas modifiée.

Il ne faut pas sélectionner aveuglément le premier fragment : `堅/硬/固い`
abrège des graphies et `堅` seul ne représente pas la graphie complète de l'adjectif.
La lecture vérifiée `かたい` évite de deviner la reconstruction.

Les vraies alternatives de lecture sont préservées, avec une occurrence par
lecture et dans l'ordre de la source. Pour la fiche 何, le catalogue contient
`なん / なに`, le Yomigana `なん/なに`, et le générateur conserve exactement les
deux occurrences `なん` puis `なに`. Un test explicite couvre aussi l'ordre inverse
lorsqu'il est fourni. Les vingt fiches du corpus à lectures multiples gardent
leurs requêtes précédentes, sans déduplication ni réordonnancement.

## Candidats séparés

Dossier : `output/audio-spelling-variants-20260909/`, avec son propre manifeste.
Sept appels Google ont réussi au premier essai, sans reprise de signal ni erreur
API, en 3,9 secondes pour la boucle de génération. Texte SSML : 471 caractères,
soit environ 0,01413 USD indicatif avant gratuité ; facture réelle non consultée.

| Graphie conservée | Lecture unique envoyée | Fichier candidat | Durée |
|---|---|---|---:|
| 初め/始め | はじめ | bf834dc3385e4f69513af9a6.wav | 1,12 s |
| 伯母さん/叔母さん | おばさん | 4b37819ad832af7f137febcb.wav | 1,12 s |
| 丸い/円い | まるい | 215998df3963dcd0c492312d.wav | 0,76 s |
| 川/河 | かわ | 760daa5f12470af4e563afa6.wav | 0,92 s |
| 伯父さん/叔父さん | おじさん | 7d846214004ca68b7b5b509a.wav | 1,08 s |
| 堅/硬/固い | かたい | cf5d740a00cce7cadc4fd3f8.wav | 0,72 s |
| 作る/造る | つくる | 4548e787b276f6f12bdd971a.wav | 0,72 s |

Les sept requêtes ont une seule balise phoneme contenant uniquement la lecture.
Les WAV passent le décodage et le contrôle de signal, et leurs empreintes
correspondent à leur manifeste. Cela ne valide pas automatiquement la justesse
de la prononciation ou le nombre de mots réellement entendus : ils restent
`pronunciation_verified: false`, en attente de validation perceptive.

## Périmètre vérifié

- Exactement sept requêtes modifiées sur 8 038 ; les 8 031 autres sont identiques.
- Les signatures de fichier changent pour ces sept requêtes, donc les anciens
  fichiers ne seront pas réutilisés après une génération avec le correctif.
- Aucune modification de CSV, de base, de progression, ni du manifeste servi.
- Les deux audios validés précédemment, ええ et さん, restent inchangés.
- Les essais restent disponibles jusqu'à validation, puis seront nettoyés comme convenu.

Empreintes avant/après identiques :

- `vocabulary.csv` : `66bfb45716876d7d74c28c59aa973ce5dab6ca3fe8cf9c5792038b5dc0c67597`.
- Manifeste servi : `9621c2104f8e67cfdd414b532146d1b54245c618d4325ec9a8b3f63dfac53162`.

Tests dédiés : sept cas réels, slash pleine largeur, conservation de l'entrée
source et des accents, graphie abrégée, invalidation de l'ancien nom de fichier,
et conservation explicite de nan/nani dans les deux ordres fournis.

Suite backend vérifiée : 348 tests, 271 réussis et 77 optionnels ignorés.
