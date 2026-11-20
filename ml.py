"""Machine learning: predict how much a flatmate will like a recipe, from the dishes they rated before.

1. Every recipe becomes a row of numbers (features): one 0/1 column per cuisine, diet and tag, plus cooking time.
2. For each person, a ridge regression learns one weight per column from their ratings (1-10).
   Ridge = linear regression with a "brake": with only a few ratings it keeps the weights small
   instead of jumping to extreme conclusions (less overfitting).
3. The model then predicts a rating for every recipe the person hasn't rated yet.
"""

#
# The idea in one example: if Peer gives high ratings to Indian dishes and low ones to long oven dishes,
# the model learns a positive weight for "cuisine_indian" and a negative one for "hours".
# Predicted rating of a recipe = intercept + sum of (weight * value) over all columns.
import pandas as pd
from sklearn.linear_model import Ridge  # scikit-learn: the standard Python library for machine learning

MIN_RATINGS = 3   # fewer ratings than this: nothing sensible to learn yet
NEUTRAL = 5.5     # middle of the 1-10 scale, used when there is no model


def features(recipes: pd.DataFrame) -> pd.DataFrame:
    """One row per recipe (index = recipe id), one numeric column per property."""
    # ML models only understand numbers, so text like "italian" is turned into 0/1 columns
    # ("one-hot encoding"): cuisine_italian = 1 for Italian recipes, 0 for all others.
    X = pd.get_dummies(recipes[["cuisine", "diet"]], dtype=float)        # e.g. cuisine_italian = 1 or 0
    # tags are a comma-separated list ("pasta,classic"), so one recipe can have several tag columns = 1
    tags = recipes["tags"].fillna("").str.get_dummies(sep=",").add_prefix("tag_")  # e.g. tag_quick
    X = pd.concat([X, tags], axis=1)  # axis=1: put the tag columns next to the others
    # hours instead of minutes keeps the number in a similar range as 0/1; anything over 4 hours (bread dough,
    # marinating overnight) counts as 4, otherwise a few 100-hour recipes would dominate this column
    X["hours"] = recipes["minutes"].clip(upper=240) / 60
    X.index = recipes["id"]  # rows are found by recipe id, e.g. X.loc["bolo"]
    return X.drop(columns="tag_", errors="ignore")  # 'tag_' only means 'has no tags'


def train(ratings: pd.DataFrame, X: pd.DataFrame):
    """ratings = one person's rows with columns 'recipe' and 'score'. Returns a trained model or None."""
    ratings = ratings[ratings["recipe"].isin(X.index)]  # ignore ratings of recipes that no longer exist
    if len(ratings) < MIN_RATINGS:
        return None  # too little data: the caller falls back to a simple rule (see cooking.py)
    # alpha = strength of the "brake" (regularisation). Higher alpha = smaller, more careful weights.
    model = Ridge(alpha=1.0)
    # fit = training: input = feature rows of the rated recipes, target = the person's scores
    model.fit(X.loc[ratings["recipe"]], ratings["score"])
    return model


def predict(model, X: pd.DataFrame) -> pd.Series:
    """Predicted rating (1-10) for every recipe in X."""
    # a linear model can predict e.g. 11.3 or -0.5, so clip() cuts the result to the 1-10 scale
    return pd.Series(model.predict(X), index=X.index).clip(1, 10)


def weights(model, X: pd.DataFrame) -> pd.Series:
    """The learned weight of every property, with readable names, e.g. 'cuisine: indian' -> +1.2.
    Positive = makes this person's predicted rating higher, negative = lower. Used for the chart in cooking.py."""
    # model.coef_ holds one number per column of X, in the same order as X.columns
    label = lambda col: (col.replace("cuisine_", "cuisine: ").replace("diet_", "diet: ").replace("tag_", "tag: ")
                         .replace("hours", "cooking time (per hour)"))
    return pd.Series(model.coef_, index=[label(c) for c in X.columns]).sort_values()


def explain(model, X: pd.DataFrame, k: int = 3) -> tuple[list, list]:
    """The k properties that raise / lower this person's predicted rating the most."""
    # sort_values(): smallest (most negative) weight first, largest last
    weights = pd.Series(model.coef_, index=X.columns).sort_values()
    # weights[::-1] = reversed order, so the largest weights come first; only clear effects (> 0.1) count
    likes = [friendly(c) for c, w in weights[::-1].items() if w > 0.1][:k]
    dislikes = [friendly(c) for c, w in weights.items() if w < -0.1][:k]
    return likes, dislikes


DIETS = {"meat": "dishes with meat", "pesce": "fish dishes", "veg": "vegetarian dishes", "vegan": "vegan dishes"}
TAGS = {"quick": "quick dishes", "cheap": "cheap dishes", "comfort": "comfort food", "oven": "oven dishes",
        "sharing": "dishes to share", "spicy": "spicy food", "classic": "classic dishes", "one pot": "one-pot dishes",
        "wok": "wok dishes", "mild": "mild dishes"}


def friendly(col: str) -> str:
    """Column name -> words a flatmate understands: 'cuisine_indian' -> 'Indian food', 'tag_quick' -> 'quick dishes'."""
    if col.startswith("cuisine_"):
        return "dishes from other cuisines" if col == "cuisine_other" else col[8:].title() + " food"
    if col.startswith("diet_"):
        return DIETS[col[5:]]
    if col == "hours":
        return "dishes that take longer"
    return TAGS.get(col[4:], col[4:])  # other tags are already words, e.g. 'pasta', 'curry'
