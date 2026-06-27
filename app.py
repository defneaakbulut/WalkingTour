import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


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


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.first_name = row["first_name"]
        self.last_name = row["last_name"]
        self.email = row["email"]
        self.role = row["role"]
        self.languages = json.loads(row["languages"] or "[]")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


@login_manager.user_loader
def load_user(user_id):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


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
    schedule_rows = get_db().execute(
        "SELECT weekday, start_time FROM schedules WHERE tour_id = ? ORDER BY weekday", (tour_id,)
    ).fetchall()
    schedule = {row["weekday"]: row["start_time"] for row in schedule_rows}
    results = []
    day = date.today()
    for offset in range(91):
        candidate = day + timedelta(days=offset)
        if candidate.weekday() in schedule:
            start = schedule[candidate.weekday()]
            start_dt = datetime.combine(candidate, datetime.strptime(start, "%H:%M").time())
            if start_dt > datetime.now():
                booked = get_db().execute(
                    """SELECT COUNT(*) + COALESCE(SUM((SELECT COUNT(*) FROM reservation_guests rg
                       WHERE rg.reservation_id = r.id)), 0) AS total
                       FROM reservations r WHERE tour_id = ? AND tour_date = ?""",
                    (tour_id, candidate.isoformat()),
                ).fetchone()["total"]
                results.append({"date": candidate.isoformat(), "label": candidate.strftime("%a, %d %b"),
                                "time": start, "booked": booked or 0})
                if len(results) >= limit:
                    break
    return results


@app.route("/")
def home():
    rows = get_db().execute(
        """SELECT t.*, u.first_name || ' ' || u.last_name AS guide_name
           FROM tours t JOIN users u ON u.id = t.guide_id ORDER BY t.id"""
    ).fetchall()
    return render_template("home.html", tours=[tour_from_row(row) for row in rows])


@app.route("/tours")
def tours():
    query = """SELECT t.*, u.first_name || ' ' || u.last_name AS guide_name
               FROM tours t JOIN users u ON u.id = t.guide_id WHERE 1=1"""
    params = []
    language = request.args.get("language", "")
    duration = request.args.get("duration", "")
    requested_date = request.args.get("date", "")
    if language in LANGUAGES:
        query += " AND t.language = ?"
        params.append(language)
    if duration in {"120", "180", "240"}:
        query += " AND t.duration <= ?"
        params.append(int(duration))
    if requested_date:
        try:
            weekday = date.fromisoformat(requested_date).weekday()
            query += " AND EXISTS (SELECT 1 FROM schedules s WHERE s.tour_id = t.id AND s.weekday = ?)"
            params.append(weekday)
        except ValueError:
            flash("Please choose a valid date.", "error")
    rows = get_db().execute(query + " ORDER BY t.id", params).fetchall()
    tours = [tour_from_row(row) for row in rows]
    return render_template("tours.html", tours=tours, languages=LANGUAGES,
                           today=date.today().isoformat())


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/guides")
def guides():
    rows = get_db().execute(
        """SELECT * FROM users WHERE role = 'guide'
           ORDER BY CASE email
             WHEN 'isil@turkishdelight.test' THEN 1
             WHEN 'deniz@turkishdelight.test' THEN 2
             WHEN 'ilker@turkishdelight.test' THEN 3
             WHEN 'nisan@turkishdelight.test' THEN 4
             ELSE 5 END, id"""
    ).fetchall()
    guide_list = []
    for row in rows:
        guide = User(row)
        guide_tours = get_db().execute(
            "SELECT id, title, subtitle FROM tours WHERE guide_id = ? ORDER BY id", (guide.id,)
        ).fetchall()
        image = "Logo.png"
        for tour in guide_tours:
            candidate = BASE_DIR / "static" / f"Guide{tour['id']}.jpg"
            if candidate.exists():
                image = candidate.name
                break
        guide_list.append({"user": guide, "tours": guide_tours, "image": image})
    return render_template("guides.html", guides=guide_list)


@app.route("/tour/<int:tour_id>")
def tour_detail(tour_id):
    row = get_db().execute(
        """SELECT t.*, u.first_name || ' ' || u.last_name AS guide_name
           FROM tours t JOIN users u ON u.id = t.guide_id WHERE t.id = ?""", (tour_id,)
    ).fetchone()
    if not row:
        abort(404)
    schedules = get_db().execute(
        "SELECT weekday, start_time FROM schedules WHERE tour_id = ? ORDER BY weekday", (tour_id,)
    ).fetchall()
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
        languages = [x for x in request.form.getlist("languages") if x in LANGUAGES]
        errors = []
        if not first or not last: errors.append("First and last name are required.")
        if "@" not in email: errors.append("Enter a valid email address.")
        if len(password) < 8: errors.append("Password must be at least 8 characters.")
        if role not in {"guide", "participant"}: errors.append("Choose an account type.")
        if role == "guide" and not languages: errors.append("Guides must choose at least one language.")
        if get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            errors.append("An account with that email already exists.")
        if errors:
            for error in errors: flash(error, "error")
        else:
            cur = get_db().execute(
                "INSERT INTO users(first_name,last_name,email,password_hash,role,languages) VALUES(?,?,?,?,?,?)",
                (first, last, email, generate_password_hash(password), role, json.dumps(languages)),
            )
            get_db().commit()
            login_user(load_user(cur.lastrowid))
            flash("Welcome to Turkish Delight!", "success")
            return redirect(url_for("profile"))
    return render_template("register.html", languages=LANGUAGES)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("profile"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
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
        reservations = db.execute(
            """SELECT r.*, t.title, t.meeting_point, t.duration,
               (SELECT start_time FROM schedules s WHERE s.tour_id=t.id AND s.weekday=CAST(strftime('%w',r.tour_date) AS INTEGER)-1) AS start_time
               FROM reservations r JOIN tours t ON t.id=r.tour_id
               WHERE r.participant_id=? ORDER BY r.tour_date""", (current_user.id,)
        ).fetchall()
        enriched = []
        for reservation in reservations:
            item = dict(reservation)
            item["guests"] = db.execute(
                "SELECT name FROM reservation_guests WHERE reservation_id=?", (item["id"],)
            ).fetchall()
            start = item["start_time"] or db.execute(
                "SELECT start_time FROM schedules WHERE tour_id=? AND weekday=?",
                (item["tour_id"], date.fromisoformat(item["tour_date"]).weekday()),
            ).fetchone()["start_time"]
            item["start_time"] = start
            start_dt = datetime.combine(date.fromisoformat(item["tour_date"]), datetime.strptime(start, "%H:%M").time())
            item["can_cancel"] = start_dt - datetime.now() >= timedelta(hours=24)
            enriched.append(item)
        return render_template("participant_profile.html", reservations=enriched)
    tours = db.execute("SELECT * FROM tours WHERE guide_id=? ORDER BY id", (current_user.id,)).fetchall()
    summaries = []
    for row in tours:
        item = tour_from_row(row)
        item["reservation_count"] = db.execute(
            "SELECT COUNT(*) FROM reservations WHERE tour_id=?", (row["id"],)
        ).fetchone()[0]
        item["dates"] = db.execute(
            """SELECT r.tour_date, COUNT(r.id) + COALESCE(SUM((SELECT COUNT(*) FROM reservation_guests rg WHERE rg.reservation_id=r.id)),0) total
               FROM reservations r WHERE r.tour_id=? GROUP BY r.tour_date ORDER BY r.tour_date""", (row["id"],)
        ).fetchall()
        item["bookings"] = db.execute(
            """SELECT r.tour_date, u.first_name || ' ' || u.last_name AS participant_name,
               1 + (SELECT COUNT(*) FROM reservation_guests rg WHERE rg.reservation_id=r.id) AS group_size
               FROM reservations r JOIN users u ON u.id=r.participant_id
               WHERE r.tour_id=? ORDER BY r.tour_date, u.last_name""", (row["id"],)
        ).fetchall()
        summaries.append(item)
    return render_template("guide_profile.html", tours=summaries)


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    db = get_db()
    statistics = {
        "guides": db.execute("SELECT COUNT(*) FROM users WHERE role='guide'").fetchone()[0],
        "participants": db.execute("SELECT COUNT(*) FROM users WHERE role='participant'").fetchone()[0],
        "tours": db.execute("SELECT COUNT(*) FROM tours").fetchone()[0],
        "reservations": db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0],
    }
    reservations_by_language = db.execute(
        """SELECT t.language, COUNT(r.id) AS total
           FROM tours t LEFT JOIN reservations r ON r.tour_id=t.id
           GROUP BY t.language ORDER BY total DESC, t.language"""
    ).fetchall()
    guide_rows = db.execute(
        "SELECT * FROM users WHERE role='guide' ORDER BY last_name, first_name"
    ).fetchall()
    guides = []
    for guide_row in guide_rows:
        guide = User(guide_row)
        tour_rows = db.execute(
            "SELECT * FROM tours WHERE guide_id=? ORDER BY title", (guide.id,)
        ).fetchall()
        detailed_tours = []
        for tour_row in tour_rows:
            tour = tour_from_row(tour_row)
            tour["schedules"] = db.execute(
                "SELECT weekday,start_time FROM schedules WHERE tour_id=? ORDER BY weekday",
                (tour["id"],),
            ).fetchall()
            tour["reservation_count"] = db.execute(
                "SELECT COUNT(*) FROM reservations WHERE tour_id=?", (tour["id"],)
            ).fetchone()[0]
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
    tour = db.execute("SELECT * FROM tours WHERE id=?", (tour_id,)).fetchone()
    if not tour: abort(404)
    try:
        tour_date = date.fromisoformat(request.form.get("tour_date", ""))
    except ValueError:
        flash("Choose a valid tour date.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    schedule = db.execute(
        "SELECT start_time FROM schedules WHERE tour_id=? AND weekday=?", (tour_id, tour_date.weekday())
    ).fetchone()
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
    booked = db.execute(
        """SELECT COUNT(*) + COALESCE(SUM((SELECT COUNT(*) FROM reservation_guests rg WHERE rg.reservation_id=r.id)),0)
           FROM reservations r WHERE tour_id=? AND tour_date=?""", (tour_id, tour_date.isoformat())
    ).fetchone()[0]
    if booked + 1 + len(guests) > tour["capacity"]:
        flash("There are not enough places left for this group.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    if db.execute("SELECT 1 FROM reservations WHERE participant_id=? AND tour_id=? AND tour_date=?",
                  (current_user.id, tour_id, tour_date.isoformat())).fetchone():
        flash("You already have a reservation for this tour date.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))
    existing = db.execute(
        """SELECT r.tour_date, t.duration, s.start_time FROM reservations r
           JOIN tours t ON t.id=r.tour_id JOIN schedules s ON s.tour_id=t.id AND s.weekday=?
           WHERE r.participant_id=? AND r.tour_date=?""",
        (tour_date.weekday(), current_user.id, tour_date.isoformat()),
    ).fetchall()
    new_end = start_dt + timedelta(minutes=tour["duration"])
    for other in existing:
        other_start = datetime.combine(tour_date, datetime.strptime(other["start_time"], "%H:%M").time())
        if start_dt < other_start + timedelta(minutes=other["duration"]) and other_start < new_end:
            flash("This tour overlaps another reservation in your schedule.", "error")
            return redirect(url_for("tour_detail", tour_id=tour_id))
    cur = db.execute(
        "INSERT INTO reservations(participant_id,tour_id,tour_date,created_at) VALUES(?,?,?,?)",
        (current_user.id, tour_id, tour_date.isoformat(), datetime.now().isoformat(timespec="seconds")),
    )
    for name in guests:
        db.execute("INSERT INTO reservation_guests(reservation_id,name) VALUES(?,?)", (cur.lastrowid, name))
    db.commit()
    flash("Your place is reserved. See you in İzmir!", "success")
    return redirect(url_for("profile"))


@app.route("/reservation/<int:reservation_id>/cancel", methods=["POST"])
@role_required("participant")
def cancel_reservation(reservation_id):
    db = get_db()
    reservation = db.execute(
        "SELECT * FROM reservations WHERE id=? AND participant_id=?", (reservation_id, current_user.id)
    ).fetchone()
    if not reservation: abort(404)
    tour_day = date.fromisoformat(reservation["tour_date"])
    schedule = db.execute("SELECT start_time FROM schedules WHERE tour_id=? AND weekday=?",
                          (reservation["tour_id"], tour_day.weekday())).fetchone()
    start_dt = datetime.combine(tour_day, datetime.strptime(schedule["start_time"], "%H:%M").time())
    if start_dt - datetime.now() < timedelta(hours=24):
        flash("Reservations can only be cancelled at least 24 hours before the tour.", "error")
    else:
        db.execute("DELETE FROM reservations WHERE id=?", (reservation_id,))
        db.commit()
        flash("Your reservation has been cancelled.", "success")
    return redirect(url_for("profile"))


def parse_tour_form(existing=None):
    data = {
        "title": request.form.get("title", "").strip(), "subtitle": request.form.get("subtitle", "").strip(),
        "description": request.form.get("description", "").strip(), "story": request.form.get("story", "").strip(),
        "final_message": request.form.get("final_message", "").strip(),
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
            cur = db.execute(
                """INSERT INTO tours(guide_id,title,subtitle,description,story,final_message,foods,stops,story_points,
                   meeting_point,duration,language,capacity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (current_user.id, data["title"], data["subtitle"], data["description"], data["story"], data["final_message"],
                 json.dumps(data["foods"]), json.dumps(data["stops"]), json.dumps(data["story_points"]),
                 data["meeting_point"], data["duration"], data["language"], data["capacity"]),
            )
            for weekday, start in schedules: db.execute("INSERT INTO schedules VALUES(?,?,?)", (cur.lastrowid, weekday, start))
            for number, photo in enumerate(photos, 1):
                suffix = Path(photo.filename).suffix.lower()
                photo.save(BASE_DIR / "static" / f"Tour{cur.lastrowid}_{number}{suffix}")
            db.commit()
            flash("Tour created.", "success")
            return redirect(url_for("profile"))
    return render_template("tour_form.html", tour=None, languages=current_user.languages, schedule={})


@app.route("/guide/tour/<int:tour_id>/edit", methods=["GET", "POST"])
@role_required("guide")
def edit_tour(tour_id):
    db = get_db()
    row = db.execute("SELECT * FROM tours WHERE id=? AND guide_id=?", (tour_id, current_user.id)).fetchone()
    if not row: abort(404)
    has_reservations = bool(db.execute("SELECT 1 FROM reservations WHERE tour_id=?", (tour_id,)).fetchone())
    if request.method == "POST":
        data, schedules, errors = parse_tour_form(row)
        if errors:
            for error in errors: flash(error, "error")
        else:
            if has_reservations:
                db.execute("""UPDATE tours SET title=?,subtitle=?,description=?,story=?,final_message=?,foods=?,stops=?,story_points=? WHERE id=?""",
                           (data["title"],data["subtitle"],data["description"],data["story"],data["final_message"],
                            json.dumps(data["foods"]),json.dumps(data["stops"]),json.dumps(data["story_points"]),tour_id))
            else:
                db.execute("""UPDATE tours SET title=?,subtitle=?,description=?,story=?,final_message=?,foods=?,stops=?,story_points=?,
                           meeting_point=?,duration=?,language=?,capacity=? WHERE id=?""",
                           (data["title"],data["subtitle"],data["description"],data["story"],data["final_message"],
                            json.dumps(data["foods"]),json.dumps(data["stops"]),json.dumps(data["story_points"]),
                            data["meeting_point"],data["duration"],data["language"],data["capacity"],tour_id))
                db.execute("DELETE FROM schedules WHERE tour_id=?", (tour_id,))
                for weekday, start in schedules: db.execute("INSERT INTO schedules VALUES(?,?,?)", (tour_id,weekday,start))
            db.commit()
            flash("Tour updated.", "success")
            return redirect(url_for("profile"))
    schedule = {r["weekday"]: r["start_time"] for r in db.execute("SELECT * FROM schedules WHERE tour_id=?",(tour_id,))}
    return render_template("tour_form.html", tour=tour_from_row(row), languages=current_user.languages,
                           schedule=schedule, locked=has_reservations)


@app.route("/guide/report/<int:tour_id>", methods=["POST"])
@role_required("guide")
def submit_report(tour_id):
    db = get_db()
    tour = db.execute("SELECT * FROM tours WHERE id=? AND guide_id=?", (tour_id,current_user.id)).fetchone()
    if not tour: abort(404)
    tour_date = request.form.get("tour_date", "")
    if not db.execute("SELECT 1 FROM reservations WHERE tour_id=? AND tour_date=?",(tour_id,tour_date)).fetchone():
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
    db.execute("""INSERT INTO reports(tour_id,tour_date,attendees,evidence_photo) VALUES(?,?,?,?)
                ON CONFLICT(tour_id,tour_date) DO UPDATE SET attendees=excluded.attendees,evidence_photo=excluded.evidence_photo""",
               (tour_id,tour_date,attended,filename))
    db.commit()
    flash("Post-tour report saved.", "success")
    return redirect(url_for("profile"))


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html")
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    message = request.form.get("message", "").strip()
    if not name or "@" not in email or len(message) < 10:
        flash("Please complete your name, email, and a message of at least 10 characters.", "error")
    else:
        get_db().execute("INSERT INTO contact_messages(name,email,message,created_at) VALUES(?,?,?,?)",
                         (name,email,message,datetime.now().isoformat(timespec="seconds")))
        get_db().commit()
        flash("Thank you — we’ll be in touch soon.", "success")
    return redirect(url_for("contact"))


@app.errorhandler(404)
def not_found(_error): return render_template("error.html", code=404, message="That page wandered off the route."), 404


@app.errorhandler(403)
def forbidden(_error): return render_template("error.html", code=403, message="This path is reserved for another account type."), 403


def init_db():
    db = get_db()
    db.executescript((BASE_DIR / "schema.sql").read_text())
    migrate_admin_role(db)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_platform_admin ON users(role) WHERE role='admin'")
    if not db.execute("SELECT 1 FROM users").fetchone():
        seed_db(db)
    ensure_admin_account(db)


def migrate_admin_role(db):
    """Expand older databases without discarding any existing project data."""
    table_sql = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()["sql"]
    if "'admin'" in table_sql:
        return
    db.commit()
    db.executescript("""
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE users_new (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          first_name TEXT NOT NULL, last_name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('guide','participant','admin')),
          languages TEXT NOT NULL DEFAULT '[]'
        );
        INSERT INTO users_new SELECT * FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
        COMMIT;
        PRAGMA foreign_keys = ON;
    """)


def ensure_admin_account(db):
    """The optional Prova finale specification permits one administrator only."""
    admin = db.execute("SELECT id FROM users WHERE role='admin'").fetchone()
    if not admin:
        db.execute(
            """INSERT INTO users(first_name,last_name,email,password_hash,role,languages)
               VALUES(?,?,?,?,?,?)""",
            ("Platform", "Administrator", "admin@turkishdelight.test",
             generate_password_hash("Admin2026!"), "admin", "[]"),
        )
        db.commit()


def seed_db(db):
    users = [
        ("Işıl","Çakan","isil@turkishdelight.test","guide",["English","German"]),
        ("Deniz","Sürür","deniz@turkishdelight.test","guide",["English","Italian"]),
        ("İlker","Başar","ilker@turkishdelight.test","guide",["English","Spanish","German"]),
        ("Nisan","Köse","nisan@turkishdelight.test","guide",["English","Italian"]),
        ("Sofia","Rossi","sofia@example.test","participant",[]),
        ("Lucas","Meyer","lucas@example.test","participant",[]),
        ("Ines","Costa","ines@example.test","participant",[]),
    ]
    ids = []
    for first,last,email,role,languages in users:
        ids.append(db.execute("INSERT INTO users(first_name,last_name,email,password_hash,role,languages) VALUES(?,?,?,?,?,?)",
                              (first,last,email,generate_password_hash("Delight2026!"),role,json.dumps(languages))).lastrowid)
    tours = [
        (ids[1],"Sweet İzmir","Empires Through Desserts","Explore İzmir through its famous sweets and discover how desserts became symbols of charity, memory, and celebration.","From Ottoman palace kitchens to neighbourhood lokma stands, İzmir’s sweets carry customs across generations.","In İzmir, desserts are not only food—they are acts of memory, charity and community.",["Şambali","Turkish Delight","Lokma"],["Kemeraltı Bazaar","Historical Şambali shop","Hisar Mosque","Konak Square","Traditional Lokma stand"],["Ottoman cuisine","Religious traditions","Why lokma is distributed during funerals and celebrations","Desserts as part of social life and community"],"Kemeraltı main gate",150,"English",12),
        (ids[2],"Coffee and the Ottoman Empire","The Drink That Conquered Europe","Discover how Ottoman coffee culture transformed Europe and gave birth to modern cafés.","Follow the coffee bean from Ottoman trade routes and convivial hans to the café tables of Europe.","Without Ottoman coffeehouses, modern cafés in Europe might never have existed.",["Turkish Coffee","Optional Turkish Delight"],["Kızlarağası Han","Kemeraltı Bazaar","Hisar Mosque","Konak Square","İzmir Clock Tower"],["Ottoman trade routes","Coffee culture","Historical coffeehouses","The spread of coffee to Europe"],"Courtyard of Kızlarağası Han",120,"English",10),
        (ids[0],"Wine and Ancient Greeks","The Taste of Ancient Smyrna","Travel back to Ancient Smyrna and experience the role of wine in Greek and Roman civilization.","At Smyrna’s ancient stones, learn how vines, ritual, and commerce connected the city to a Mediterranean world.","Wine connected Ancient Smyrna to the entire Mediterranean world.",["Grapes","Local cheeses","Aegean wines"],["Agora of Smyrna","Kadifekale","Ancient Theatre of Smyrna","Optional extension to Urla vineyards"],["Ancient Greeks","Dionysus","Trade with Rome","Wine culture of Ancient Smyrna"],"Agora visitor entrance",180,"German",8),
        (ids[3],"The Boyoz Story","How Immigrants Shaped İzmir","Discover the story of the Sephardic Jews and how a pastry from Spain became one of İzmir's most iconic foods.","Trace a 500-year migration through synagogues, market lanes, and the layered folds of a beloved pastry.","You are eating a recipe that travelled from Spain over 500 years ago.",["Boyoz"],["Dostlar Fırını","Kemeraltı Bazaar","Havra Street","Synagogue District","Kızlarağası Han"],["Expulsion of Sephardic Jews from Spain","Arrival in the Ottoman Empire","Multicultural history of İzmir","Food and migration"],"Dostlar Fırını, Alsancak",135,"Italian",10),
    ]
    schedules = [[(1,"10:00"),(5,"10:30")],[(2,"14:00"),(6,"11:00")],[(4,"15:00"),(6,"15:00")],[(0,"09:30"),(5,"09:30")]]
    tour_ids=[]
    for t, sched in zip(tours,schedules):
        cur=db.execute("""INSERT INTO tours(guide_id,title,subtitle,description,story,final_message,foods,stops,story_points,meeting_point,duration,language,capacity)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(t[0],t[1],t[2],t[3],t[4],t[5],json.dumps(t[6]),json.dumps(t[7]),json.dumps(t[8]),*t[9:]))
        tour_ids.append(cur.lastrowid)
        for weekday,start in sched: db.execute("INSERT INTO schedules VALUES(?,?,?)",(cur.lastrowid,weekday,start))
    for participant_id,tour_id,days_ahead in [(ids[4],tour_ids[0],5),(ids[5],tour_ids[1],6),(ids[6],tour_ids[3],3)]:
        weekday=db.execute("SELECT weekday FROM schedules WHERE tour_id=? ORDER BY weekday LIMIT 1",(tour_id,)).fetchone()[0]
        d=date.today()+timedelta(days=days_ahead)
        d += timedelta(days=(weekday-d.weekday())%7)
        cur=db.execute("INSERT INTO reservations(participant_id,tour_id,tour_date,created_at) VALUES(?,?,?,?)",(participant_id,tour_id,d.isoformat(),datetime.now().isoformat()))
        if participant_id==ids[4]: db.execute("INSERT INTO reservation_guests(reservation_id,name) VALUES(?,?)",(cur.lastrowid,"Marco Rossi"))
    past_day = date.today() - timedelta(days=1)
    past_weekday = db.execute("SELECT weekday FROM schedules WHERE tour_id=? ORDER BY weekday LIMIT 1", (tour_ids[0],)).fetchone()[0]
    past_day -= timedelta(days=(past_day.weekday() - past_weekday) % 7)
    db.execute("INSERT INTO reservations(participant_id,tour_id,tour_date,created_at) VALUES(?,?,?,?)",
               (ids[5], tour_ids[0], past_day.isoformat(), datetime.now().isoformat()))
    db.commit()


with app.app_context():
    init_db()


if __name__ == "__main__":
    # Port 5000 is commonly occupied by AirPlay Receiver on macOS.
    app.run(debug=True, port=8000)
