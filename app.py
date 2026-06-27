import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import tourdb
import userdb
from user import User


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "turkish_delight.db"
LANGUAGES = ["English", "Italian", "Spanish", "Portuguese", "German"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-this-secret"),
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    UPLOAD_FOLDER=str(BASE_DIR / "static" / "reports"),
)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@login_manager.user_loader
def load_user(user_id):
    return userdb.get_user(get_db(), user_id)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(24)
    return session["csrf_token"]


app.jinja_env.globals.update(csrf_token=csrf_token, weekdays=WEEKDAYS)


@app.before_request
def verify_csrf():
    if request.method == "POST" and request.form.get("csrf_token") != session.get("csrf_token"):
        abort(400, "Invalid or missing form token.")


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def tour_images(tour_id):
    files = sorted((BASE_DIR / "static").glob(f"Tour{tour_id}_*"))
    return [f.name for f in files if f.is_file()]


def tour_from_row(row):
    tour = dict(row)
    tour["foods"] = json.loads(tour["foods"])
    tour["stops"] = json.loads(tour["stops"])
    tour["story_points"] = json.loads(tour["story_points"])
    tour["images"] = tour_images(tour["id"])
    preferred_guide = BASE_DIR / "static" / f"Guide{tour['id']}.jpg"
    tour["guide_image"] = preferred_guide.name if preferred_guide.exists() else "Guide1.jpg"
    return tour


def next_occurrences(tour_id, limit=10):
    schedule_rows = tourdb.schedules_for_tour(get_db(), tour_id)
    schedule = {row["weekday"]: row["start_time"] for row in schedule_rows}
    results = []
    day = date.today()
    for offset in range(91):
        candidate = day + timedelta(days=offset)
        if candidate.weekday() in schedule:
            start = schedule[candidate.weekday()]
            start_dt = datetime.combine(candidate, datetime.strptime(start, "%H:%M").time())
            if start_dt > datetime.now():
                booked = tourdb.booked_places(get_db(), tour_id, candidate.isoformat())
                results.append({"date": candidate.isoformat(), "label": candidate.strftime("%a, %d %b"),
                                "time": start, "booked": booked or 0})
                if len(results) >= limit:
                    break
    return results


@app.route("/")
def home():
    language = request.args.get("language", "")
    duration = request.args.get("duration", "")
    requested_date = request.args.get("date", "")
    selected_language = language if language in LANGUAGES else ""
    max_duration = int(duration) if duration in {"120", "180", "240"} else None
    weekday = None
    if requested_date:
        try:
            weekday = date.fromisoformat(requested_date).weekday()
        except ValueError:
            flash("Please choose a valid date.", "error")
    rows = tourdb.list_tours(get_db(), selected_language, max_duration, weekday)
    tours = [tour_from_row(row) for row in rows]
    return render_template("home.html", tours=tours, languages=LANGUAGES,
                           today=date.today().isoformat())


@app.route("/tours")
def tours():
    return redirect(url_for("home", **request.args) + "#tours")


@app.route("/guides")
def guides():
    rows = userdb.list_guides(get_db(), public_order=True)
    guide_list = []
    for row in rows:
        guide = User(row)
        guide_tours = tourdb.tours_for_guide(get_db(), guide.id, summary=True)
        image = "Logo.png"
        for tour in guide_tours:
            candidate = BASE_DIR / "static" / f"Guide{tour['id']}.jpg"
            if candidate.exists():
                image = candidate.name
                break
        guide_list.append({"user": guide, "tours": guide_tours, "image": image})
    return render_template("guides.html", guides=guide_list)


@app.route("/guides/<int:guide_id>")
def guide_detail(guide_id):
    guide = userdb.get_guide(get_db(), guide_id)
    if not guide:
        abort(404)
    tour_rows = tourdb.tours_for_guide(get_db(), guide_id)
    guide_tours = [tour_from_row(tour) for tour in tour_rows]
    image = "Homepage.jpg"
    for tour in guide_tours:
        candidate = BASE_DIR / "static" / f"Guide{tour['id']}.jpg"
        if candidate.exists():
            image = candidate.name
            break
    return render_template("guide_detail.html", guide=guide, tours=guide_tours, image=image)


@app.route("/tour/<int:tour_id>")
def tour_detail(tour_id):
    row = tourdb.get_tour_with_guide(get_db(), tour_id)
    if not row:
        abort(404)
    schedules = tourdb.schedules_for_tour(get_db(), tour_id)
    return render_template("tour_detail.html", tour=tour_from_row(row), schedules=schedules,
                           occurrences=next_occurrences(tour_id))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("profile"))
    if request.method == "POST":
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        languages = [x for x in request.form.getlist("languages") if x in LANGUAGES] if role == "guide" else []
        errors = []
        if not first or not last: errors.append("First and last name are required.")
        if "@" not in email: errors.append("Enter a valid email address.")
        if len(password) < 8: errors.append("Password must be at least 8 characters.")
        if role not in {"guide", "participant"}: errors.append("Choose an account type.")
        if role == "guide" and not languages: errors.append("Guides must choose at least one language.")
        if userdb.email_exists(get_db(), email):
            errors.append("An account with that email already exists.")
        if errors:
            for error in errors: flash(error, "error")
        else:
            user_id = userdb.create_user(get_db(), first, last, email, password, role, languages)
            login_user(load_user(user_id))
            flash("Welcome to Turkish Delight!", "success")
            return redirect(url_for("profile"))
    return render_template("register.html", languages=LANGUAGES)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("profile"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        row = userdb.get_user_by_email(get_db(), email)
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            login_user(User(row), remember=bool(request.form.get("remember")))
            return redirect(request.args.get("next") or url_for("profile"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("home"))


@app.route("/profile")
@login_required
def profile():
    db = get_db()
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "participant":
        reservations = tourdb.participant_reservations(db, current_user.id)
        enriched = []
        for reservation in reservations:
            item = dict(reservation)
            item["guests"] = tourdb.reservation_guests(db, item["id"])
            schedule = tourdb.schedule_for_day(
                db, item["tour_id"], date.fromisoformat(item["tour_date"]).weekday()
            )
            start = item["start_time"] or schedule["start_time"]
            item["start_time"] = start
            start_dt = datetime.combine(date.fromisoformat(item["tour_date"]), datetime.strptime(start, "%H:%M").time())
            item["can_cancel"] = start_dt - datetime.now() >= timedelta(hours=24)
            enriched.append(item)
        return render_template("participant_profile.html", reservations=enriched)
    tours = tourdb.tours_for_guide(db, current_user.id)
    summaries = []
    for row in tours:
        item = tour_from_row(row)
        item["reservation_count"] = tourdb.reservation_count(db, row["id"])
        item["dates"] = tourdb.guide_tour_dates(db, row["id"])
        item["bookings"] = tourdb.guide_tour_bookings(db, row["id"])
        summaries.append(item)
    return render_template("guide_profile.html", tours=summaries)


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    db = get_db()
    statistics = {
        "guides": userdb.count_role(db, "guide"),
        "participants": userdb.count_role(db, "participant"),
        "tours": tourdb.tour_count(db),
        "reservations": tourdb.reservation_count(db),
    }
    reservations_by_language = tourdb.reservations_by_language(db)
    guide_rows = userdb.list_guides(db)
    guides = []
    for guide_row in guide_rows:
        guide = User(guide_row)
        tour_rows = tourdb.tours_for_guide(db, guide.id)
        detailed_tours = []
        for tour_row in tour_rows:
            tour = tour_from_row(tour_row)
            tour["schedules"] = tourdb.schedules_for_tour(db, tour["id"])
            tour["reservation_count"] = tourdb.reservation_count(db, tour["id"])
            detailed_tours.append(tour)
        guides.append({"user": guide, "tours": detailed_tours})
    return render_template(
        "admin_dashboard.html", statistics=statistics,
        reservations_by_language=reservations_by_language, guides=guides,
    )


@app.route("/tour/<int:tour_id>/book", methods=["POST"])
@role_required("participant")
def book_tour(tour_id):
    db = get_db()
    tour = tourdb.get_tour(db, tour_id)
    if not tour: abort(404)
    try:
        tour_date = date.fromisoformat(request.form.get("tour_date", ""))
    except ValueError:
        flash("Choose a valid tour date.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    schedule = tourdb.schedule_for_day(db, tour_id, tour_date.weekday())
    if not schedule:
        flash("This tour is not offered on that day.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    start_dt = datetime.combine(tour_date, datetime.strptime(schedule["start_time"], "%H:%M").time())
    if start_dt <= datetime.now():
        flash("Please choose a future occurrence.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    guests = [name.strip() for name in request.form.getlist("guest_names") if name.strip()]
    if len(guests) > 3 or any(len(name.split()) < 2 for name in guests):
        flash("Add up to three guests, each with a first and last name.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    booked = tourdb.booked_places(db, tour_id, tour_date.isoformat())
    if booked + 1 + len(guests) > tour["capacity"]:
        flash("There are not enough places left for this group.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    if tourdb.reservation_exists(db, current_user.id, tour_id, tour_date.isoformat()):
        flash("You already have a reservation for this tour date.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    existing = tourdb.overlapping_reservations(
        db, current_user.id, tour_date.isoformat(), tour_date.weekday()
    )
    new_end = start_dt + timedelta(minutes=tour["duration"])
    for other in existing:
        other_start = datetime.combine(tour_date, datetime.strptime(other["start_time"], "%H:%M").time())
        if start_dt < other_start + timedelta(minutes=other["duration"]) and other_start < new_end:
            flash("This tour overlaps another reservation in your schedule.", "error")
            return redirect(url_for("tour_detail", tour_id=tour_id))
    tourdb.create_reservation(
        db, current_user.id, tour_id, tour_date.isoformat(), guests,
        datetime.now().isoformat(timespec="seconds"),
    )
    flash("Your place is reserved. See you in İzmir!", "success")
    return redirect(url_for("profile"))


@app.route("/reservation/<int:reservation_id>/cancel", methods=["POST"])
@role_required("participant")
def cancel_reservation(reservation_id):
    db = get_db()
    reservation = tourdb.get_participant_reservation(db, reservation_id, current_user.id)
    if not reservation: abort(404)
    tour_day = date.fromisoformat(reservation["tour_date"])
    schedule = tourdb.schedule_for_day(db, reservation["tour_id"], tour_day.weekday())
    start_dt = datetime.combine(tour_day, datetime.strptime(schedule["start_time"], "%H:%M").time())
    if start_dt - datetime.now() < timedelta(hours=24):
        flash("Reservations can only be cancelled at least 24 hours before the tour.", "error")
    else:
        tourdb.cancel_reservation(db, reservation_id)
        flash("Your reservation has been cancelled.", "success")
    return redirect(url_for("profile"))


def parse_tour_form(existing=None):
    data = {
        "title": request.form.get("title", "").strip(), "subtitle": request.form.get("subtitle", "").strip(),
        "description": request.form.get("description", "").strip(), "story": "", "final_message": "",
        "meeting_point": request.form.get("meeting_point", "").strip(), "language": request.form.get("language", ""),
        "foods": [x.strip() for x in request.form.get("foods", "").split(",") if x.strip()],
        "stops": [x.strip() for x in request.form.get("stops", "").splitlines() if x.strip()],
        "story_points": [x.strip() for x in request.form.get("story_points", "").splitlines() if x.strip()],
    }
    errors = []
    try: data["duration"] = int(request.form.get("duration", ""))
    except ValueError: errors.append("Duration must be a number.")
    try: data["capacity"] = int(request.form.get("capacity", ""))
    except ValueError: errors.append("Capacity must be a number.")
    if any(not data[k] for k in ["title", "subtitle", "description", "meeting_point"]): errors.append("Complete all required text fields.")
    if len(data["stops"]) < 4: errors.append("Add at least four stops, one per line.")
    if data["language"] not in current_user.languages: errors.append("Choose a language that you speak.")
    schedules = []
    for day in range(7):
        value = request.form.get(f"day_{day}")
        if value: schedules.append((day, value))
    if not schedules: errors.append("Choose at least one weekly start time.")
    return data, schedules, errors


@app.route("/guide/tour/new", methods=["GET", "POST"])
@role_required("guide")
def new_tour():
    if request.method == "POST":
        data, schedules, errors = parse_tour_form()
        photos = [photo for photo in request.files.getlist("photos") if photo.filename]
        allowed = {".jpg", ".jpeg", ".png", ".webp"}
        if len(photos) != 5 or any(Path(photo.filename).suffix.lower() not in allowed for photo in photos):
            errors.append("Upload exactly five promotional photos (JPG, PNG, or WebP).")
        if errors:
            for error in errors: flash(error, "error")
        else:
            db = get_db()
            tour_id = tourdb.create_tour(db, current_user.id, data, schedules)
            for number, photo in enumerate(photos, 1):
                suffix = Path(photo.filename).suffix.lower()
                photo.save(BASE_DIR / "static" / f"Tour{tour_id}_{number}{suffix}")
            flash("Tour created.", "success")
            return redirect(url_for("profile"))
    return render_template("tour_form.html", tour=None, languages=current_user.languages, schedule={})


@app.route("/guide/tour/<int:tour_id>/edit", methods=["GET", "POST"])
@role_required("guide")
def edit_tour(tour_id):
    db = get_db()
    row = tourdb.get_tour(db, tour_id, current_user.id)
    if not row: abort(404)
    has_reservations = tourdb.has_tour_reservations(db, tour_id)
    if request.method == "POST":
        data, schedules, errors = parse_tour_form(row)
        if errors:
            for error in errors: flash(error, "error")
        else:
            if has_reservations:
                tourdb.update_tour(db, tour_id, data, essential=False)
            else:
                tourdb.update_tour(db, tour_id, data, schedules, essential=True)
            flash("Tour updated.", "success")
            return redirect(url_for("profile"))
    schedule = tourdb.schedule_map(db, tour_id)
    return render_template("tour_form.html", tour=tour_from_row(row), languages=current_user.languages,
                           schedule=schedule, locked=has_reservations)


@app.route("/guide/report/<int:tour_id>", methods=["POST"])
@role_required("guide")
def submit_report(tour_id):
    db = get_db()
    tour = tourdb.get_tour(db, tour_id, current_user.id)
    if not tour: abort(404)
    tour_date = request.form.get("tour_date", "")
    if not tourdb.date_has_reservations(db, tour_id, tour_date):
        flash("Only dates with reservations can be reported.", "error")
        return redirect(url_for("profile"))
    try:
        attended = int(request.form.get("attended", ""))
        if attended < 0: raise ValueError
        day = date.fromisoformat(tour_date)
    except ValueError:
        flash("Enter a valid date and attendance count.", "error")
        return redirect(url_for("profile"))
    if day >= date.today():
        flash("A report can only be submitted after the tour date.", "error")
        return redirect(url_for("profile"))
    photo = request.files.get("evidence")
    if not photo or Path(photo.filename).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        flash("Upload a JPG, PNG, or WebP evidence photo.", "error")
        return redirect(url_for("profile"))
    filename = secure_filename(f"tour-{tour_id}-{tour_date}-{photo.filename}")
    photo.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
    tourdb.save_report(db, tour_id, tour_date, attended, filename)
    flash("Post-tour report saved.", "success")
    return redirect(url_for("profile"))


@app.errorhandler(404)
def not_found(_error): return render_template("error.html", code=404, message="That page wandered off the route."), 404


@app.errorhandler(403)
def forbidden(_error): return render_template("error.html", code=403, message="This path is reserved for another account type."), 403


def init_db():
    db = get_db()
    db.executescript((BASE_DIR / "schema.sql").read_text())
    userdb.prepare_user_schema(db)
    if not userdb.has_users(db):
        user_ids = userdb.seed_sample_users(db)
        tourdb.seed_sample_tours(db, user_ids, date.today(), datetime.now())
    userdb.ensure_admin_account(db)
    userdb.migrate_sample_password_hashes(db)


with app.app_context():
    init_db()


if __name__ == "__main__":
    # Port 5000 is commonly occupied by AirPlay Receiver on macOS.
    app.run(debug=True, port=8000)
