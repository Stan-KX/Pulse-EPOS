from flask import Blueprint

# Define the blueprint at the module level
auth_bp = Blueprint("auth", __name__)

# OAuth will be initialized later
oauth = None

# Import routes at the end (after auth_bp is defined)
from . import routes

def init_oauth(app):
    global oauth
    from authlib.integrations.flask_client import OAuth
    oauth = OAuth(app)
    oauth.register(
        name="microsoft",
        client_id=app.config["CLIENT_ID"],
        client_secret=app.config["CLIENT_SECRET"],
        server_metadata_url=f"https://login.microsoftonline.com/{app.config['TENANT_ID']}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )
    app.extensions = getattr(app, "extensions", {})
    app.extensions["oauth"] = oauth
