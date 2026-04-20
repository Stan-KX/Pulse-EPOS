# auth/decorators.py
from functools import wraps
from flask import session, redirect, url_for, flash, request
import db

# def login_required(func):
#     @wraps(func)
#     def secure_function(*args, **kwargs):
#         if "user" not in session:
#             session['next'] = request.path
#             return redirect(url_for("login"))
#         return func(*args, **kwargs)
#     return secure_function

# def user_required(allowed_roles):
#     def decorator(func):
#         @wraps(func)
#         def wrapper(*args, **kwargs):
#             try:
#                 email = session["user"]["email"].lower()
#                 print(f"Checking user: {email} for allowed roles: {allowed_roles}")
#                 if email:
#                     role= db.query_db('SELECT role FROM staff WHERE LOWER(username) = ?', (email,), single=True)['role']
#                     print(f"user {email} has role {role}")
#                     if role not in allowed_roles:
#                         print(f"Access denied for user: {session['user']['email']} with role: {role}")
#                         flash("You do not have permission to access this page.", "danger")
#                         return redirect(url_for("login"))
#                 else:
#                     print("No user in session, redirecting to login.")
#                     flash("You must be logged in to access this page.", "danger")
#                     return redirect(url_for("login"))
#                 return func(*args, **kwargs)
#             except Exception as e:
#                 print(f"Error in user_required decorator: {e}")
#                 flash("An error occurred while checking permissions.", "danger")
#                 return redirect(url_for("login"))
#         return wrapper
#     return decorator

def login_required(func):
    @wraps(func)
    def secure_function(*args, **kwargs):
        # DUMMY: Bypass login for development
        return func(*args, **kwargs)
    return secure_function

def user_required(allowed_roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # DUMMY: Bypass role check for development
            return func(*args, **kwargs)
        return wrapper
    return decorator