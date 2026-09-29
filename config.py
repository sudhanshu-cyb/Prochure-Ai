import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    APP_NAME = os.getenv('APP_NAME', 'PROCUREAI')
    APP_ENV = os.getenv('APP_ENV', 'development')
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    BACKEND_HOST = os.getenv('BACKEND_HOST', '127.0.0.1')
    BACKEND_PORT = int(os.getenv('BACKEND_PORT', '5000'))
    FRONTEND_URL = os.getenv('FRONTEND_URL', f'http://{BACKEND_HOST}:{BACKEND_PORT}')
    API_URL = os.getenv('API_URL', f'http://{BACKEND_HOST}:{BACKEND_PORT}')
    CORS_ORIGINS = [origin.strip() for origin in os.getenv('CORS_ORIGINS', FRONTEND_URL).split(',') if origin.strip()]
    DATABASE_URL = os.getenv('DATABASE_URL')
    DATABASE_BACKEND = os.getenv('DATABASE_BACKEND', 'json').lower()

    ODOO_URL = os.getenv('ODOO_URL')
    ODOO_DB = os.getenv('ODOO_DB')
    ODOO_USERNAME = os.getenv('ODOO_USERNAME')
    ODOO_PASSWORD = os.getenv('ODOO_PASSWORD')
    
    AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai').lower()
    AI_API_KEY = os.getenv('AI_API_KEY') or os.getenv('GEMINI_API_KEY')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
    LOCATION_PROVIDER = os.getenv('LOCATION_PROVIDER', 'google').lower()
    MAPPLS_CLIENT_ID = os.getenv('MAPPLS_CLIENT_ID')
    MAPPLS_CLIENT_SECRET = os.getenv('MAPPLS_CLIENT_SECRET')
    AI_ENABLED = os.getenv('AI_ENABLED', 'false').lower() == 'true'
    
    DEMO_MODE = os.getenv('DEMO_MODE', 'true').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret')
