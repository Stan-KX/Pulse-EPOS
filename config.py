import os
import secrets

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(16))
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
    CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
    TENANT_ID = os.getenv("TENANT_ID", "common")
    db_name = 'eshop.db'
    DATABASE = os.path.join(os.path.dirname(__file__), f'{db_name}')

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False   # local HTTP — cookie must not require HTTPS
    SERVER_NAME = 'localhost:5000'

class ProductionConfig(Config):
    SECRET_KEY = os.getenv("SECRET_KEY")    # no fallback — fail loudly if unset
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
