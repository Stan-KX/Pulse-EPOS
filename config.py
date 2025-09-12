import os
import secrets

class Config:
    # Flask secret key (for session signing)
    SECRET_KEY = os.getenv("SECRET_KEY") 
    SESSION_USE_SIGNER = True     # adds an HMAC signer for extra integrity
    # Cookie hardening
    SESSION_COOKIE_SECURE = True       # only over HTTPS
    SESSION_COOKIE_HTTPONLY = True     # not accessible via JS
    SESSION_COOKIE_SAMESITE = "Lax"    # or "Strict"
    # Microsoft Open Identity
    CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
    CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
    TENANT_ID = os.getenv("TENANT_ID", "common")  
    #DB
    db_name = 'eshop.db'
    DATABASE = os.path.join(os.path.dirname(__file__), f'{db_name}')
    PREFERRED_URL_SCHEME = "https"

    DEBUG = False  # turn off in production
