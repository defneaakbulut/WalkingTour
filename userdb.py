import json

from werkzeug.security import generate_password_hash

from user import User

PASSWORD_METHOD = "pbkdf2:sha256"


def hash_password(password):
    """Use a method supported by Python 3.9 and PythonAnywhere."""
    return generate_password_hash(password, method=PASSWORD_METHOD)


def get_user(db, user_id):
    row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return User(row) if row else None


def get_user_by_email(db, email):
    return db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()


def get_guide(db, guide_id):
    row = db.execute(
        "SELECT * FROM users WHERE id=? AND role='guide'", (guide_id,)
    ).fetchone()
    return User(row) if row else None


def email_exists(db, email):
    return bool(db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone())


def create_user(db, first_name, last_name, email, password, role, languages):
    cursor = db.execute(
        """INSERT INTO users(first_name,last_name,email,password_hash,role,languages)
           VALUES(?,?,?,?,?,?)""",
        (first_name, last_name, email, hash_password(password), role, json.dumps(languages)),
    )
    db.commit()
    return cursor.lastrowid


def list_guides(db, public_order=False):
    order = "last_name, first_name"
    if public_order:
        order = """CASE email
          WHEN 'isil@turkishdelight.test' THEN 1
          WHEN 'deniz@turkishdelight.test' THEN 2
          WHEN 'ilker@turkishdelight.test' THEN 3
          WHEN 'nisan@turkishdelight.test' THEN 4
          ELSE 5 END, id"""
    return db.execute(f"SELECT * FROM users WHERE role='guide' ORDER BY {order}").fetchall()


def count_role(db, role):
    return db.execute("SELECT COUNT(*) FROM users WHERE role=?", (role,)).fetchone()[0]


def has_users(db):
    return bool(db.execute("SELECT 1 FROM users").fetchone())


def prepare_user_schema(db):
    """Expand older databases to support the optional administrator role."""
    table_sql = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()["sql"]
    if "'admin'" not in table_sql:
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
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS one_platform_admin ON users(role) WHERE role='admin'"
    )


def ensure_admin_account(db):
    if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        create_user(
            db, "Platform", "Administrator", "admin@turkishdelight.test",
            "Admin2026!", "admin", [],
        )


def migrate_sample_password_hashes(db):
    """Replace incompatible scrypt hashes for the documented sample accounts."""
    sample_passwords = {
        "isil@turkishdelight.test": "Delight2026!",
        "deniz@turkishdelight.test": "Delight2026!",
        "ilker@turkishdelight.test": "Delight2026!",
        "nisan@turkishdelight.test": "Delight2026!",
        "sofia@example.test": "Delight2026!",
        "lucas@example.test": "Delight2026!",
        "ines@example.test": "Delight2026!",
        "admin@turkishdelight.test": "Admin2026!",
    }
    changed = False
    for email, password in sample_passwords.items():
        row = db.execute("SELECT password_hash FROM users WHERE email=?", (email,)).fetchone()
        if row and row["password_hash"].startswith("scrypt:"):
            db.execute(
                "UPDATE users SET password_hash=? WHERE email=?",
                (hash_password(password), email),
            )
            changed = True
    if changed:
        db.commit()


def seed_sample_users(db):
    sample_users = [
        ("Işıl", "Çakan", "isil@turkishdelight.test", "guide", ["English", "German"]),
        ("Deniz", "Sürür", "deniz@turkishdelight.test", "guide", ["English", "Italian"]),
        ("İlker", "Başar", "ilker@turkishdelight.test", "guide", ["English", "Spanish", "German"]),
        ("Nisan", "Köse", "nisan@turkishdelight.test", "guide", ["English", "Italian"]),
        ("Sofia", "Rossi", "sofia@example.test", "participant", []),
        ("Lucas", "Meyer", "lucas@example.test", "participant", []),
        ("Ines", "Costa", "ines@example.test", "participant", []),
    ]
    ids = []
    for first, last, email, role, languages in sample_users:
        cursor = db.execute(
            """INSERT INTO users(first_name,last_name,email,password_hash,role,languages)
               VALUES(?,?,?,?,?,?)""",
            (first, last, email, hash_password("Delight2026!"), role, json.dumps(languages)),
        )
        ids.append(cursor.lastrowid)
    db.commit()
    return ids
