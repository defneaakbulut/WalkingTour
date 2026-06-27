import json

from flask_login import UserMixin


class User(UserMixin):
    """Authenticated application user backed by a SQLite row."""

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
