"""Read-only coverage audit using the vocabulary's kanji-spelling levels."""
import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEVELS = ('N5', 'N4', 'N3', 'N2', 'N1')


def is_kanji(character):
    name = unicodedata.name(character, '')
    return name.startswith(('CJK UNIFIED IDEOGRAPH-', 'CJK COMPATIBILITY IDEOGRAPH-'))


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle, delimiter=';'))


def audit(words, catalogue):
    occurrences = defaultdict(list)
    excluded = Counter()
    for word in words:
        if word['level'] not in LEVELS:
            raise ValueError(f'Invalid word level: {word}')
        if any(is_kanji(c) for c in word['word']) and word.get('spelling_level') not in LEVELS:
            raise ValueError(f'Missing or invalid KanjiLevel for kanji spelling: {word}')
        for character in set(word['word']):
            if is_kanji(character):
                occurrences[character].append(word)
            elif character in '々〆〇ヶヵ':
                excluded[character] += 1
    missing = []
    for character, examples in occurrences.items():
        if character in catalogue:
            continue
        examples = sorted(examples, key=lambda word: (LEVELS.index(word['spelling_level']), word['word'], word['source']))
        missing.append({'kanji': character, 'level': examples[0]['spelling_level'], 'occurrences': examples})
    missing.sort(key=lambda item: (LEVELS.index(item['level']), ord(item['kanji'])))
    return {
        'level_basis': 'KanjiLevel',
        'word_rows': len(words),
        'rows_with_kanji': sum(any(is_kanji(c) for c in word['word']) for word in words),
        'catalogue_kanji': len(catalogue),
        'distinct_word_kanji': len(occurrences),
        'covered': len(set(occurrences) & catalogue),
        'missing_count': len(missing),
        'by_level': {level: sum(item['level'] == level for item in missing) for level in LEVELS},
        'excluded_marks': dict(sorted(excluded.items())),
        'missing': missing,
    }


def source_audits(directory):
    consolidated = directory / 'consolidated'
    paths = [consolidated / 'kanji.csv', consolidated / 'vocabulary.csv']
    fingerprints = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    canonical_kanji = {row['Kanji'].strip() for row in read_csv(consolidated / 'kanji.csv')}
    if not all(len(character) == 1 and is_kanji(character) for character in canonical_kanji):
        raise ValueError('Catalogue contains a non-kanji or a multi-character entry')
    canonical_words = [
        {'word': row['Kanji'] or row['Kana'], 'reading': row['Kana'], 'level': row['Level'],
         'spelling_level': row['KanjiLevel'], 'id': row['ID'], 'source': f'consolidated/vocabulary.csv:{index}'}
        for index, row in enumerate(read_csv(consolidated / 'vocabulary.csv'), 2)
    ]
    return {
        'source_sha256': fingerprints,
        'consolidated': audit(canonical_words, canonical_kanji),
    }


def write_report(result, destination):
    destination.mkdir(parents=True, exist_ok=True)
    principal = result['consolidated']
    with (destination / 'missing-kanji.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(['Kanji', 'SuggestedLevel', 'WordCount', 'ExamplesAtSuggestedLevel', 'AllOccurrences'])
        for item in principal['missing']:
            examples = [word for word in item['occurrences'] if word['spelling_level'] == item['level']]
            writer.writerow([item['kanji'], item['level'], len(item['occurrences']),
                             ' / '.join(dict.fromkeys(word['word'] for word in examples)),
                             json.dumps(item['occurrences'], ensure_ascii=False)])
    (destination / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# Kanjis absents du catalogue JLPT', '',
             'Source principale : catalogue consolide corrige. Comparaison exacte avec tous les kanjis N1-N5, sans normaliser les variantes graphiques.',
             "Niveau propose = KanjiLevel le plus facile parmi les mots contenant ce caractere : N5, N4, N3, N2, N1. Level (apprentissage lexical/kana) n'est pas utilise pour le classement.",
             'Cette version remplace le classement precedent fonde sur Level. Un KanjiLevel absent ou invalide pour une graphie kanji bloque le rapport, sans niveau invente.',
             'Ce classement est deduit du vocabulaire du projet, pas une attribution JLPT officielle. Aucun contenu ni aucune base ne sont modifies.', '',
             '| Source | Mots | Mots avec kanji | Kanjis distincts utilises | Kanjis du catalogue | Absents |',
             '|---|---:|---:|---:|---:|---:|']
    lines.append(f"| Consolide corrige uniquement | {principal['word_rows']} | {principal['rows_with_kanji']} | {principal['distinct_word_kanji']} | {principal['catalogue_kanji']} | {principal['missing_count']} |")
    for level in LEVELS:
        lines += ['', f"## {level} : {principal['by_level'][level]} kanjis", '', '| Kanji | Mots justificatifs au niveau propose | Occurrences, tous niveaux |', '|---|---|---:|']
        for item in principal['missing']:
            if item['level'] == level:
                examples = list(dict.fromkeys(w['word'] for w in item['occurrences'] if w['spelling_level'] == level))
                lines.append(f"| {item['kanji']} | {' / '.join(examples).replace('|', '&#124;')} | {len(item['occurrences'])} |")
    lines += ['', 'Les marques 々, 〆, 〇 et les kana ヶ, ヵ ne sont pas comptes comme des ideogrammes kanji.',
              'Les occurrences completes, niveaux, lectures, identifiants et lignes CSV sont dans audit.json et missing-kanji.csv.',
              'Les empreintes SHA-256 des sources sont conservees dans audit.json.', '']
    (destination / 'missing-kanji.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output' / 'kanji-coverage-2026-09-08')
    args = parser.parse_args()
    result = source_audits(ROOT / 'contenu csv')
    write_report(result, args.output)
    print(json.dumps({k: v for k, v in result['consolidated'].items() if k != 'missing'}, ensure_ascii=False))
    print('Report:', args.output / 'missing-kanji.md')


if __name__ == '__main__':
    main()
