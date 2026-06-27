# Turkish Delight

A responsive Flask + SQLite platform for food-led free walking tours in İzmir.

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

Set a secure `SECRET_KEY` environment variable in production. For PythonAnywhere, point the WSGI file at `app` in `app.py` and set the working directory to this project.
