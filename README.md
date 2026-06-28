# Procurement Control Demo

A compact Flask + SQLite procurement tracker for engineering material visibility.

## Features

- Viewer mode works without a password.
- Manager login reveals commercial data and unlocks edit, delete, audit, users, settings, and backups.
- Viewer can create procurement requests, but cannot see or enter prices.
- MMS No. accepts numbers only, quantity is stored as an integer, and currency supports MOP, HKD, USD, and CNY.
- List dashboard with MMS No., item, quantity, requester, PR/PO dates, purchase date, ETA, received status, and operational statistics.
- Per-item timeline with generated milestones and manager-added events.
- Audit log for login, failed login, logout, create, update, delete, user changes, timeline events, and backups.
- One automatic database backup per day, plus manual backups from Settings.

## Run

```powershell
cd "E:\Users\Figo\Documents\Thailand Travelling\procurement_demo"
py -m pip install -r requirements.txt
py app.py
```

Open:

```text
http://127.0.0.1:5000
```

Default manager account:

```text
admin / admin123
```

## Data

- Database: `data/procurement.sqlite3`
- Backups: `backups/`

The repository includes a demo SQLite database so the app can be tested immediately after cloning.

This is a local demo. Before using it in production, change the secret key, remove the default password, and run behind a real WSGI server with HTTPS.
