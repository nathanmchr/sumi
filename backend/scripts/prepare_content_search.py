"""Populate only romaji search keys. Preview by default; --write saves a backup."""
import argparse
import csv
import json
from pathlib import Path
import tempfile

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models.content import GrammarItem, KanjiItem, VocabularyItem
from app.utils.romaji import normalize_romaji, romaji_search_key

ROOT = Path(__file__).resolve().parents[2]


def source_romaji(directory: Path) -> dict[tuple[str, str], str]:
    result = {}
    for path in sorted(directory.glob('* Vocab.csv')):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter=';'):
                reading = row.get('Hiragana', '').strip()
                word = row.get('Kanji', '').strip() or reading
                value = row.get('Romaji', '').strip()
                if value:
                    key = (word, reading)
                    if key in result and result[key] != value:
                        raise ValueError(f'Conflicting source romaji: {word} / {reading}')
                    result[key] = value
    return result


def prepare(*, write: bool, content_dir: Path) -> dict:
    source = source_romaji(content_dir)
    summary = {}
    with SessionLocal() as db:
        backup = {}
        pending = []
        for model in (VocabularyItem, KanjiItem, GrammarItem):
            table = model.__table__
            stmt = select(table)
            if write:
                stmt = stmt.with_for_update()
            rows = [dict(row) for row in db.execute(stmt).mappings()]
            backup[table.name] = rows
            changed = 0
            source_matches = 0
            for row in rows:
                if model is VocabularyItem:
                    explicit = source.get((row['japanese'], row['reading']), '')
                    source_matches += bool(explicit)
                    key = romaji_search_key([row['reading'], row['japanese']], explicit)
                elif model is KanjiItem:
                    key = romaji_search_key([*row['onyomi'], *row['kunyomi']])
                else:
                    key = normalize_romaji(row['structure'])
                if key != row['romaji_search']:
                    pending.append((table, row, key))
                    changed += 1
            summary[table.name] = {'rows': len(rows), 'changed': changed, 'source_matches': source_matches}
        if write:
            with tempfile.NamedTemporaryFile(mode='w', prefix='romaji-search-backup-', suffix='.json', delete=False) as handle:
                json.dump(backup, handle, ensure_ascii=False, default=str)
                summary['backup'] = handle.name
            for table, row, key in pending:
                db.execute(update(table).where(table.c.id == row['id']).values(romaji_search=key, updated_at=row['updated_at']))
            for model in (VocabularyItem, KanjiItem, GrammarItem):
                table = model.__table__
                originals = {row['id']: row for row in backup[table.name]}
                for current in db.execute(select(table)).mappings():
                    original = originals[current['id']]
                    if any(value != original[field] for field, value in current.items() if field != 'romaji_search'):
                        raise ValueError(f'Unexpected content change in {table.name}')
            db.commit()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--content-dir', type=Path, default=ROOT / 'contenu csv')
    args = parser.parse_args()
    print(json.dumps(prepare(write=args.write, content_dir=args.content_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
