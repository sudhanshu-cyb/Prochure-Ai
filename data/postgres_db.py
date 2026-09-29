import json
import uuid

import psycopg

from config import Config

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS procure_purchase_requests (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _connect():
    if not Config.DATABASE_URL:
        raise RuntimeError('DATABASE_URL is not configured.')
    return psycopg.connect(Config.DATABASE_URL, connect_timeout=5)


def load_prs():
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(TABLE_SQL)
            cursor.execute('SELECT payload FROM procure_purchase_requests ORDER BY updated_at DESC')
            return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in cursor.fetchall()]


def save_prs(prs):
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(TABLE_SQL)
            cursor.executemany(
                """
                INSERT INTO procure_purchase_requests (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                [(item['id'], json.dumps(item)) for item in prs],
            )
            cursor.execute(
                'DELETE FROM procure_purchase_requests WHERE id <> ALL(%s)',
                ([item['id'] for item in prs],),
            )


def save_vendor_search(user_id, query, location, provider, results):
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS procure_vendor_searches (id TEXT PRIMARY KEY, user_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
            cursor.execute(
                'INSERT INTO procure_vendor_searches (id, user_id, payload) VALUES (%s, %s, %s::jsonb)',
                (str(uuid.uuid4()), user_id, json.dumps({'query': query, 'location': location, 'provider': provider, 'results': results})),
            )
