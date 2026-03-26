import sqlite3

con = sqlite3.connect("database.db")
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
   aadhaar TEXT UNIQUE CHECK (
        length(aadhaar) = 12
        AND aadhaar GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
    ),
    candidate TEXT,
    time TEXT
)
""")

con.commit()
con.close()

print("✅ Database created successfully")


