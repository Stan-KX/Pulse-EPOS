from functools import wraps
from flask import session, redirect, url_for, flash, request
import os
import db

_dev = os.environ.get('FLASK_ENV', 'development') != 'production'

def login_required(func):
    if _dev:
        return func
    @wraps(func)
    def secure_function(*args, **kwargs):
        if "user" not in session:
            session['next'] = request.path
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return secure_function

def user_required(allowed_roles):
    def decorator(func):
        if _dev:
            return func
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                email = session.get("user", {}).get("email", "").lower()
                if not email:
                    flash("You must be logged in to access this page.", "danger")
                    return redirect(url_for("login"))
                role = db.query_db('SELECT role FROM staff WHERE LOWER(username) = ?', (email,), single=True)['role']
                if role not in allowed_roles:
                    flash("You do not have permission to access this page.", "danger")
                    return redirect(url_for("login"))
                return func(*args, **kwargs)
            except Exception as e:
                print(f"Error in user_required decorator: {e}")
                flash("An error occurred while checking permissions.", "danger")
                return redirect(url_for("login"))
        return wrapper
    return decorator
