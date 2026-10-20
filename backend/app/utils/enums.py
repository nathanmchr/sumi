from enum import Enum


class ContentType(str, Enum):
    vocabulary = "vocabulary"
    kanji = "kanji"
    grammar = "grammar"


class ReviewStatus(str, Enum):
    new = "new"
    learning = "learning"
    relearning = "relearning"
    fragile = "fragile"
    known = "known"
    review = "review"
    master = "master"


class FuriganaDisplayMode(str, Enum):
    always = "always"
    hover = "hover"
    hidden = "hidden"
