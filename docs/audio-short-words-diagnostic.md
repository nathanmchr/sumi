# Audios quasi muets : ええ et さん

Diagnostic du 9 septembre 2026. Les essais ont été réalisés séparément dans
`output/audio-diagnostics-20260909/`. Après validation utilisateur, seuls les deux
audios ont été publiés sur le site. Aucun catalogue ni état d'apprentissage n'a
été modifié. Les essais intermédiaires ont ensuite été déplacés dans la corbeille.

## Conclusion établie

L'échec est intermittent côté service de synthèse : une requête strictement
identique peut produire différents signaux, dont un WAV quasi muet. Pour ええ,
les octets défectueux ont été reproduits exactement, y compris sans balise
phoneme et en texte brut. Le générateur enregistrait ces octets sans découpe ;
le serveur les distribuait sans modification. Ce n'est donc pas un défaut du
lecteur, une erreur de correspondance du manifeste, ni un problème provoqué
uniquement par Yomigana. Cela ne permet pas d'identifier le mécanisme interne
du modèle Google ou de son infrastructure.

Le défaut apparaît aussi avec une autre voix, Kore. Aucun essai ne justifie de
supprimer les kana imposés, de modifier l'accent ou de changer toutes les voix.
L'hypothèse d'une fragilité sur certains mots isolés très courts est compatible
avec les résultats, mais n'est pas une règle démontrée pour tous les mots courts.

## Comparaison contrôlée

Chaque variante est répétée, avec ordre entrelacé. Voix Aoede, débit 1, sortie
LINEAR16, sauf la variante Kore où seul le nom de voix change. Aucun appel de
ces deux matrices n'utilise de reprise automatique.

| Entrée | Variante | Essais | Quasi muets |
|---|---|---:|---:|
| ええ | Requête originale, phoneme Yomigana + point japonais | 13 | 1 |
| ええ | Phoneme sans point final | 3 | 0 |
| ええ | SSML simple, sans phoneme | 3 | 1 |
| ええ | Texte brut | 3 | 1 |
| ええ | Requête originale, voix Kore | 3 | 0 |
| さん | Requête originale, phoneme Yomigana + point japonais | 13 | 0 |
| さん | Phoneme sans point final | 3 | 1 |
| さん | SSML simple, sans phoneme | 3 | 0 |
| さん | Texte brut | 3 | 0 |
| さん | Requête originale, voix Kore | 3 | 3 |
| はい, témoin | Requête originale | 3 | 0 |

53 appels, zéro erreur HTTP remontée. Ces petits effectifs décrivent les essais,
pas des taux de fiabilité généralisables. « Non quasi muet » ne signifie pas
« prononciation validée ». Les requêtes exactes, réponses WAV, empreintes et
mesures étaient conservées dans `baseline/` et `reproduce/`. Après nettoyage,
les traces JSON restent dans `.local/audio-jobs/before-approved-20260909/` ;
les WAV expérimentaux sont récupérables dans la corbeille jusqu'à son vidage.

La requête originale de ええ a donné, entre autres, 0,60 s à -3,12 dBFS,
0,96 s à -7,85 dBFS et 0,28 s à -40,12 dBFS. Ce dernier fichier a la même
empreinte que le défectueux servi par le site :
`3bce95694234a20e1468546f82ace26742f64ebbe3fe51a3f25423bbe8e20f13`.

Le format employé est conforme au
[Yomigana documenté par Google](https://docs.cloud.google.com/text-to-speech/docs/phonemes#japanese_yomigana).
Les accents sont facultatifs ; leur absence ne doit pas être assimilée à une
erreur syntaxique. La documentation ne fournit pas l'explication interne de
l'anomalie observée.

## Garde-fou du générateur

Le correctif reste dans `generate_vocab_audio_google.py`, sans nouvelle dépendance :

- Décodage des WAV et MP3 ; rejet des fichiers illisibles, vides ou non finis.
- Rejet conservateur si le niveau de crête est inférieur à -35 dBFS.
- Nouvelle tentative de la même requête, avec délai et limite `--max-retries`.
- En cas d'échec persistant, arrêt explicite, sans écrasement de l'ancien fichier
  ni du manifeste. Ni accent, ni voix, ni lecture ne sont modifiés pour contourner l'échec.
- Les fichiers en cache repassent ce contrôle avant réutilisation.
- Aucune durée minimale imposée : un mot court n'est pas forcément incorrect.

Avant remplacement, sur les 8 038 fichiers, le contrôle rejetait exactement ええ et さん ;
les 8 036 autres passent ce seul contrôle de signal. Leurs crêtes sont toutes
supérieures à -15 dBFS, contre -40,1 et -37,0 pour les deux fichiers concernés.
Cela ne détecte pas une mauvaise lecture audible, une intonation incorrecte,
une répétition ni nécessairement un souffle plus fort. La validation d'écoute
reste indispensable.

## Candidats validés puis publiés

Le générateur corrigé a été exécuté ensuite uniquement pour les deux ID, dans
`candidates/`, avec une reprise maximum par mot. Il a rejeté une nouvelle
réponse quasi muette pour ええ, puis accepté la tentative suivante. さん a passé
le contrôle au premier appel. Aucune donnée de production n'a été modifiée.

- ええ : `candidates/2b55b5c163b975e19e6f1213.wav`, 1,40 s, crête -4,90 dBFS.
- さん : `candidates/d538e9243385bea8b89a5398.wav`, 0,84 s, crête -3,34 dBFS.

L'utilisateur a confirmé entendre ces deux candidats et demandé leur publication.
Le manifeste conserve `pronunciation_verified: false` et ajoute une
`listening_validation` limitée à l'audibilité acceptée par l'utilisateur : ce
n'est pas une certification linguistique de l'accent.

Les fichiers publiés sont désormais :

- `audio/vocabulary-chirp3-yomigana/2b55b5c163b975e19e6f1213.wav`
- `audio/vocabulary-chirp3-yomigana/d538e9243385bea8b89a5398.wav`

Les URL du site incluent une version dérivée des octets validés (`?v=…`) ; une
nouvelle réponse de synthèse ne réutilise donc pas la même clé de cache si son
contenu a changé. API vocabulaire réelle et fichiers HTTP vérifiés avec les
empreintes des candidats approuvés. Audit complet après publication : 8 038
références valides, aucun signal quasi muet, ordre inchangé et exactement deux
enregistrements modifiés. La sauvegarde des deux anciens WAV, de l'ancien manifeste
et des traces JSON est dans `.local/audio-jobs/before-approved-20260909/`.
Les 60 fichiers intermédiaires ont été déplacés dans la corbeille sous
`audio-diagnostics-20260909-validated` ; ils restent récupérables tant qu'elle
n'est pas vidée. Le script ponctuel de publication a été supprimé.

Les essais et la vérification réelle du correctif représentent 56 appels
applicatifs, environ 0,0894 USD au tarif indicatif texte avant gratuité ; ce
n'est pas une lecture de la facture Google.

Tests : 41 tests ciblés du générateur et des services audio réussis, y compris
reprise sans modification de requête, limite d'essais, WAV/MP3, conservation
des anciens fichiers/manifeste et rejet d'un cache quasi muet avec empreinte valide.
Après publication et test d'invalidation du cache : 42 tests audio réussis.
Suite backend complète : 327 tests, 256 réussis et 71 optionnels ignorés.
