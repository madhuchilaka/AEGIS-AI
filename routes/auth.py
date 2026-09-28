import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models import db, User

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["user_role"] = user.role
            session["full_name"] = user.full_name or user.username
            logger.info(f"Successful login for user '{username}' (role: {user.role})")

            flash(f"Welcome back, {session['full_name']}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.index"))
        else:
            logger.warning(f"Failed login attempt for username: '{username}'")
            flash("Invalid username or password. Please try again.", "danger")

    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    user = session.get("username")
    session.clear()
    if user:
        logger.info(f"User '{user}' logged out.")
    flash("You have been securely logged out.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        session.clear()
        session["user_id"] = user.id
        session["username"] = user.username
        session["user_role"] = user.role
        session["full_name"] = user.full_name or user.username
        logger.info(f"API Login success for user '{username}'")
        return jsonify({"status": "success", "user": user.to_dict()})

    logger.warning(f"API Login failed for user '{username}'")
    return jsonify({"status": "error", "message": "Invalid username or password"}), 401

@auth_bp.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"status": "success", "message": "Logged out successfully"})
