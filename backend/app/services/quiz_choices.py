"""Conservative bilingual collision checks for meaning questions."""

import math
import random
import re
import unicodedata

RNG = random.SystemRandom()
STOP_WORDS = set(
    "a an the to of in on at for and or with be have do one some something someone le la les un une des du de d l et ou en au aux se s être avoir faire quelque chose quelqu quelquun très plus par pour to as one's".split()
)
SYNONYMS = [
    {"car", "automobile", "auto", "voiture"},
    {"bike", "bicycle", "vélo", "bicyclette"},
    {"house", "home", "maison", "domicile"},
    {"job", "work", "emploi", "travail"},
    {"buy", "purchase", "acheter", "achat"},
    {"begin", "start", "commencer", "débuter"},
    {"end", "finish", "terminate", "finir", "terminer", "achever"},
    {"happy", "glad", "joyful", "heureux", "content", "joyeux"},
    {"big", "large", "grand", "gros"},
    {"small", "little", "petit"},
    {"fast", "quick", "rapid", "rapide", "vite"},
    {"speak", "talk", "parler", "discuter"},
    {"see", "look", "watch", "voir", "regarder"},
    {"eat", "consume", "manger", "consommer"},
    {"friend", "pal", "ami", "copain"},
    {"teacher", "instructor", "professor", "professeur", "enseignant", "instituteur"},
    {"doctor", "physician", "médecin", "docteur"},
    {"student", "pupil", "élève", "étudiant"},
    {"shop", "store", "boutique", "magasin"},
    {"beautiful", "pretty", "joli", "beau", "belle"},
    {"difficult", "hard", "difficile", "ardu"},
    {"easy", "simple", "facile"},
    {"immediately", "instantly", "immédiatement", "aussitôt"},
    {"child", "kid", "enfant", "gamin"},
]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def senses(text: str) -> set[str]:
    return {
        normalize(part)
        for part in re.split(r"[;,/|]", re.sub(r"\([^)]*\)", "", text))
        if normalize(part)
    }


def keywords(text: str) -> set[str]:
    words = {w for w in normalize(text).split() if w not in STOP_WORDS and len(w) > 2}
    # Plural/verb variants share a conservative key, favoring safe distant alternatives.
    words |= {w[:-1] for w in words if w.endswith("s") and len(w) > 4}
    for group in SYNONYMS:
        normalized = {normalize(w) for w in group}
        if words & normalized:
            words |= normalized
    return words


def conflicts(left: dict, right: dict) -> bool:
    if left["id"] == right["id"] or (
        left.get("surface") and left.get("surface") == right.get("surface")
    ):
        return True
    for field in ("label", "canonical"):
        a, b = left.get(field, ""), right.get(field, "")
        if a and b and (senses(a) & senses(b) or keywords(a) & keywords(b)):
            return True
    return False


def answer_shape(item: dict) -> str:
    # English dictionary infinitives remain useful when the imported POS is "other".
    if re.match(r"^to\s+", item.get("canonical", "").strip(), re.IGNORECASE):
        return "infinitive"
    if re.fullmatch(r"[\d\s.,]+", item["label"]):
        return "number"
    return "phrase"


def choose_distractors(target: dict, candidates: list[dict]) -> list[dict]:
    ranked = []
    for item in candidates:
        if item["locale"] != target["locale"] or not item["label"].strip():
            continue
        distance = abs(int(item["level"][1]) - int(target["level"][1]))
        if distance > 1 or conflicts(target, item):
            continue
        known_pos = target.get("pos") not in (None, "", "other")
        score = (
            int(known_pos and item.get("pos") != target.get("pos")),
            distance,
            int(answer_shape(item) != answer_shape(target)),
            abs(len(senses(item["label"])) - len(senses(target["label"]))),
            abs(math.log((len(item["label"]) + 1) / (len(target["label"]) + 1))),
            RNG.random(),
        )
        ranked.append((score, item))
    selected = []
    for _, item in sorted(ranked, key=lambda pair: pair[0]):
        if any(conflicts(item, previous) for previous in selected):
            continue
        selected.append(item)
        if len(selected) == 3:
            break
    return selected
