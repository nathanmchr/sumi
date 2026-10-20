# Yomigana et accent mélodique du vocabulaire

Recherche vérifiée le 6 septembre 2026. Périmètre : japonais standard de Tokyo,
mots du catalogue consolidé, préparation locale des demandes Chirp 3 HD.
La préparation d’une demande n’est pas une validation de son résultat sonore.

Livraison initiale vérifiée le 8 septembre 2026 : les 8 038 fiches ont une colonne Yomigana ;
3 475 accents sont retenus automatiquement avec les critères stricts décrits ci-dessous,
et un accent supplémentaire est désambiguïsé explicitement pour 橋 « pont ».
Les 4 562 autres fiches gardent leur lecture sans accent imposé. Les ID, niveaux,
ordre et anciennes colonnes sont inchangés. Aucun nouvel audio n’avait alors été
produit. La régénération autorisée ensuite est décrite dans [le suivi du lot](audio-regeneration.md).

## Colonne directement exploitable

`Kana` reste la lecture pédagogique. `Yomigana`, immédiatement après, conserve la
prononciation destinée à Google, avec les marqueurs d’accent lorsque la source est
suffisamment déterminée. L’ordre, les ID et les niveaux du vocabulaire ne changent pas.

| Exemple | Kana | Yomigana accentué |
|---|---|---|
| 箸 | はし | `^は!し` |
| 橋 | はし | `^はし!` |
| 音色 | ねいろ | `^ねいろ` |
| 塵, lecture ごみ | ごみ | `^ごみ!` |

`^` marque le **début de la phrase accentuelle**, pas la position de la montée.
`!` marque la chute après la more accentuée. `^ねいろ` indique un accent plat
connu ; `ねいろ` seul ne précise aucun accent. Une lecture inconnue ne doit donc
jamais recevoir automatiquement `^` sans `!`. Google accepte hiragana et katakana
et ne documente ici que le dialecte de Tokyo.
[Encodage officiel Google](https://docs.cloud.google.com/text-to-speech/docs/reference/rest/Shared.Types/PhoneticEncoding).

Les alternatives restent séparées par `/` dans leur ordre d’origine. La pause de
`より、ほう` est conservée. `けいけん・する` devient `けいけんする` en phonétique :
seul le séparateur éditorial disparaît, jamais le suffixe `する`.

## Sources d’accents trouvées

| Source | Intérêt | Conditions et décision |
|---|---|---|
| UniDic, NINJAL | Dictionnaire local avec lecture, prononciation et accent ; pas de service distant ni quota pour la consultation locale. | Source retenue. Les éditions modernes CWJ/CSJ concernées proposent notamment une licence BSD modifiée et autorisent l’usage commercial. Conserver version, attribution et notices. [Conditions officielles](https://clrd.ninjal.ac.jp/unidic/commerce_use.html), [FAQ licence](https://clrd.ninjal.ac.jp/unidic/faq.html). |
| OJAD, Université de Tokyo | Référence pédagogique pour des contrôles ponctuels, avec des formes fléchies accentuées. | Usage annoncé pour l’éducation et la recherche académique ; pas de permission générale trouvée pour importer/redistribuer la base. Non importé. [Présentation](https://www.gavo.t.u-tokyo.ac.jp/ojad/eng/pages/home), [conditions](https://www.gavo.t.u-tokyo.ac.jp/ojad/pages/notes). |
| Kanjium | Le dépôt annonce 124 137 mots dans `accents.txt`, avec des positions d’accent. | Données annoncées CC BY-SA 4.0 ; la recherche n’a pas établi la provenance détaillée de chaque annotation. Non importé. [Dépôt et licence](https://github.com/mifunetoshiro/kanjium). |
| WaDoku | Export XML utilisable localement, comportant des accents. | Licence propre : conditions d’attribution et restrictions selon la distribution, la publicité ou l’usage en entreprise. Pas une licence ouverte sans conditions commerciales. Non importé. [Export](https://www.wadoku.de/wiki/display/WAD/Downloads%2Bund%2BLinks), [licence des données](https://www.wadoku.de/wiki/display/WAD/Wadoku.de-Daten%2BLizenz). |

## Interprétation prudente d’UniDic

Le dictionnaire installé est `unidic-3.1.0+2021-08-31` ; ce numéro est distinct
de celui du paquet Python. Les archives officielles proposent aussi des éditions
2025.12, non téléchargées pour cette tâche.
[Versions disponibles](https://clrd.ninjal.ac.jp/unidic/back_number.html).

`aType` donne la position du noyau en **mores** : `0` signifie plat ; plusieurs
valeurs peuvent coexister. Les champs `aConType` et `aModType` décrivent des changements
liés aux combinaisons et aux flexions. Un composé n’hérite donc pas simplement des
accents de chacun de ses kanjis. `きょ` compte pour une more, `きょう` pour deux.
[Manuel UniDic, sections 6.5–6.7](https://clrd.ninjal.ac.jp/unidic/UNIDIC_manual.pdf).

Une correspondance doit porter sur la graphie **et** la lecture attendue. Les
analyses concurrentes, les mots composés découpés en plusieurs unités et les accents
multiples demandent une revue ; on ne choisit pas arbitrairement le premier résultat.
Le journal `_audit/yomigana.json` conserve les décisions par ID, la version et la
provenance. Une annotation de dictionnaire n’est pas une certification humaine du sens
anglais/français ni de l’audio généré.

La politique automatique exige une graphie complète reconnue en un seul mot, la lecture
attendue, un accent unique dans les limites du nombre de mores, et des analyses
concurrentes épuisées sous une limite de 64, toutes concordantes pour le même lemme et
la même morphologie. Les cas hors de ces critères restent sans accent imposé.
Pour 橋, le sens « bridge / pont » permet d’écarter le patronyme concurrent : l’entrée
commune UniDic 29677 a l’accent 2, également illustré dans la référence Google ci-dessus.
Cette décision explicite est vérifiée par ID, sens et preuve lexicale lors de la
reconstruction ; elle ne relâche pas les règles automatiques pour les autres mots.

## Transmission et contrôle sonore

Le générateur transmet la colonne par un `<phoneme alphabet="yomigana">` SSML,
y compris pour une seule lecture. Ce choix a été vérifié avec l’API le 8 septembre :
`custom_pronunciations` refusait `太い / ふとい`, alors que le phonème SSML avec
la même graphie et la même lecture était accepté. Aucun accent n’a été ajouté ou retiré.
Pour plusieurs lectures dans une même fiche, il emploie un phonème par occurrence :
aucun remplacement global ambigu de la même graphie par deux lectures différentes.
Le support SSML de Chirp 3 HD est
documenté en Preview pour les demandes synchrones.
[Documentation Chirp](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd).

Avant une génération complète : écouter un petit lot contrastif (箸/橋, ごみ, 音色,
lectures multiples). Contrôler aussi certains mots avec une particule : un accent
plat et un accent final peuvent être difficiles à distinguer sur le mot isolé.
Les anciens audios restent conservés ; ni la migration du site ni une synthèse
payante ne sont réalisées par la simple modification de ces données.

Le 8 septembre, l’utilisateur a autorisé la régénération. Les 40 premiers mots ont
été produits avec ce format et contrôlés techniquement ; la validation à l’écoute
reste distincte. Le lot complet est reprenable dans `audio/vocabulary-chirp3-yomigana/`.
