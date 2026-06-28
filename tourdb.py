"""Database queries for tours, schedules, reservations, and reports."""

import json


# Tour catalogue and weekly schedule queries.
def list_tours(db, language="", max_duration=None, weekday=None):
    query = """SELECT t.*, u.first_name || ' ' || u.last_name AS guide_name
               FROM tours t JOIN users u ON u.id=t.guide_id WHERE 1=1"""
    params = []
    if language:
        query += " AND t.language=?"
        params.append(language)
    if max_duration:
        query += " AND t.duration<=?"
        params.append(max_duration)
    if weekday is not None:
        query += " AND EXISTS (SELECT 1 FROM schedules s WHERE s.tour_id=t.id AND s.weekday=?)"
        params.append(weekday)
    return db.execute(query + " ORDER BY t.id", params).fetchall()


def get_tour(db, tour_id, guide_id=None):
    query = "SELECT * FROM tours WHERE id=?"
    params = [tour_id]
    if guide_id is not None:
        query += " AND guide_id=?"
        params.append(guide_id)
    return db.execute(query, params).fetchone()


def get_tour_with_guide(db, tour_id):
    return db.execute(
        """SELECT t.*, u.first_name || ' ' || u.last_name AS guide_name,
           u.profile_photo AS guide_image
           FROM tours t JOIN users u ON u.id=t.guide_id WHERE t.id=?""",
        (tour_id,),
    ).fetchone()


def tours_for_guide(db, guide_id, summary=False):
    fields = "id,title,subtitle" if summary else "*"
    return db.execute(
        f"SELECT {fields} FROM tours WHERE guide_id=? ORDER BY id", (guide_id,)
    ).fetchall()


def schedules_for_tour(db, tour_id):
    return db.execute(
        "SELECT weekday,start_time FROM schedules WHERE tour_id=? ORDER BY weekday", (tour_id,)
    ).fetchall()


def schedule_map(db, tour_id):
    return {row["weekday"]: row["start_time"] for row in schedules_for_tour(db, tour_id)}


def schedule_for_day(db, tour_id, weekday):
    return db.execute(
        "SELECT start_time FROM schedules WHERE tour_id=? AND weekday=?", (tour_id, weekday)
    ).fetchone()


# Reservation totals include the participant and any named guests.
def booked_places(db, tour_id, tour_date):
    return db.execute(
        """SELECT COUNT(*) + COALESCE(SUM((SELECT COUNT(*) FROM reservation_guests rg
           WHERE rg.reservation_id=r.id)),0) FROM reservations r
           WHERE tour_id=? AND tour_date=?""",
        (tour_id, tour_date),
    ).fetchone()[0]


def participant_reservations(db, participant_id):
    return db.execute(
        """SELECT r.*, t.title, t.meeting_point, t.duration,
           (SELECT start_time FROM schedules s WHERE s.tour_id=t.id
            AND s.weekday=CAST(strftime('%w',r.tour_date) AS INTEGER)-1) AS start_time
           FROM reservations r JOIN tours t ON t.id=r.tour_id
           WHERE r.participant_id=? ORDER BY r.tour_date""",
        (participant_id,),
    ).fetchall()


def reservation_guests(db, reservation_id):
    return db.execute(
        "SELECT name FROM reservation_guests WHERE reservation_id=?", (reservation_id,)
    ).fetchall()


def guide_tour_dates(db, tour_id):
    return db.execute(
        """SELECT r.tour_date, COUNT(r.id) + COALESCE(SUM((SELECT COUNT(*)
           FROM reservation_guests rg WHERE rg.reservation_id=r.id)),0) total
           FROM reservations r WHERE r.tour_id=? GROUP BY r.tour_date ORDER BY r.tour_date""",
        (tour_id,),
    ).fetchall()


def guide_tour_bookings(db, tour_id):
    return db.execute(
        """SELECT r.tour_date, u.first_name || ' ' || u.last_name AS participant_name,
           1 + (SELECT COUNT(*) FROM reservation_guests rg WHERE rg.reservation_id=r.id) AS group_size
           FROM reservations r JOIN users u ON u.id=r.participant_id
           WHERE r.tour_id=? ORDER BY r.tour_date,u.last_name""",
        (tour_id,),
    ).fetchall()


def reservation_count(db, tour_id=None):
    if tour_id is None:
        return db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
    return db.execute("SELECT COUNT(*) FROM reservations WHERE tour_id=?", (tour_id,)).fetchone()[0]


def tour_count(db):
    return db.execute("SELECT COUNT(*) FROM tours").fetchone()[0]


def reservations_by_language(db):
    return db.execute(
        """SELECT t.language,COUNT(r.id) AS total FROM tours t
           LEFT JOIN reservations r ON r.tour_id=t.id
           GROUP BY t.language ORDER BY total DESC,t.language"""
    ).fetchall()


def reservation_exists(db, participant_id, tour_id, tour_date):
    return bool(db.execute(
        "SELECT 1 FROM reservations WHERE participant_id=? AND tour_id=? AND tour_date=?",
        (participant_id, tour_id, tour_date),
    ).fetchone())


def overlapping_reservations(db, participant_id, tour_date, weekday):
    return db.execute(
        """SELECT r.tour_date,t.duration,s.start_time FROM reservations r
           JOIN tours t ON t.id=r.tour_id
           JOIN schedules s ON s.tour_id=t.id AND s.weekday=?
           WHERE r.participant_id=? AND r.tour_date=?""",
        (weekday, participant_id, tour_date),
    ).fetchall()


def create_reservation(db, participant_id, tour_id, tour_date, guests, created_at):
    cursor = db.execute(
        "INSERT INTO reservations(participant_id,tour_id,tour_date,created_at) VALUES(?,?,?,?)",
        (participant_id, tour_id, tour_date, created_at),
    )
    for name in guests:
        db.execute(
            "INSERT INTO reservation_guests(reservation_id,name) VALUES(?,?)",
            (cursor.lastrowid, name),
        )
    db.commit()
    return cursor.lastrowid


def get_participant_reservation(db, reservation_id, participant_id):
    return db.execute(
        "SELECT * FROM reservations WHERE id=? AND participant_id=?",
        (reservation_id, participant_id),
    ).fetchone()


def cancel_reservation(db, reservation_id):
    db.execute("DELETE FROM reservations WHERE id=?", (reservation_id,))
    db.commit()


def has_tour_reservations(db, tour_id):
    return bool(db.execute("SELECT 1 FROM reservations WHERE tour_id=?", (tour_id,)).fetchone())


# Tour changes keep their weekly schedules in the separate schedules table.
def create_tour(db, guide_id, data, schedules):
    cursor = db.execute(
        """INSERT INTO tours(guide_id,title,subtitle,description,story,final_message,
           foods,stops,story_points,meeting_point,duration,language,capacity)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (guide_id, data["title"], data["subtitle"], data["description"], data["story"],
         data["final_message"], json.dumps(data["foods"]), json.dumps(data["stops"]),
         json.dumps(data["story_points"]), data["meeting_point"], data["duration"],
         data["language"], data["capacity"]),
    )
    replace_schedules(db, cursor.lastrowid, schedules)
    db.commit()
    return cursor.lastrowid


def replace_schedules(db, tour_id, schedules):
    db.execute("DELETE FROM schedules WHERE tour_id=?", (tour_id,))
    for weekday, start_time in schedules:
        db.execute(
            "INSERT INTO schedules(tour_id,weekday,start_time) VALUES(?,?,?)",
            (tour_id, weekday, start_time),
        )


def update_tour(db, tour_id, data, schedules=None, essential=True):
    common = (data["title"], data["subtitle"], data["description"], data["story"],
              data["final_message"], json.dumps(data["foods"]), json.dumps(data["stops"]),
              json.dumps(data["story_points"]))
    if essential:
        db.execute(
            """UPDATE tours SET title=?,subtitle=?,description=?,story=?,final_message=?,foods=?,
               stops=?,story_points=?,meeting_point=?,duration=?,language=?,capacity=? WHERE id=?""",
            common + (data["meeting_point"], data["duration"], data["language"],
                      data["capacity"], tour_id),
        )
        replace_schedules(db, tour_id, schedules or [])
    else:
        db.execute(
            """UPDATE tours SET title=?,subtitle=?,description=?,story=?,final_message=?,
               foods=?,stops=?,story_points=? WHERE id=?""",
            common + (tour_id,),
        )
    db.commit()


def date_has_reservations(db, tour_id, tour_date):
    return bool(db.execute(
        "SELECT 1 FROM reservations WHERE tour_id=? AND tour_date=?", (tour_id, tour_date)
    ).fetchone())


def save_report(db, tour_id, tour_date, attendees, evidence_photo):
    """Insert a report, or replace its values for the same tour and date."""
    db.execute(
        """INSERT INTO reports(tour_id,tour_date,attendees,evidence_photo) VALUES(?,?,?,?)
           ON CONFLICT(tour_id,tour_date) DO UPDATE SET
           attendees=excluded.attendees,evidence_photo=excluded.evidence_photo""",
        (tour_id, tour_date, attendees, evidence_photo),
    )
    db.commit()
