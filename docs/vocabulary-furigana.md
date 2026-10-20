# Furigana du vocabulaire

Les cinq CSV de vocabulaire possèdent une colonne `Furigana` contenant une liste JSON de segments. Le serveur valide ces données à l’import ; le navigateur les affiche sans recalcul linguistique.

```json
[{"surface":"お"},{"surface":"母","reading":"かあ"},{"surface":"さん"}]
```

Les composés décomposables utilisent une annotation par kanji : `日/にち・曜/よう・日/び`, `学/がっ・校/こう`. Les lectures indivisibles restent groupées : `今日/きょう`, `大人/おとな`. La granularité dépend du couple graphie/lecture : `今日/こんにち` peut ainsi utiliser `今/こん・日/にち`.

## Validation

Chaque ligne est contrôlée avant écriture ou import :

- La concaténation des surfaces reproduit exactement le mot.
- Seuls des segments entièrement composés de kanjis portent une lecture.
- Dès qu’un mot est annoté, tous ses kanjis doivent être couverts.
- Les lectures des segments **et les kana laissés sans annotation** reconstituent la lecture source : `お + かあ + さん = おかあさん`.
- La comparaison normalise Unicode et katakana/hiragana. Les variantes séparées par `/` doivent correspondre exactement : aucune combinaison supplémentaire n’est autorisée.
- Un découpage lexical disponible est également comparé aux segments enregistrés lors de l’audit.

Une entrée volontairement sans ruby conserve le mot entier comme surface. Elle n’est pas considérée comme une lecture validée par reconstruction. Une concaténation correcte ne démontre pas, à elle seule, que la prononciation source ou chaque attribution à un kanji est correcte.

## Audit du 6 septembre 2026

Les **8 410 lignes** ont été parcourues individuellement par le validateur et l’audit lexical. Les couples graphie/lecture sont confrontés à JMdict, en respectant ses restrictions de graphie et de lecture ; KANJIDIC2 complète les kanjis isolés. UniDic fournit un contrôle supplémentaire, insuffisant à lui seul pour confirmer une entrée. Des cas douteux ont été examinés manuellement dans les dictionnaires en ligne, avec sources et conclusions conservées.

| Résultat | Lignes |
| --- | ---: |
| Correspondance JMdict | 7 133 |
| Correspondance KANJIDIC2 | 22 |
| Confirmation manuelle avec référence en ligne | 5 |
| Aucun ruby nécessaire | 1 134 |
| Lecture non confirmée ou source incohérente, ruby retiré | 116 |

Parmi les **7 160 lignes annotées**, 7 100 utilisent un découpage lexical confirmé par JmdictFurigana. Les 60 autres conservent un découpage prudent par groupes de kanjis, aligné sur les kana, faute de correspondance de segmentation univoque. Leur lecture globale est confirmée, mais cela ne constitue pas une certification manuelle de chaque limite interne.

Les 116 entrées signalées ne sont pas toutes des erreurs certaines : certaines lectures rares restent à confirmer. Des incohérences source sont cependant documentées, par exemple `途中/つちゅう` ou `灰皿/はいさら`. Les graphies, lectures, traductions et autres colonnes source n’ont pas été corrigées implicitement. Le rendu n’ajoute pas de furigana à ces entrées.

Cet audit n’est **pas une relecture humaine certifiée des 8 410 mots**, ni une garantie linguistique de zéro erreur.

- [Audit complet, une ligne par entrée](vocabulary-furigana-audit.csv).
- [Entrées nécessitant une vérification](vocabulary-furigana-review.csv).
- [Vérifications manuelles et liens des dictionnaires consultés](vocabulary-furigana-manual-review.json).
- [Méthode, décomptes et empreintes des sources](vocabulary-furigana-audit.json).

## Reproduire les contrôles

Depuis la racine du projet, contrôler la colonne existante sans modifier les CSV :

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/prepare_vocab_furigana.py
```

Préparer les colonnes manquantes et affiner les découpages automatiques avec le JSON extrait de la publication JmdictFurigana ; les corrections explicites existantes sont conservées :

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/prepare_vocab_furigana.py --write --reference /tmp/furigana-reference.json
```

L’écriture crée une sauvegarde temporaire dont le chemin est affiché. La génération ne remplace pas l’audit lexical et la vérification des nouvelles entrées.

Pour refaire l’audit avec les fichiers de référence téléchargés et un environnement contenant fugashi/UniDic :

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/audit_vocab_furigana.py --jmdict /tmp/furigana-JMdict_e.gz --kanjidic /tmp/furigana-kanjidic2.xml.gz --reference /tmp/furigana-reference.json
```

## Sources et attribution

La colonne de segmentation adapte les données de **Doublevil et des contributeurs de [JmdictFurigana](https://github.com/Doublevil/JmdictFurigana)**, publication [2.3.1+2026-08-25](https://github.com/Doublevil/JmdictFurigana/releases/tag/2.3.1%2B2026-08-25). Les adaptations comprennent le format `surface`/`reading`, la normalisation des lectures, la fusion des limites communes aux variantes et le retrait des annotations non confirmées. Ces données dérivées restent sous la licence Creative Commons Attribution-ShareAlike annoncée par le projet.

Les références lexicales proviennent de **l’Electronic Dictionary Research and Development Group**, [JMdict](https://www.edrdg.org/jmdict/j_jmdict.html) et [KANJIDIC2](https://www.edrdg.org/wiki/index.php/KANJIDIC_Project). Voir leurs [conditions de licence et attribution](https://www.edrdg.org/edrdg/licence.html). Les références en ligne des décisions manuelles figurent dans le fichier de relecture lié ci-dessus.

## Intégration et vérifications

La synchronisation a mis à jour uniquement les segments de 8 406 entrées en base, après sauvegarde complète du vocabulaire et comparaison de tous les autres champs. Une entrée en kana, sans correspondance source exacte, est restée inchangée. Les progrès et les audios ne sont pas modifiés. Les anciens instantanés de questions ne sont pas réécrits.

Vérifications : 17 tests ciblés réussis ; suite backend de 86 tests, dont 52 exécutés avec succès et 34 ignorés ; TypeScript valide. Les modes toujours visible, survol/focus et masqué ont été contrôlés dans un navigateur à 390 et 1 440 pixels, sur cinq mots issus de la base synchronisée avec réponses API de test. Aucune reconstruction incorrecte détectée parmi les entrées annotées et aucun débordement horizontal dans ces scénarios.
