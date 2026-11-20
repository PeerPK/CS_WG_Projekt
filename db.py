"""Database: one SQLite file (wg.sqlite) with one table per kind of data.

Lists (who shares an expense, allergies, ...) are stored as comma-separated text, e.g. "1,3".
"""


import os                      # Werkzeug Dateien und Ordner 
import sqlite3                 # Datenbank

import pandas as pd            # Tabellenwerkzueg, pd als Abkürzung

# Where the database file lives: next to this file, unless the environment variable WG_DB says otherwise.
# os.path.abspath(__file__) = full path of db.py, dirname = its folder.
DB_PATH = os.environ.get("WG_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "wg.sqlite"))

# The structure of all tables (SQL). "IF NOT EXISTS" makes it safe to run this on every start:
# existing tables and their data are left alone. Text after -- is an SQL comment.
# INTEGER PRIMARY KEY AUTOINCREMENT = sqlite gives every new row a unique number (1, 2, 3, ...) by itself.
# """ Text merhere Zeilen 

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    diet      TEXT NOT NULL DEFAULT 'any',   -- any / pesce / veg / vegan
    allergies TEXT NOT NULL DEFAULT '',      -- e.g. 'Gluten,Nuts'
    dislikes  TEXT NOT NULL DEFAULT '',      -- e.g. 'tofu,mushrooms'
    cuisines  TEXT NOT NULL DEFAULT ''       -- favourite cuisines, e.g. 'italian,indian'
);
CREATE TABLE IF NOT EXISTS expenses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT,
    category   TEXT,
    date       TEXT,                          -- 'YYYY-MM-DD'
    amount     REAL,                          -- as typed in ...
    currency   TEXT,                          -- ... in this currency
    amount_chf REAL,                          -- converted once when saved, never again
    payer      INTEGER,                       -- member id
    shared_by  TEXT                           -- member ids, e.g. '1,2,4'
);
CREATE TABLE IF NOT EXISTS ratings (
    member INTEGER,
    recipe TEXT,
    score  INTEGER,                           -- 1 to 10
    date   TEXT,
    PRIMARY KEY (member, recipe)              -- one rating per person and dish; a new one replaces the old
);
CREATE TABLE IF NOT EXISTS chores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT,
    every_days INTEGER,
    due        TEXT,
    assignee   INTEGER
);
CREATE TABLE IF NOT EXISTS shopping (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT,
    done INTEGER DEFAULT 0                    -- 0 = still to buy, 1 = in the trolley
);
CREATE TABLE IF NOT EXISTS plan (pos INTEGER PRIMARY KEY, recipe TEXT);  -- week plan: pos 0 = Monday, recipe = id
"""

# Tabelle wird einmal geabut, wenn die APp startet
# (this code runs when another file does "import db"; Python imports a module only once per process)
_con = sqlite3.connect(DB_PATH) #connection -> öffnet wg.sqlite, gibt es sie nicht wird soe angelegt
_con.executescript(SCHEMA)  # executescript führt mehreree SQL statements gleichzeitgig aus 
_con.close()


def run(sql: str, params=()) -> None:
    """Run a statement that changes data (INSERT, UPDATE, DELETE)."""
    # Usage: run("DELETE FROM shopping WHERE id = ?", (5,)) -> each ? is filled with a value from params.
    # Never build SQL by gluing user input into the string: the ? placeholders prevent SQL injection.
    con = sqlite3.connect(DB_PATH)     # verbinden mit DB 
    con.execute(sql, params)           # Befehl ausführen
    con.commit()                       # Befehl endgültig Speichern
    con.close()                        # Verbindung trennen


def table(sql: str, params=()) -> pd.DataFrame:
    """Run a SELECT and get the result as a pandas DataFrame."""
    # A DataFrame is a table in Python: columns can be accessed like df["name"], rows filtered like
    # df[df["category"] == "Groceries"]. The views use it for charts, sums and filters.
    con = sqlite3.connect(DB_PATH)
    result = pd.read_sql_query(sql, con, params=params)     #output als komplette Tabelle
    con.close()
    return result


def members() -> pd.DataFrame:
    """All flatmates, in the order they were added (= order of the cleaning rota)."""
    return table("SELECT * FROM members ORDER BY id")


def names() -> dict:
    """{member id: name}, used everywhere to show names instead of ids."""
    m = members()
    # zip pairs the two columns element by element: (1, "Oskar"), (2, "Peer"), ... -> dict {1: "Oskar", ...}
    return dict(zip(m["id"], m["name"]))
