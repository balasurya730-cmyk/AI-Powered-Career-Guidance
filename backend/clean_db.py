import sqlite3
import os

DATABASE = os.path.join(os.path.dirname(__file__), "learning_planner.db")
conn = sqlite3.connect(DATABASE)
cur = conn.cursor()
cur.execute("DELETE FROM learning_plans WHERE daily_plan LIKE '%item 1%'")
print(f"Deleted {cur.rowcount} bad plans")
conn.commit()
conn.close()
