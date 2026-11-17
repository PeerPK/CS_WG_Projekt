"""Cooking: recipes that suit everyone at home, ranked by what the app has learned from your ratings."""
# Draft generated with Claude (Anthropic), November 2026. Cite it if you reuse this code.
# Explanatory comments and the taste-profile chart (end of file) added with Claude (Anthropic), 6 November 2026.
# Allrecipes data, load_features() and the course filter added with Claude (Anthropic), 17 November 2026.
#
# Order of work on this page:
# 1. filters (search, cuisine, time) -> 2. hard rules (diet, allergies, dislikes) remove recipes
# -> 3. the ML model ranks what is left -> 4. show the suggestions, ratings and what the model learned.
import os
from datetime import date

import altair as alt   # chart library that Streamlit uses internally; used directly for the taste-profile chart
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


# one column per person at the table, then the average per recipe (row) = expected rating of the group
table_scores = pd.concat([expected_rating(p) for p in at_table], axis=1).mean(axis=1)
fits["score"] = fits["id"].map(table_scores)  # look up the group score of every suitable recipe
fits = fits.sort_values("score", ascending=False)  # best first

learning = [p["name"] for p in at_table if models.get(p["id"]) is not None]
st.subheader(f"Suits everyone ({len(fits)})")
st.caption("Sorted by the expected rating of everyone at the table. "
           + (f"Learned from the ratings of {', '.join(learning)}." if learning
              else f"Rate at least {ml.MIN_RATINGS} dishes each and the app starts learning what you like."))

# ---------- the suggestions: one expandable box per recipe ----------
for r in fits.head(SHOW).to_dict("records"):
    with st.expander(f"**{r['name']}** · ⭐ {r['score']:.1f} · {r['minutes']} min · {r['diet']} · {r['cuisine']}"):
        if isinstance(r["allergens"], str):  # an empty CSV cell is read as NaN (a float), not as text
            st.caption("Contains: " + r["allergens"].replace(",", ", "))
        if r["id"].startswith("ar-"):  # recipes from the Allrecipes dataset have ids like 'ar-123'
            st.caption("From the Allrecipes dataset: diet, allergens and cuisine were estimated from the ingredients. "
                       "Check the ingredients if someone has an allergy.")
        a, b = st.columns([1, 1.4])
        # in the CSV, ingredients are separated by "; " and steps by " | "
        a.markdown("**Ingredients (4 servings)**\n" + "\n".join(f"- {i}" for i in r["ingredients"].split("; ")))
        b.markdown("**Method**\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(r["steps"].split(" | "), 1)))

        # every widget needs a unique key, otherwise Streamlit can't tell the buttons of different recipes apart
        if st.button("Add ingredients to shopping list", key=f"shop-{r['id']}"):
            for i in r["ingredients"].split("; "):
                db.run("INSERT INTO shopping (item) VALUES (?)", (f"{i} ({r['name']})",))
            st.toast("Added to the shopping list")  # small pop-up message

        # the rating is the training data for the ML model: each new rating changes the next suggestions
        with st.form(f"rate-{r['id']}"):
            a, b, c = st.columns([1.2, 2, 1])
            who = a.selectbox("Who rates?", [p["id"] for p in at_table], format_func=names.get)
            score = b.slider("How was it?", 1, 10, 7)  # from 1 to 10, preset to 7
            if c.form_submit_button("Save rating"):
                # INSERT OR REPLACE: rating the same dish again overwrites the old rating
                db.run("INSERT OR REPLACE INTO ratings (member, recipe, score, date) VALUES (?, ?, ?, ?)",
                       (who, r["id"], score, date.today().isoformat()))
                st.rerun()  # rerun so the models are retrained with the new rating

# recipes that passed the filters but broke a hard rule, with the reasons (~ means "not")
nofit = shown[~shown["id"].isin(fits["id"])]
if not nofit.empty:
    with st.expander(f"Not suitable today ({len(nofit)})"):
        st.dataframe(pd.DataFrame({"Recipe": nofit["name"], "Why not": nofit["id"].map(lambda rid: "; ".join(reasons[rid]))}),
                     hide_index=True)

# ---------- what the model learned (good to show in the video) ----------
st.subheader("What the app has learned")
for m in members.to_dict("records"):
    n = int((ratings["member"] == m["id"]).sum())  # True counts as 1, so sum() = number of ratings
    model = models.get(m["id"])
    if model is None:
        st.write(f"**{m['name']}**: {n} rating(s), needs {ml.MIN_RATINGS} to start learning.")
    else:
        likes, dislikes = ml.explain(model, X)
        st.write(f"**{m['name']}** ({n} ratings): likes {', '.join(likes) or '–'} · less keen on {', '.join(dislikes) or '–'}")

# ---------- taste-profile chart: the learned weights of one person's model ----------
trained = [m["id"] for m in members.to_dict("records") if models.get(m["id"]) is not None]
if trained:
    person = st.selectbox("Taste profile of", trained, format_func=names.get)
    w = ml.weights(models[person], X)
    # keep only the 12 properties with the biggest effect (positive or negative), ignore near-zero weights
    w = w[w.abs() > 0.05]
    w = w.reindex(w.abs().sort_values(ascending=False).index[:12])
    if w.empty:
        st.caption("No clear preferences yet: the ratings are too similar to each other.")
    else:
        data = pd.DataFrame({"Property": w.index, "Effect": w.values.round(2)})
        data["Direction"] = ["raises rating" if v > 0 else "lowers rating" for v in data["Effect"]]
        # Altair builds a chart from a DataFrame: x = number, y = category, colour = direction.
        # sort="-x" puts the strongest positive effect at the top and the most negative at the bottom.
        chart = alt.Chart(data).mark_bar().encode(
            x=alt.X("Effect:Q", title="Effect on predicted rating (points)"),
            y=alt.Y("Property:N", sort="-x", title=None),
            color=alt.Color("Direction:N", legend=None,
                            scale=alt.Scale(domain=["raises rating", "lowers rating"], range=["#2C8452", "#BF3F2B"])),
            tooltip=["Property", alt.Tooltip("Effect:Q", format="+.2f")],
        )
        st.altair_chart(chart)
        st.caption("Each bar is one weight of the ridge regression: how many points a property adds to (green) "
                   "or takes away from (red) the predicted rating. Cooking time counts per hour.")
