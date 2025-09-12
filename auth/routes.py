from flask import session, redirect, url_for, current_app
from . import auth_bp  # import blueprint defined in __init__.py

@auth_bp.route("/mslogin")
def mslogin():
    print("Inside auth.mslogin")
    oauth = current_app.extensions["oauth"]
    redirect_uri = url_for("auth.auth_callback", _external=True)
    return oauth.microsoft.authorize_redirect(redirect_uri)

@auth_bp.route("/auth/callback")
def auth_callback():
    print("Inside auth.auth_callback")
    oauth = current_app.extensions["oauth"]
    token = oauth.microsoft.authorize_access_token()
    user = token.get("userinfo", {})
    session["user"] = {
        "id": user.get("sub"),
        "name": user.get("name"),
        "email": user.get("preferred_username")
    }
    print("User session:", session["user"]["email"])
    return redirect(url_for("mainpage"))

@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))
