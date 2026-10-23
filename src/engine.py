"""Deterministic recipe matching for Food Rescue.

Pure standard library (json, typing). No randomness and no AI calls:
the same inputs always produce the same ranking.

Rules implemented (from the project proposal):
  * A pantry made up only of staples is rejected with ValueError.
  * Recipes slower than ``max_time`` are excluded (hard filter).
  * Staples weigh 0.5, "use soon" ingredients weigh 1.5, everything else 1.0.
  * Score = matched weight / total recipe weight.
"""

import json
import os
from typing import Dict, Iterable, List, Optional

# Ingredients that should not count as "real" cooking inputs.
STAPLES = {"salt", "pepper", "water", "oil"}

STAPLE_WEIGHT = 0.5
USE_SOON_WEIGHT = 1.5
STANDARD_WEIGHT = 1.0

DEFAULT_DATA_PATH = os.path.join("data", "sample_recipes.json")


def _normalise(ingredient: str) -> str:
    """Lowercase and collapse whitespace so matches are stable."""
    return " ".join(str(ingredient).strip().lower().split())


def _normalise_all(ingredients: Iterable[str]) -> List[str]:
    """Normalise a sequence of ingredient names, dropping blanks."""
    return [_normalise(item) for item in ingredients if str(item).strip()]


def _weight(ingredient: str, use_soon: set) -> float:
    """Weight for a single recipe ingredient.

    "Use soon" takes precedence over the staple weight, because rescuing a
    perishable is the whole point of the product.
    """
    if ingredient in use_soon:
        return USE_SOON_WEIGHT
    if ingredient in STAPLES:
        return STAPLE_WEIGHT
    return STANDARD_WEIGHT


def _resolve_data_path(data_path: str) -> str:
    """Allow the default relative path to work from the repo root or src/."""
    if os.path.isfile(data_path):
        return data_path

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback = os.path.join(project_root, data_path)
    return fallback if os.path.isfile(fallback) else data_path


def load_recipes(data_path: str = DEFAULT_DATA_PATH) -> List[Dict]:
    """Load the recipe dataset from disk."""
    with open(_resolve_data_path(data_path), "r", encoding="utf-8") as handle:
        return json.load(handle)


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
        Path to the recipe JSON file.

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
    pantry = set(_normalise_all(user_pantry))

    # Guardrail: staples alone cannot make a meal.
    if not pantry or pantry.issubset(STAPLES):
        raise ValueError("Please provide at least one core ingredient.")

    soon = set(_normalise_all(use_soon))
    recipes = load_recipes(data_path)

    best_recipe = None
    best_rank = None

    for recipe in recipes:
        time_minutes = recipe.get("time_minutes")

        # Hard time filter. Recipes with an unknown time are dropped when a
        # limit is requested, so the promise to the user still holds.
        if max_time is not None:
            if time_minutes is None or time_minutes > max_time:
                continue

        ingredients = _normalise_all(recipe.get("ingredients", []))
        if not ingredients:
            continue

        total_weight = sum(_weight(item, soon) for item in ingredients)
        matched = [item for item in ingredients if item in pantry]
        missing = [item for item in ingredients if item not in pantry]
        score = sum(_weight(item, soon) for item in matched) / total_weight

        candidate = {
            "title": recipe.get("title", ""),
            "score": score,
            "matched_ingredients": matched,
            "missing_ingredients": missing,
            "time_minutes": time_minutes,
            "instructions": recipe.get("instructions", ""),
        }

        # Deterministic tie-break: highest score first, then title A-Z.
        rank = (-score, candidate["title"].lower())
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_recipe = candidate

    return best_recipe


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
    print(f"Steps:      {result['instructions']}")


if __name__ == "__main__":
    pantry = ["eggs", "butter", "brown sugar", "flour", "bananas"]

    _print_result(
        "Standard match (bananas marked use-soon)",
        match_recipes(pantry, use_soon=["bananas"]),
    )

    _print_result(
        "Same pantry, but only 30 minutes available",
        match_recipes(pantry, use_soon=["bananas"], max_time=30),
    )

    try:
        match_recipes(["salt", "pepper", "water"])
    except ValueError as error:
        print("\nStaples-only guardrail")
        print("----------------------")
        print(f"ValueError: {error}")
