# Procurement Control Demo

A compact single-file Flask procurement tracker for Windows server deployment.

## Files

- `app.py`: application, pages, styles, and database logic.
- `config.ini`: host, port, and debug settings.
- `requirements.txt`: Python dependency list.
- `data/procurement.sqlite3`: demo SQLite database.
- `backups/`: automatic and manual database backups, ignored by Git.

## Run On Windows

```powershell
cd C:\path\to\procurement-control-demo
py -m pip install -r requirements.txt
py app.py
```

Open:

```text
http://SERVER_IP:5000
```

Change the port in `config.ini`:

```ini
[server]
host = 0.0.0.0
port = 5000
debug = false
```

For Windows Task Scheduler, set:

- Program: `py`
- Arguments: `app.py`
- Start in: the project folder path

Default manager account:

```text
admin / admin123
```

## Features

- Viewer mode works without a password.
- Manager mode reveals price and unlocks edit, delete, users, audit log, settings, and backups.
- MMS No. accepts numbers only.
- Quantity is stored as an integer.
- Currency supports MOP, HKD, USD, and CNY.
- Engineering follow-up list includes MMS No., item, quantity, price for managers, priority, requester, request date, owner, PR No./date, PO No./date, purchase date, received status, and status.
- Clickable dashboard status cards for pending arrival, received, late arrival, and open PR.
- Per-item timeline and audit log.
- One automatic backup per day plus manual backups from Settings.
