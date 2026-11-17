"""Fair Split: enter expenses, see where the money goes, who owes whom, and settle up."""
# Draft generated with Claude (Anthropic), November 2026. Cite it if you reuse this code.
from datetime import date

import pandas as pd
import streamlit as st

import db
import fx
import logic

CATEGORIES = ["Groceries", "Household", "Rent & utilities", "Going out", "Travel", "Other"]
SETTLEMENT = "Settlement"  # money paid back between flatmates: not real spending

st.title("💸 Fair Split")
names = db.names()
member_ids = list(names)
expenses = db.table("SELECT * FROM expenses ORDER BY date DESC, id DESC")

# ---------- who owes whom ----------
bal = logic.balances(member_ids, [(e.payer, e.amount_chf, logic.ids(e.shared_by)) for e in expenses.itertuples()])
transfers = logic.settle(bal)
spending = expenses[expenses["category"] != SETTLEMENT]

c1, c2 = st.columns(2)
c1.metric("Spent together", f"CHF {spending['amount_chf'].sum():,.2f}", border=True)
c2.metric("Open payments", len(transfers), border=True)

# ---------- new expense ----------
n = st.session_state.setdefault("form_n", 0)  # goes up after each save: new keys = empty fields
with st.expander("➕ New expense", expanded=expenses.empty):
    title = st.text_input("What for?", placeholder="e.g. weekly shop", key=f"title-{n}")
    a, b = st.columns([2, 1])
    amount = a.number_input("Amount", min_value=0.0, step=0.5, value=None, placeholder="0.00", key=f"amount-{n}")
    currency = b.selectbox("Currency", fx.CURRENCIES)
    a, b = st.columns(2)
    category = a.selectbox("Category", CATEGORIES)
    day = b.date_input("Date", value=date.today(), max_value=date.today(), format="DD.MM.YYYY")
    rate = None
    try:
        rate = fx.rate_to_chf(currency, day.isoformat())  # the ECB rate of the expense's day
        if currency != "CHF":  # show the conversion right away, before saving
            st.success(f"1 {currency} = {rate:.4f} CHF (ECB rate for {day:%d.%m.%Y})"
                       + (f"  \n**{currency} {amount:,.2f} = CHF {amount * rate:,.2f}**" if amount else ""), icon="💱")
    except Exception:
        st.warning("Couldn't load the exchange rate right now. Try again later or enter it in CHF.")
    payer = st.selectbox("Paid by", member_ids, format_func=names.get)
    shared_by = st.multiselect("Split between", member_ids, default=member_ids, format_func=names.get)
    if st.button("Save", type="primary", disabled=rate is None):
        if not amount or not shared_by:
            st.error("Please enter an amount and choose at least one person.")
        else:
            # convert ONCE, at the rate of the expense's day, and store the CHF value
            db.run("INSERT INTO expenses (title, category, date, amount, currency, amount_chf, payer, shared_by) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (title.strip() or "Expense", category, day.isoformat(), amount, currency, round(amount * rate, 2),
                    payer, ",".join(map(str, shared_by))))
            st.session_state["form_n"] += 1
            st.rerun()

left, right = st.columns(2, gap="large")

# ---------- charts ----------
with left:
    st.subheader("Where does our money go?")
    if spending.empty:
        st.caption("No expenses yet.")
    else:
        per_month = spending.groupby(spending["date"].str[:7])["amount_chf"].sum()  # '2026-11-04' -> '2026-11'
        st.bar_chart(per_month, x_label="Month", y_label="CHF")
        totals = spending.groupby("category")["amount_chf"].sum().sort_values(ascending=False)
        st.dataframe(totals.rename("CHF").round(2))

with right:
    st.subheader("Balances")
    st.bar_chart(pd.DataFrame({"Person": [names.get(m, "Former flatmate") for m in bal],
                               "CHF": [round(v, 2) for v in bal.values()]}),
                 x="Person", y="CHF", horizontal=True)
    st.caption("Plus = gets money back, minus = owes money.")

    st.subheader("Who pays whom?")
    if not transfers:
        st.caption("All settled up. 🎉")
    for i, (frm, to, value) in enumerate(transfers):
        a, b = st.columns([3, 1])
        a.write(f"**{names.get(frm, '?')}** → **{names.get(to, '?')}**: CHF {value:,.2f}")
        if b.button("Paid", key=f"paid-{i}"):
            # booked like an expense that the debtor paid for the creditor alone: both balances move to zero
            db.run("INSERT INTO expenses (title, category, date, amount, currency, amount_chf, payer, shared_by) "
                   "VALUES (?, ?, ?, ?, 'CHF', ?, ?, ?)",
                   (f"{names[frm]} paid back {names[to]}", SETTLEMENT, date.today().isoformat(), value, value, frm, str(to)))
            st.rerun()

# ---------- list of all expenses ----------
st.subheader("All expenses")
for e in expenses.itertuples():
    a, b, c = st.columns([4, 2, 0.5])
    who = ", ".join(names.get(m, "?") for m in logic.ids(e.shared_by))
    a.write(f"**{e.title}** · {e.category} · {e.date}  \n{names.get(e.payer, '?')} paid for {who}")
    b.markdown(f"**CHF {e.amount_chf:,.2f}**")
    if e.currency != "CHF":  # paid in another currency: show what was paid and the rate used
        b.caption(f"{e.currency} {e.amount:,.2f} · 1 {e.currency} = {e.amount_chf / e.amount:.4f} CHF")
    if c.button("✕", key=f"del-{e.id}", help="Delete"):
        db.run("DELETE FROM expenses WHERE id = ?", (e.id,))
        st.rerun()
