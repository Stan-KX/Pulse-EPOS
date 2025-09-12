import sqlite3
from flask import g, current_app

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(error=None):
    db_conn = g.pop('db', None)
    if db_conn is not None:
        db_conn.close()

def query_db(query, args=(), single=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if single else rv

# True if single row insert, False if multiple inserts
def insert_db(query, args=(), single=False):  
    db_conn = get_db()
    cur = db_conn.cursor()
    try:
        if single:
            cur.execute(query, args)
        else:
            cur.executemany(query, args)
        db_conn.commit()
    except sqlite3.Error as e:
        db_conn.rollback()
        print(f"DB Error: {e}")
        raise
    finally:
        cur.close()
