# WG Organizer (simplified draft)

A Streamlit app for a flat share: split costs fairly, organise chores and shopping, and find dishes everyone at home can eat. It learns from your ratings what each flatmate likes.

## Run it

You need Python 3.10 or newer.

```bash
cd wg-simple
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Tests for the money and cooking rules: `python -m pytest`

## How it covers the requirements

| Requirement | Where |
|---|---|
| Data via API / database | ECB exchange rates via the Frankfurter API (`fx.py`), SQLite database (`db.py`), about 22,300 recipes (`data/recipes.csv`, `data/allrecipes.csv.gz`) |
| Visualisation | Fair Split: spending per month and category, balances per person · Cooking: taste profile per flatmate (learned model weights) |
| User interaction | Every page: forms, filters, ratings, ticking off chores and items |
| Machine learning | `ml.py`: one ridge regression per flatmate predicts ratings from cuisine, diet, tags and cooking time |

## Files

| File | Contents |
|---|---|
| `app.py` | Start page: first setup, "who's home today", navigation |
| `views/split.py` | Fair Split: expenses, charts, who pays whom |
| `views/house.py` | Cleaning rota and shopping list |
| `views/cooking.py` | Suggestions, ratings, what the model learned |
| `views/flatmates.py` | Food preferences, adding and removing flatmates |
| `logic.py` | Rules as plain functions: balances, settling up, rota, diet/allergy/dislike checks |
| `ml.py` | Machine learning |
| `fx.py` | Exchange rates |
| `db.py` | Database tables and helpers |
| `data/recipes.csv` | 45 hand-picked recipes |
| `data/allrecipes.csv.gz` | 22,247 recipes from the Allrecipes dataset (gzip-compressed CSV, same columns) |
| `tools/make_recipe_csv.py` | Built `allrecipes.csv.gz` from the earlier app's recipe database; the app doesn't run it |
| `tests/test_logic.py` | Tests for `logic.py` |

Data is stored in `wg.sqlite` next to `app.py`. There is no login.

## Recipe data

`data/allrecipes.csv.gz` comes from the Allrecipes recipe dataset (raw file `1_Recipe_csv.csv`, 62,126 rows; duplicates and
recipes without a cooking time removed). **Source:** TODO – add the exact download page of the dataset here.

The dataset has no diet, allergen, cuisine or course fields. They were estimated from titles, categories and ingredients,
and some ingredient lists in the dataset are incomplete, so these labels can be wrong. The app says so on every
Allrecipes recipe. Our 45 hand-picked recipes in `data/recipes.csv` were checked by hand.

## Use of AI

This draft was generated with Claude (Anthropic) in November 2026, based on an earlier vibe-coded version. On 6 November 2026, Claude (Anthropic) also added the explanatory comments in all files and the taste-profile chart (`ml.weights()` and the end of `views/cooking.py`). On 17 November 2026, Claude (Anthropic) added the Allrecipes recipes (`tools/make_recipe_csv.py`, `load_recipes()` in `views/cooking.py`) and the course filter. Each file is marked accordingly.
