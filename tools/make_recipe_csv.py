"""Turns the big recipe database of the earlier app version (recipes.db, built from the Allrecipes dataset)
into data/allrecipes.csv.gz in the same columns as data/recipes.csv. The app itself never runs this file.

Run once:  python tools/make_recipe_csv.py path/to/recipes.db
"""

import json
import os
import re
import sqlite3
import sys

import pandas as pd

MIN_TAG_COUNT = 100  # keep only categories that at least 100 recipes share (fewer, more meaningful ML features)
# categories that say nothing about the dish itself (website labels, or the same as the course column)
NOT_TAGS = {"Allrecipes Allstar Recipes", "Chef John", "Main Dishes", "Dinner", "Lunch", "Desserts"}


# The ingredient lists in the dataset are sometimes incomplete ("Chinese Pork Dumplings" lists only the dipping sauce),
# so the earlier version labelled some meat dishes as vegan. These word lists check the title and ingredients again.
MEAT = r"\b(?:chicken|beef|pork|bacon|hams?|sausages?|turkey|lamb|veal|steaks?|prosciutto|salami|pepperoni|chorizo|duck|venison|meatballs?|meatloaf|brisket|pancetta|gelatin)\b"
FISH = r"\b(?:fish|salmon|tuna|cod|tilapia|anchov\w*|sardines?|trout|halibut)\b"
SHELLFISH = r"\b(?:shrimps?|prawns?|crabs?|lobsters?|scallops?|clams?|mussels?|oysters?|calamari|squid)\b"
MEAT_FREE = r"\b(?:vegan|vegetarian|meatless|tofu|seitan|plant-based|mock|faux)\b"  # 'Vegan Chicken Nuggets' stays vegan


def fix_diet_and_allergens(row) -> pd.Series:
    """Correct diet and allergens when the title or ingredients clearly name meat, fish or shellfish."""
    text = (row["name"] + " " + row["ingredients"]).lower()
    diet, allergens = row["diet"], [a for a in row["allergens"].split(",") if a]
    if not re.search(MEAT_FREE, row["name"].lower()):
        has_fish, has_shellfish = re.search(FISH, text), re.search(SHELLFISH, text)
        if re.search(MEAT, text):
            diet = "meat"
        elif (has_fish or has_shellfish) and diet in ("veg", "vegan"):
            diet = "pesce"
        if has_fish and "Fish" not in allergens:
            allergens.append("Fish")
        if has_shellfish and "Shellfish" not in allergens:
            allergens.append("Shellfish")
    return pd.Series({"diet": diet, "allergens": ",".join(allergens)})


def amount_text(amount) -> str:
    """0.5 -> '0.5', 2.0 -> '2', 0 -> '' (0 means 'no amount given', e.g. 'salt and pepper')."""
    if not amount:
        return ""
    return f"{round(float(amount), 2):g}"


def ingredient_text(items: list) -> str:
    """[[180, 'ml', 'ketchup'], [0, '', 'salt']] -> '180 ml ketchup; salt' (the format of recipes.csv)."""
    parts = []
    for amount, unit, name in items:
        words = [amount_text(amount), unit, name.replace(";", ",")]
        parts.append(" ".join(w for w in words if w))
    return "; ".join(parts)


db_path = sys.argv[1] if len(sys.argv) > 1 else "recipes.db"
with sqlite3.connect(db_path) as con:
    old = pd.read_sql_query("SELECT * FROM recipes", con)

old = old[old["time"].notna()]  # recipes without a cooking time can't be filtered by time: leave them out
categories = old["categories"].map(json.loads)  # JSON text -> Python list
counts = categories.explode().value_counts()
common = set(counts[counts >= MIN_TAG_COUNT].index) - NOT_TAGS

new = pd.DataFrame({
    "id": old["id"],
    "name": old["name"],
    "course": old["course"],
    "cuisine": old["cuisine"].replace("", "other"),  # most recipes have no clear cuisine
    "diet": old["diet"],
    "minutes": old["time"].astype(int),
    "allergens": old["allergens"],
    "tags": categories.map(lambda cats: ",".join(c.lower() for c in cats if c in common)),
    "ingredients": old["ingredients"].map(lambda text: ingredient_text(json.loads(text))),
    "steps": old["steps"].map(lambda text: " | ".join(s.replace("|", "/") for s in json.loads(text))),
})

before = new["diet"].copy()
new[["diet", "allergens"]] = new.apply(fix_diet_and_allergens, axis=1)  # row by row, see the function above
print(f"diet corrected for {(before != new['diet']).sum()} recipes")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "allrecipes.csv.gz")
new.to_csv(out, index=False, compression="gzip")  # gzip: about a fifth of the size, pandas reads it directly
print(f"{len(new)} recipes, {len(common)} tags -> {out}")
