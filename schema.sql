CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name TEXT NOT NULL, last_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('guide','participant','admin')),
  languages TEXT NOT NULL DEFAULT '[]'
);
CREATE UNIQUE INDEX IF NOT EXISTS one_platform_admin ON users(role) WHERE role = 'admin';
CREATE TABLE IF NOT EXISTS tours (
  id INTEGER PRIMARY KEY AUTOINCREMENT, guide_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, subtitle TEXT NOT NULL, description TEXT NOT NULL, story TEXT NOT NULL,
  final_message TEXT NOT NULL, foods TEXT NOT NULL, stops TEXT NOT NULL, story_points TEXT NOT NULL,
  meeting_point TEXT NOT NULL, duration INTEGER NOT NULL CHECK(duration > 0),
  language TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity > 0)
);
CREATE TABLE IF NOT EXISTS schedules (
  tour_id INTEGER NOT NULL REFERENCES tours(id) ON DELETE CASCADE,
  weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6), start_time TEXT NOT NULL,
  PRIMARY KEY(tour_id, weekday)
);
CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, participant_id INTEGER NOT NULL REFERENCES users(id),
  tour_id INTEGER NOT NULL REFERENCES tours(id), tour_date TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(participant_id,tour_id,tour_date)
);
CREATE TABLE IF NOT EXISTS reservation_guests (
  id INTEGER PRIMARY KEY AUTOINCREMENT, reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tour_id INTEGER NOT NULL REFERENCES tours(id),
  tour_date TEXT NOT NULL, attendees INTEGER NOT NULL, evidence_photo TEXT NOT NULL,
  UNIQUE(tour_id,tour_date)
);
CREATE TABLE IF NOT EXISTS contact_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL,
  message TEXT NOT NULL, created_at TEXT NOT NULL
);
