"""Deterministic recipe matching for Food Rescue (CSV edition).

Reads the Allrecipes-style CSV in ``data/sample_recipes.csv``. Every row
stores its ingredients as a Python-style list of dicts and its directions as
a Python-style list of strings, so the CSV fields are parsed with
``ast.literal_eval``.

Matching rules (from the project proposal):
  * A pantry made up only of staples is rejected with ValueError.
  * Recipes slower than ``max_time`` are excluded (hard filter).
  * Staples weigh 0.5, "use soon" ingredients weigh 1.5, everything else 1.0.
  * Score = matched weight / total recipe weight.

No randomness and no AI calls: identical inputs always produce identical
output.
"""

import ast
import csv
import os
import re
from typing import Any, Dict, Iterable, List, Optional

STAPLES = {"salt", "pepper", "water", "oil"}

STAPLE_WEIGHT = 0.5
USE_SOON_WEIGHT = 1.5
STANDARD_WEIGHT = 1.0

DEFAULT_DATA_PATH = os.path.join("data", "sample_recipes.csv")

_TIME_PART = re.compile(
    r"(\d+(?:\.\d+)?)\s*(hrs?|hours?|mins?|minutes?)", re.IGNORECASE
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Words that describe a variety or preparation of a staple, not a new food.
_STAPLE_QUALIFIERS = {
    "ground", "black", "white", "sea", "coarse", "fine", "kosher", "table",
    "olive", "vegetable", "canola", "corn", "sesame", "peanut", "cooking",
    "extra", "virgin", "light", "hot", "cold", "warm", "boiling", "lukewarm",
    "filtered", "tap", "grind",
}

# Words that describe quantity, preparation, or grammar rather than the food.
_FILLER_WORDS = {
    "a", "an", "and", "or", "to", "taste", "as", "needed", "more", "less",
    "optional", "for", "of", "with", "such", "into", "cut", "divided",
    "plus", "about", "if", "desired", "deep", "frying", "coating",
    "dredging", "packed", "prepared", "finely", "thinly", "chopped",
    "minced", "grated", "shredded", "sliced", "diced", "beaten", "melted",
    "crushed", "cracked", "peeled", "cored", "seeded", "drained", "rinsed",
    "softened", "halves", "half", "pieces", "piece", "chunks", "chunk",
    "strips", "strip", "cubes", "cube", "wedges", "wedge", "leaves", "leaf",
    "sprigs", "sprig", "stalks", "stalk", "cloves", "clove", "heads", "head",
    "cans", "can", "packages", "package", "bottles", "bottle", "jars", "jar",
    "sleeves", "sleeve", "cover", "lengthwise", "pounded", "butterflied",
}

# If a recipe ingredient is a derived product (broth, powder, sauce...), a
# plain food word such as "chicken" or "garlic" must not match it.
_DERIVED_HEADS = {
    "broth", "stock", "soup", "sauce", "dressing", "seasoning", "powder",
    "paste", "base", "gravy", "vinegar", "oil", "fat", "juice", "zest",
    "extract", "syrup",
}


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _singular(word: str) -> str:
    """Very small English plural normaliser (deterministic, no dependencies)."""
    if len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> List[str]:
    """Lowercase words used for matching, with fillers and plurals removed."""
    tokens = []
    for word in _NON_ALNUM.sub(" ", str(text).lower()).split():
        if word in _FILLER_WORDS:
            continue
        tokens.append(_singular(word))
    return tokens


def _staple_core(tokens: Iterable[str]) -> List[str]:
    """Keep only the meaningful part of a possible staple name."""
    return [token for token in tokens if token not in _STAPLE_QUALIFIERS]


def _is_staple_name(name: str) -> bool:
    """True for salt/pepper/water/oil and simple variants of them."""
    tokens = _tokens(name)
    if not tokens:
        return False
    core = _staple_core(tokens)
    return bool(core) and all(token in STAPLES for token in core)


def _matches(pantry_item: str, ingredient: str) -> bool:
    """True when a pantry term covers a recipe ingredient.

    Matching is token based, so ``chicken`` covers ``skinless, boneless
    chicken breast halves`` while ``chicken`` does not cover ``chicken broth``.
    """
    pantry_tokens = _tokens(pantry_item)
    ingredient_tokens = _tokens(ingredient)
    if not pantry_tokens or not ingredient_tokens:
        return False

    if _is_staple_name(pantry_item):
        return _is_staple_name(ingredient) and set(
            _staple_core(pantry_tokens)
        ) <= set(_staple_core(ingredient_tokens))

    # Do not let "chicken" satisfy "chicken broth", "garlic" satisfy
    # "garlic powder", and similar derived products.
    if (
        ingredient_tokens[-1] in _DERIVED_HEADS
        and pantry_tokens[-1] != ingredient_tokens[-1]
    ):
        return False

    return set(pantry_tokens) <= set(ingredient_tokens)


def _clean_all(items: Iterable[str]) -> List[str]:
    """Lowercase, collapse whitespace, and drop blanks."""
    if items is None:
        return []
    if isinstance(items, str):
        items = [items]
    cleaned = []
    for item in items:
        text = " ".join(str(item).strip().lower().split())
        if text:
            cleaned.append(text)
    return cleaned


def _unique(items: Iterable[str]) -> List[str]:
    """Preserve order while removing duplicates (Python 3.7+ dicts)."""
    return list(dict.fromkeys(items))


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _resolve_data_path(data_path: str) -> str:
    """Allow the default relative path to work from the repo root or src/."""
    if os.path.isfile(data_path):
        return data_path

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback = os.path.join(project_root, data_path)
    return fallback if os.path.isfile(fallback) else data_path


def _literal_list(raw: str) -> List[Any]:
    """Parse a CSV field that holds a Python-style list."""
    if not raw or not raw.strip():
        return []
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return []
    return value if isinstance(value, list) else []


def _parse_minutes(value: str) -> Optional[int]:
    """Turn ``1 hrs 5 mins`` into 65."""
    if value is None:
        return None

    total = 0.0
    for amount, unit in _TIME_PART.findall(str(value)):
        amount = float(amount)
        if unit.lower().startswith("h"):
            total += amount * 60
        else:
            total += amount
    return int(round(total)) if total > 0 else None


def _recipe_minutes(row: Dict[str, str]) -> Optional[int]:
    """Prefer Total Time; fall back to Prep + Cook + Additional."""
    total = _parse_minutes(row.get("Total Time"))
    if total is not None:
        return total

    parts = [
        _parse_minutes(row.get(column))
        for column in ("Prep Time", "Cook Time", "Additional Time")
    ]
    known = [part for part in parts if part is not None]
    return sum(known) if known else None


def _ingredient_names(raw: str) -> List[str]:
    """Extract just the names from the list-of-dicts Ingredients field."""
    names = []
    for entry in _literal_list(raw):
        name = entry.get("name", "") if isinstance(entry, dict) else entry
        name = " ".join(str(name).split())
        if name:
            names.append(name)
    return names


def _direction_text(raw: str) -> str:
    """Join the Directions list, dropping credits and note headers."""
    lines = []
    for entry in _literal_list(raw):
        text = " ".join(str(entry).split())
        if not text:
            continue
        # Author credits and "Editor's Note:" headers are short and have no
        # sentence punctuation; real steps do.
        if text.startswith("Photo by"):
            continue
        if len(text.split()) <= 6 and "." not in text:
            continue
        lines.append(text)
    return "\n".join(lines)


def load_recipes(data_path: str = DEFAULT_DATA_PATH) -> List[Dict]:
    """Load and normalise the recipe CSV."""
    recipes = []
    with open(
        _resolve_data_path(data_path), newline="", encoding="utf-8-sig"
    ) as handle:
        for row in csv.DictReader(handle):
            title = (row.get("Name") or "").strip()
            if not title:
                continue
            recipes.append(
                {
                    "title": title,
                    "time_minutes": _recipe_minutes(row),
                    "ingredients": _ingredient_names(row.get("Ingredients", "")),
                    "instructions": _direction_text(row.get("Directions", "")),
                }
            )
    return recipes


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _weight(ingredient: str, use_soon: Iterable[str]) -> float:
    """Weight for one recipe ingredient."""
    if any(_matches(term, ingredient) for term in use_soon):
        return USE_SOON_WEIGHT
    if _is_staple_name(ingredient):
        return STAPLE_WEIGHT
    return STANDARD_WEIGHT


def match_recipes(
    user_pantry: Iterable[str],
    use_soon: Iterable[str] = [],
    max_time: Optional[int] = None,
    data_path: str = DEFAULT_DATA_PATH,
) -> Optional[Dict]:
    """Return the single best recipe for the given pantry, or None.

    Parameters
    ----------
    user_pantry:
        Ingredients the user already has.
    use_soon:
        Perishables that should be prioritised (weight 1.5).
    max_time:
        Hard upper bound on ``time_minutes``; slower recipes are dropped.
    data_path:
        Path to the recipe CSV file.

    Raises
    ------
    ValueError
        If the pantry contains only staples (or nothing at all).

    Returns
    -------
    dict | None
        ``title``, ``score``, ``matched_ingredients``, ``missing_ingredients``,
        ``time_minutes`` and ``instructions`` for the top recipe. ``None`` if
        every recipe was filtered out by ``max_time``.
    """
    pantry = _unique(_clean_all(user_pantry))

    # Guardrail: staples alone cannot make a meal.
    if not pantry or all(_is_staple_name(item) for item in pantry):
        raise ValueError("Please provide at least one core ingredient.")

    soon = _unique(_clean_all(use_soon))
    best_recipe = None
    best_rank = None

    for recipe in load_recipes(data_path):
        time_minutes = recipe["time_minutes"]

        # Hard time filter. Recipes with an unknown time are dropped when a
        # limit is requested, so the promise to the user still holds.
        if max_time is not None:
            if time_minutes is None or time_minutes > max_time:
                continue

        ingredients = recipe["ingredients"]
        if not ingredients:
            continue

        weights = [_weight(item, soon) for item in ingredients]
        hits = [
            any(_matches(item, ingredient) for item in pantry)
            for ingredient in ingredients
        ]

        total_weight = sum(weights)
        score = sum(
            weight for weight, hit in zip(weights, hits) if hit
        ) / total_weight

        matched = _unique(
            [item for item, hit in zip(ingredients, hits) if hit]
        )
        missing = _unique(
            [item for item, hit in zip(ingredients, hits) if not hit]
        )

        candidate = {
            "title": recipe["title"],
            "score": score,
            "matched_ingredients": matched,
            "missing_ingredients": missing,
            "time_minutes": time_minutes,
            "instructions": recipe["instructions"],
        }

        # Deterministic tie-break: highest score, then recipes that use more
        # of the pantry, then title A-Z.
        rank = (-score, -len(matched), candidate["title"].lower())
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_recipe = candidate

    return best_recipe


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _print_result(label: str, result: Optional[Dict]) -> None:
    print(f"\n{label}")
    print("-" * len(label))
    if result is None:
        print("No recipe matched the constraints.")
        return

    print(f"Title:      {result['title']}")
    print(f"Score:      {result['score']:.3f}")
    print(f"Time:       {result['time_minutes']} min")
    print(f"Matched:    {', '.join(result['matched_ingredients']) or '(none)'}")
    print(f"Missing:    {', '.join(result['missing_ingredients']) or '(none)'}")
    print("Steps:")
    for step in result["instructions"].splitlines():
        print(f"  - {step}")


if __name__ == "__main__":
    pantry = [
        "chicken breast",
        "mushrooms",
        "butter",
        "olive oil",
        "flour",
        "salt",
        "black pepper",
    ]

    _print_result("Standard match", match_recipes(pantry))

    _print_result(
        "Same pantry, only 30 minutes available",
        match_recipes(pantry, max_time=30),
    )

    _print_result(
        "Mushrooms marked use-soon, 30 minute limit",
        match_recipes(
            pantry + ["mushrooms"], use_soon=["mushrooms"], max_time=30
        ),
    )

    try:
        match_recipes(["salt", "pepper", "water"])
    except ValueError as error:
        print("\nStaples-only guardrail")
        print("----------------------")
        print(f"ValueError: {error}")
