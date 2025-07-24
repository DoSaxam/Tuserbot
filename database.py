# database.py
import sqlite3

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks
                      (id INTEGER PRIMARY KEY, source TEXT, target TEXT, active INTEGER)''')
    conn.commit()
    conn.close()

def add_task(source, target):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (source, target, active) VALUES (?, ?, 1)", (source, target))
    conn.commit()
    conn.close()

def get_tasks():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks")
    return cursor.fetchall()

def toggle_task(task_id):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET active = NOT active WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def delete_task(task_id):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
