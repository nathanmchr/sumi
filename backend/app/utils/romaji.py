"""Search keys from explicit romaji or kana readings, never inferred from kanji."""
import re
import unicodedata

import jaconv


def normalize_romaji(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r"[\s'’ʼ.・-]+", '', value)


def romaji_search_key(readings: list[str], explicit: str = '') -> str:
    if explicit.strip():
        return ' / '.join(normalize_romaji(part) for part in re.split(r'[/／]', explicit) if part.strip())
    keys = []
    for reading in readings:
        for part in re.split(r'[/／・,;]', reading):
            kana = jaconv.kata2hira(unicodedata.normalize('NFKC', part)).strip().replace('.', '').replace('-', '')
            if not kana or not re.fullmatch(r'[ぁ-ゖー]+', kana):
                continue
            romanized = jaconv.kana2alphabet(kana)
            # kana2alphabet writes prolonged vowels as "-"; expand them for typing.
            expanded = ''
            for char in romanized:
                expanded += expanded[-1] if char == '-' and expanded and expanded[-1] in 'aeiou' else char
            key = normalize_romaji(expanded)
            if key and key not in keys:
                keys.append(key)
    return ' / '.join(keys)
