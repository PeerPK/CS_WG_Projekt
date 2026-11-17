"""Cooking: recipes that suit everyone at home, ranked by what the app has learned from your ratings."""
# Draft generated with Claude (Anthropic), November 2026. Cite it if you reuse this code.
# Explanatory comments and the taste-profile chart (end of file) added with Claude (Anthropic), 6 November 2026.
# Allrecipes data, load_features() and the course filter added with Claude (Anthropic), 17 November 2026;
# the taste-profile chart switched from Altair to st.bar_chart the same day.
#
# Order of work on this page:
# 1. filters (search, cuisine, time) -> 2. hard rules (diet, allergies, dislikes) remove recipes
# -> 3. the ML model ranks what is left -> 4. show the suggestions, ratings and what the model learned.
import os
from datetime import date

import pandas as pd
import streamlit as st

import db
import logic
import ml

SHOW = 15  # how many suggestions to show
DATA = os.path.join(os.path.dirname(__file__), "..", "data")  # views/../data, works no matter where the app is started
COURSES = {"main": "Main dishes", "soup": "Soups & stews", "salad": "Salads", "side": "Side dishes",
           "breakfast": "Breakfast", "snack": "Snacks & starters", "dessert": "Desserts", "baking": "Bread & baking",
           "drinks": "Drinks", "other": "Other (sauces, preserves …)"}


@st.cache_data  # read the CSV files once, not on every click
def load_recipes() -> pd.DataFrame:
    """Our 45 hand-picked recipes first, then about 22,000 from the Allrecipes dataset (see README)."""
    own = pd.read_csv(os.path.join(DATA, "recipes.csv"))
    # .csv.gz = a gzip-compressed CSV (5.7 MB instead of 30 MB); pandas unpacks it by itself
    big = pd.read_csv(os.path.join(DATA, "allrecipes.csv.gz"))
    # one table with the same columns; ignore_index numbers the rows 0, 1, 2, ... again
    return pd.concat([own, big], ignore_index=True)


@st.cache_data  # turning 22,000 recipes into numbers takes a moment, so only do it once
def load_features() -> pd.DataFrame:
    return ml.features(load_recipes())


st.title("🍝 Cooking")
recipes = load_recipes()  # columns: id, name, course, cuisine, diet, minutes, allergens, tags, ingredients, steps
members = db.members()
names = dict(zip(members["id"], members["name"]))
# only the people ticked in the sidebar (app.py stores their ids in st.session_state["home"])
# to_dict("records") turns the DataFrame into a list of dicts: [{"id": 1, "name": "Oskar", ...}, ...]
at_table = members[members["id"].isin(st.session_state.get("home", []))].to_dict("records")

if not at_table:
    st.info("Nobody is home today. Pick who's eating in the sidebar.")
    st.stop()  # nothing to suggest: end the page here
st.write("**At the table today:** " + ", ".join(p["name"] for p in at_table))

# ---------- filters ----------
a, b, c, d = st.columns([2, 1, 1, 1])  # four columns side by side, the first twice as wide
query = a.text_input("Search", placeholder="e.g. pasta, curry, quick")
course = b.selectbox("Course", list(COURSES), format_func=COURSES.get)  # first entry "main" is preselected
cuisine = c.selectbox("Cuisine", ["all"] + sorted(recipes["cuisine"].unique()))
max_minutes = d.selectbox("Max. time", [0, 20, 30, 45, 60], format_func=lambda t: "any" if t == 0 else f"{t} min")

# each filter keeps only the matching rows (boolean indexing: df[condition])
shown = recipes[recipes["course"] == course]
if query:
    # search in name, ingredients and tags at once; regex=False treats the input as plain text
    text = (shown["name"] + " " + shown["ingredients"] + " " + shown["tags"].fillna("")).str.lower()
    shown = shown[text.str.contains(query.lower(), regex=False)]
if cuisine != "all":
    shown = shown[shown["cuisine"] == cuisine]
if max_minutes:  # 0 means "any", and 0 counts as False
    shown = shown[shown["minutes"] <= max_minutes]

# ---------- hard rules first: diet, allergies, dislikes ----------
# reasons = {recipe id: list of reasons why it doesn't work}; an empty list means it suits everyone
reasons = {r["id"]: logic.blockers(r, at_table) for r in shown.to_dict("records")}
fits = shown[shown["id"].map(lambda rid: not reasons[rid])].copy()  # .copy(): we add a column below

# ---------- then machine learning: predicted rating of each person, averaged over the table ----------
X = load_features()  # recipes as numbers (see ml.py)
ratings = db.table("SELECT * FROM ratings")
# one model per flatmate, trained on that person's ratings only (None if fewer than ml.MIN_RATINGS)
models = {m["id"]: ml.train(ratings[ratings["member"] == m["id"]], X) for m in members.to_dict("records")}


def expected_rating(person) -> pd.Series:
    """What this person will probably rate each recipe (1-10)."""
    model = models.get(person["id"])
    if model is not None:
        guess = ml.predict(model, X)
    else:  # not enough ratings yet: neutral, a bit higher for their favourite cuisines
        fav = logic.words(person["cuisines"])
        guess = pd.Series([ml.NEUTRAL + (1.5 if c in fav else 0) for c in recipes["cuisine"]], index=recipes["id"])
    # dishes the person already rated: use the real rating instead of a guess
    own = ratings[ratings["member"] == person["id"]].set_index("recipe")["score"]
    guess.update(own[own.index.isin(guess.index)].astype(float))  # update() overwrites matching recipe ids
    return guess


# one column per person at the table, then one score per recipe (row) for the whole group
fair = st.toggle("Everyone should like it", help="Ranks by the person who would like a dish least, "
                 "so nobody at the table gets something they don't like.")
table = pd.concat([expected_rating(p) for p in at_table], axis=1)
table_scores = table.min(axis=1) if fair else table.mean(axis=1)  # lowest score or average
fits["score"] = fits["id"].map(table_scores)  # look up the group score of every suitable recipe
fits = fits.sort_values("score", ascending=False)  # best first

# ---------- week plan: 5 good dinners, each from a different cuisine, saved for the whole flat ----------
def show_recipe(r):
    """Ingredients and method side by side (in the CSV, ingredients are separated by "; " and steps by " | ")."""
    a, b = st.columns([1, 1.4])
    a.markdown("**Ingredients (4 servings)**\n" + "\n".join(f"- {i}" for i in r["ingredients"].split("; ")))
    b.markdown("**Method**\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(r["steps"].split(" | "), 1)))


def rate_together(r, key):
    """One slider per person at the table. The ratings are the training data for the ML model."""
    with st.form(key):  # every form needs its own key, e.g. 'rate-bolo' or 'plan-bolo'
        st.markdown("**🍳 Cooked it? Everyone rates at once**")
        scores = {p["id"]: col.select_slider(p["name"], ["skip"] + list(range(1, 11)), value="skip")
                  for col, p in zip(st.columns(len(at_table)), at_table)}  # one slider per person
        if st.form_submit_button("Save ratings"):
            for who, score in scores.items():
                if score != "skip":  # INSERT OR REPLACE: rating a dish again overwrites the old rating
                    db.run("INSERT OR REPLACE INTO ratings (member, recipe, score, date) VALUES (?, ?, ?, ?)",
                           (who, r["id"], score, date.today().isoformat()))
            st.rerun()  # rerun so the models are retrained with the new ratings


def swap(pos, key):
    """Put the dish picked in the 'Change dish' drop-down on this day of the plan."""
    db.run("UPDATE plan SET recipe = ? WHERE pos = ?", (st.session_state[key], pos))
    st.session_state[key] = None  # empty the drop-down again


with st.expander("🗓️ **Our week**", expanded=True):  # own box that can be folded away
    if st.button("Plan our week", help="5 dinners that suit everyone, with some variety"):
        picked = []
        for r in fits.to_dict("records"):  # best first
            if r["cuisine"] not in [p["cuisine"] for p in picked] or r["cuisine"] == "other":
                picked.append(r)
            if len(picked) == 5:
                break
        db.run("DELETE FROM plan")  # a new plan replaces the old one
        for pos, r in enumerate(picked):
            db.run("INSERT INTO plan (pos, recipe) VALUES (?, ?)", (pos, r["id"]))
    plan = db.table("SELECT pos, recipe AS id FROM plan ORDER BY pos").merge(recipes, on="id")  # stays until the next plan
    if plan.empty:
        st.caption("No plan yet: the app picks 5 dinners that suit everyone at the table.")
    else:
        ours = ratings[ratings["member"].isin([p["id"] for p in at_table])]  # ratings of the people at the table
        rated = ours.groupby("recipe")["score"].mean()
        favs = {}  # one favourite per person at the table: their best-rated dish that suits everyone
        for p in at_table:
            mine = ours[(ours["member"] == p["id"]) & ours["recipe"].isin(fits["id"])]
            if not mine.empty:
                best = mine.loc[mine["score"].idxmax()]
                favs.setdefault(best["recipe"], []).append(f"{p['name']} ({best['score']})")
        options = list(favs) + [i for i in fits["id"] if i not in rated.index]  # favourites, then new dishes
        dish_names = {i: f"{n} · expected ⭐ {sc:.1f}" for i, n, sc in zip(fits["id"], fits["name"], fits["score"])}
        dish_names.update({i: f"❤️ {dish_names[i].split(' · ')[0]} · favourite of {', '.join(who)}" for i, who in favs.items()})
        for r in plan.to_dict("records"):
            with st.expander(f"**{['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][r['pos']]}:** {r['name']} · {r['minutes']} min · {r['cuisine']}"):
                st.selectbox("Change dish", options, index=None, placeholder="Type to search another dish …",
                             format_func=dish_names.get, key=f"swap-{r['pos']}", on_change=swap, args=(r["pos"], f"swap-{r['pos']}"))
                show_recipe(r)
                rate_together(r, f"plan-{r['pos']}")
        if st.button("Add all ingredients to the shopping list"):
            for r in plan.to_dict("records"):
                for i in r["ingredients"].split("; "):
                    db.run("INSERT INTO shopping (item) VALUES (?)", (f"{i} ({r['name']})",))
            st.toast("Added to the shopping list")

learning = [p["name"] for p in at_table if models.get(p["id"]) is not None]
st.subheader(f"Suits everyone ({len(fits)})")
st.caption("Sorted by the expected rating of everyone at the table. "
           + (f"Learned from the ratings of {', '.join(learning)}." if learning
              else f"Rate at least {ml.MIN_RATINGS} dishes each and the app starts learning what you like."))

# ---------- something new: the best dish from the cuisine you have rated least ----------
rated = recipes[recipes["id"].isin(ratings[ratings["member"].isin([p["id"] for p in at_table])]["recipe"])]
fits["seen"] = fits["cuisine"].map(rated["cuisine"].value_counts()).fillna(0)  # ratings per cuisine
new = fits[fits["cuisine"] != "other"].sort_values(["seen", "score"], ascending=[True, False]).head(1)
cards = pd.concat([new, fits.drop(new.index)]).head(SHOW + 1)  # 'something new' first, then the best ones

# ---------- the suggestions: one expandable box per recipe ----------
for r in cards.to_dict("records"):
    label = "🎲 **Something new:** " if r["id"] in new["id"].values else ""
    with st.expander(f"{label}**{r['name']}** · ⭐ {r['score']:.1f} · {r['minutes']} min · {r['diet']} · {r['cuisine']}"):
        if isinstance(r["allergens"], str):  # an empty CSV cell is read as NaN (a float), not as text
            st.caption("Contains: " + r["allergens"].replace(",", ", "))
        if r["id"].startswith("ar-"):  # recipes from the Allrecipes dataset have ids like 'ar-123'
            st.caption("From the Allrecipes dataset: diet, allergens and cuisine were estimated from the ingredients. "
                       "Check the ingredients if someone has an allergy.")
        show_recipe(r)

        # every widget needs a unique key, otherwise Streamlit can't tell the buttons of different recipes apart
        if st.button("Add ingredients to shopping list", key=f"shop-{r['id']}"):
            for i in r["ingredients"].split("; "):
                db.run("INSERT INTO shopping (item) VALUES (?)", (f"{i} ({r['name']})",))
            st.toast("Added to the shopping list")  # small pop-up message

        rate_together(r, f"rate-{r['id']}")

# recipes that passed the filters but broke a hard rule, with the reasons (~ means "not")
nofit = shown[~shown["id"].isin(fits["id"])]
if not nofit.empty:
    with st.expander(f"Not suitable today ({len(nofit)})"):
        st.dataframe(pd.DataFrame({"Recipe": nofit["name"], "Why not": nofit["id"].map(lambda rid: "; ".join(reasons[rid]))}),
                     hide_index=True)

# ---------- what the app knows about each person, in plain words ----------
st.subheader("What the app knows about your taste")
for m in members.to_dict("records"):
    n = int((ratings["member"] == m["id"]).sum())  # True counts as 1, so sum() = number of ratings
    model = models.get(m["id"])
    if model is None:
        st.write(f"⚪ **{m['name']}**: rate {ml.MIN_RATINGS - n} more dish(es) and the app starts learning.")
    else:
        likes, dislikes = ml.explain(model, X)
        status = "🟢 knows your taste" if n >= 10 else "🟡 still learning"
        st.write(f"**{m['name']}** ({status}, {n} ratings): likes {', '.join(likes) or '–'} · "
                 f"less keen on {', '.join(dislikes) or '–'}")
