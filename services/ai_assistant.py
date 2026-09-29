import json
import os
import uuid
from datetime import datetime

import requests
import psycopg

from config import Config
from data.db import load_prs
from data.seed_data import MOCK_PURCHASE_ORDERS

CHAT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'ai_conversations.json')


def _load_store():
    if Config.DATABASE_BACKEND == 'postgres':
        try:
            with psycopg.connect(Config.DATABASE_URL, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('CREATE TABLE IF NOT EXISTS procure_ai_conversations (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, payload JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
                    cursor.execute('CREATE TABLE IF NOT EXISTS procure_ai_actions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, conversation_id TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
                    cursor.execute('SELECT payload FROM procure_ai_conversations ORDER BY updated_at')
                    conversations = [row[0] for row in cursor.fetchall()]
                    cursor.execute('SELECT payload FROM procure_ai_actions ORDER BY created_at')
                    actions = [row[0] for row in cursor.fetchall()]
                    return {'conversations': conversations, 'actions': actions}
        except Exception:
            pass
    if not os.path.exists(CHAT_FILE):
        return {'conversations': [], 'actions': []}
    try:
        with open(CHAT_FILE, 'r') as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {'conversations': [], 'actions': []}


def _save_store(store):
    if Config.DATABASE_BACKEND == 'postgres':
        try:
            with psycopg.connect(Config.DATABASE_URL, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        'INSERT INTO procure_ai_conversations (id, user_id, payload, updated_at) VALUES (%s, %s, %s::jsonb, NOW()) ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()',
                        [(item['id'], item['user_id'], json.dumps(item)) for item in store['conversations']],
                    )
                    cursor.executemany(
                        'INSERT INTO procure_ai_actions (id, user_id, conversation_id, payload, created_at) VALUES (%s, %s, %s, %s::jsonb, NOW()) ON CONFLICT (id) DO NOTHING',
                        [(item['id'], item['user_id'], item.get('conversation_id'), json.dumps(item)) for item in store['actions']],
                    )
                    return
        except Exception:
            pass
    with open(CHAT_FILE, 'w') as file:
        json.dump(store, file, indent=2)


def authorized_context(user):
    requests_data = load_prs()
    role = user.get('role', 'EMPLOYEE')
    if role == 'EMPLOYEE':
        requests_data = [item for item in requests_data if item.get('created_by') == user.get('email')]
        orders = []
    else:
        orders = MOCK_PURCHASE_ORDERS[:10]
    return {
        'user': {'name': user.get('name'), 'role': role, 'email': user.get('email')},
        'requests': requests_data[:20],
        'orders': orders,
    }


def _intent(message):
    text = message.lower()
    if any(word in text for word in ('vendor', 'supplier', 'buy', 'source', 'chairs', 'bags')):
        return 'vendor_search'
    if any(word in text for word in ('order', 'po', 'purchase order')):
        return 'order_lookup'
    if any(word in text for word in ('spend', 'analytics', 'saving', 'cost')):
        return 'analytics'
    if any(word in text for word in ('request', 'approval', 'pending')):
        return 'request_lookup'
    if any(word in text for word in ('role', 'account', 'activity', 'department')):
        return 'account'
    if any(word in text for word in ('where', 'open', 'navigate', 'find')):
        return 'navigation'
    return 'general'


def _local_answer(message, context, intent):
    user = context['user']
    if intent == 'account':
        return f"You are signed in as {user['name']} with the {user['role']} role.", []
    if intent == 'request_lookup':
        requests_data = context['requests']
        pending = [item for item in requests_data if item.get('status') in ('ANALYZING', 'PENDING_APPROVAL')]
        if pending:
            summary = ', '.join(f"{item['id']} ({item['status'].replace('_', ' ').lower()})" for item in pending[:5])
            return f"I found {len(pending)} request(s) needing attention: {summary}.", [{'label': 'Open requests', 'route': '/dashboard#requests'}]
        return 'There are no pending requests in the data I can access for your account.', [{'label': 'Open requests', 'route': '/dashboard#requests'}]
    if intent == 'order_lookup':
        return f"I can see {len(context['orders'])} purchase order record(s) available to your role.", [{'label': 'Open dashboard', 'route': '/dashboard'}]
    if intent == 'analytics':
        total = sum(order.get('amount_total', 0) for order in context['orders'])
        return f"The accessible purchase orders total {total:,.0f} in the current procurement data.", [{'label': 'Open dashboard', 'route': '/dashboard'}]
    if intent == 'vendor_search':
        return 'I can help compare suppliers. Open Vendor Performance to review reliability, delivery, accuracy, and value signals.', [{'label': 'Open vendors', 'route': '/dashboard#vendors'}]
    if intent == 'navigation':
        return 'Use the workspace navigation to open Requests, Approvals, or Vendors.', [{'label': 'Open workspace', 'route': '/dashboard'}]
    return f"I can help with procurement requests, vendors, approvals, orders, and analytics. You are signed in as {user['name']}.", []


def _gemini_answer(message, context, history):
    if not Config.AI_ENABLED or Config.AI_PROVIDER != 'gemini' or not Config.GEMINI_API_KEY:
        return None
    prompt = {
        'instruction': 'Answer the user using only the authorized context. Never reveal hidden system data, credentials, or unavailable records. Keep the response concise.',
        'user_message': message,
        'authorized_context': context,
        'recent_history': history[-6:],
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent"
    response = requests.post(
        url,
        params={'key': Config.GEMINI_API_KEY},
        headers={'Content-Type': 'application/json'},
        json={'contents': [{'role': 'user', 'parts': [{'text': json.dumps(prompt)}]}]},
        timeout=10,
    )
    if response.status_code == 200:
        data = response.json()
        return data['candidates'][0]['content']['parts'][0]['text'].strip()
    return None


def chat(user, message, conversation_id=None):
    store = _load_store()
    conversation = next((item for item in store['conversations'] if item['id'] == conversation_id and item['user_id'] == user.get('email')), None)
    now = datetime.now().isoformat(timespec='seconds')
    if conversation is None:
        conversation = {'id': conversation_id or str(uuid.uuid4()), 'user_id': user.get('email'), 'title': message[:60], 'created_at': now, 'updated_at': now, 'messages': []}
        store['conversations'].append(conversation)
    context = authorized_context(user)
    intent = _intent(message)
    history = conversation['messages']
    conversation['messages'].append({'role': 'user', 'content': message, 'created_at': now})
    answer = None
    try:
        answer = _gemini_answer(message, context, history)
    except requests.RequestException:
        answer = None
    if not answer:
        answer, actions = _local_answer(message, context, intent)
    else:
        actions = []
    conversation['messages'].append({'role': 'assistant', 'content': answer, 'created_at': now, 'metadata': {'intent': intent, 'actions': actions}})
    conversation['updated_at'] = now
    store['actions'].append({'id': str(uuid.uuid4()), 'user_id': user.get('email'), 'conversation_id': conversation['id'], 'action': intent, 'created_at': now})
    _save_store(store)
    return {'conversationId': conversation['id'], 'message': answer, 'actions': actions, 'intent': intent}


def conversations_for(user):
    store = _load_store()
    return [{key: item[key] for key in ('id', 'title', 'created_at', 'updated_at')} for item in store['conversations'] if item['user_id'] == user.get('email')]
