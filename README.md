# Turkish Delight

A responsive Flask + SQLite platform for free walking tours that talks about history with foods in İzmir.

## Live website

The deployed application is available at [https://defneakbulut.pythonanywhere.com/](https://defneakbulut.pythonanywhere.com/).

## Code structure

- `app.py` — Flask routes, form validation, and application setup
- `user.py` — authenticated `User` model
- `userdb.py` — user queries, registration, roles, and administrator setup
- `tourdb.py` — tour, schedule, reservation, and reporting queries
- `schema.sql` — SQLite table definitions

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`. The SQLite database and sample data are created automatically.

## Sample accounts

All sample accounts use password `Delight2026!`.

- Guide: `isil@turkishdelight.test`
- Guide: `deniz@turkishdelight.test`
- Guide: `ilker@turkishdelight.test`
- Guide: `nisan@turkishdelight.test`
- Participant: `sofia@example.test`
- Participant: `lucas@example.test`
- Participant: `ines@example.test`

Administrator account (Prova finale):

- Email: `admin@turkishdelight.test`
- Password: `Admin2026!`
- Dashboard: `/admin`


Some websites that I was inspired by while designing:
https://www.izmir.bel.tr/tr/Anasayfa
https://goturkiye.com/izmir/routes
