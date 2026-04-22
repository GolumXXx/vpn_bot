import sqlite3

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

# Ставим старую дату (чтобы trial считался законченным)
cursor.execute("""
UPDATE users
SET trial_activated_at = '2026-04-18 10:00:00'
WHERE telegram_id = 7066754428
""")

conn.commit()
conn.close()

print("Trial сдвинут назад ✅")