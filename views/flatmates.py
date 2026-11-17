"""Flatmates: food preferences of each person, adding and removing flatmates."""
# Draft generated with Claude (Anthropic), November 2026. Cite it if you reuse this code.
# Explanatory comments added with Claude (Anthropic), 6 November 2026.
import streamlit as st

import db
import logic

# dict: stored value -> text shown in the app
DIETS = {"any": "Eats everything", "pesce": "Pescatarian", "veg": "Vegetarian", "vegan": "Vegan"}
# must be spelled like the allergens in data/recipes.csv, because logic.blockers() compares them
ALLERGIES = ["Gluten", "Lactose", "Egg", "Nuts", "Soy", "Fish", "Shellfish", "Sesame"]
CUISINES = ["italian", "asian", "indian", "middle eastern", "mexican", "german", "mediterranean", "french",
            "american", "african"]

st.title("👥 Flatmates")
members = db.members()
# balances are needed to check whether someone may move out (see below)
expenses = db.table("SELECT payer, amount_chf, shared_by FROM expenses")
# itertuples() goes through the rows; each row e has attributes e.payer, e.amount_chf, e.shared_by
bal = logic.balances(list(members["id"]), [(e.payer, e.amount_chf, logic.ids(e.shared_by)) for e in expenses.itertuples()])

for m in members.to_dict("records"):
    with st.expander(f"**{m['name']}** · {DIETS[m['diet']]}"):
        # f"prefs-{m['id']}": each form needs its own name, one form per flatmate
        with st.form(f"prefs-{m['id']}"):
            # every widget is pre-filled with the value currently saved in the database
            name = st.text_input("Name", value=m["name"])
            diet = st.radio("Diet", list(DIETS), index=list(DIETS).index(m["diet"]), format_func=DIETS.get, horizontal=True)
            allergies = st.multiselect("Can't eat", ALLERGIES, default=[a for a in m["allergies"].split(",") if a])
            dislikes = st.text_input("Doesn't like (comma-separated)", value=m["dislikes"], placeholder="tofu, mushrooms")
            cuisines = st.multiselect("Favourite cuisines", CUISINES, default=logic.words(m["cuisines"]))
            if st.form_submit_button("Save", type="primary"):
                # lists are saved as comma-separated text (see db.py); an empty name keeps the old one
                db.run("UPDATE members SET name = ?, diet = ?, allergies = ?, dislikes = ?, cuisines = ? WHERE id = ?",
                       (name.strip() or m["name"], diet, ",".join(allergies), dislikes, ",".join(cuisines), m["id"]))
                st.rerun()
        # moving out only works once the person's balance is zero, so no debts get lost
        if abs(bal.get(m["id"], 0)) >= 0.01:
            # :+,.2f = always show the sign, thousands separator, two decimals (e.g. +1,234.50)
            st.caption(f"Can't move out yet: open balance of CHF {bal[m['id']]:+,.2f}. Settle up in Fair Split first.")
        elif st.button(f"{m['name']} moves out", key=f"out-{m['id']}"):
            db.run("DELETE FROM members WHERE id = ?", (m["id"],))
            db.run("DELETE FROM ratings WHERE member = ?", (m["id"],))  # their ratings are no longer needed
            # chores of the person go to the next flatmate in the list
            others = [i for i in members["id"] if i != m["id"]]
            if others:  # only if someone is left in the flat
                db.run("UPDATE chores SET assignee = ? WHERE assignee = ?", (logic.next_assignee(list(members["id"]), m["id"]), m["id"]))
            st.rerun()

# clear_on_submit=True empties the text field after adding, ready for the next name
with st.form("add-member", clear_on_submit=True):
    new = st.text_input("New flatmate")
    if st.form_submit_button("Add") and new.strip():  # ignore an empty name
        db.run("INSERT INTO members (name) VALUES (?)", (new.strip(),))
        st.rerun()
