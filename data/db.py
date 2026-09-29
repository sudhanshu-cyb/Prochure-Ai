import json
import os

from config import Config

DB_FILE = os.path.join(os.path.dirname(__file__), 'purchase_requests.json')

def load_prs():
    if Config.DATABASE_BACKEND == 'postgres':
        try:
            from data.postgres_db import load_prs as load_postgres_prs
            return load_postgres_prs()
        except Exception:
            pass
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_prs(prs):
    if Config.DATABASE_BACKEND == 'postgres':
        try:
            from data.postgres_db import save_prs as save_postgres_prs
            save_postgres_prs(prs)
            return
        except Exception:
            pass
    with open(DB_FILE, 'w') as f:
        json.dump(prs, f, indent=4)
