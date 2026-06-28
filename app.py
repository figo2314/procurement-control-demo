import json
import os
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "procurement.sqlite3"

APP_FIELDS = [
    "mms_no",
    "item_name",
    "quantity",
    "price",
    "currency",
    "requester",
    "supplier",
    "department",
    "purchase_date",
    "pr_created_at",
    "po_created_at",
    "expected_arrival_date",
    "arrival_date",
    "status",
    "received",
    "notes",
]

TIMELINE_LABELS = {
    "requested": "Request created",
    "pr_created": "PR created",
    "po_created": "PO created",
    "ordered": "Purchase ordered",
    "expected_arrival": "Expected arrival",
    "arrived": "Goods arrived",
    "updated": "Record updated",
}

STATUS_OPTIONS = [
    "Draft",
    "PR Created",
    "PO Created",
    "Ordered",
    "Partially Received",
    "Received",
    "Delayed",
]

CURRENCY_OPTIONS = ["MOP", "HKD", "USD", "CNY"]


app = Flask(__name__)
app.secret_key = os.environ.get("PROCUREMENT_SECRET", "demo-secret-change-me")


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if "db" not in g:
        DATA_DIR.mkdir(exist_ok=True)
        BACKUP_DIR.mkdir(exist_ok=True)
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'manager',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS procurement_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_no TEXT,
            item_name TEXT NOT NULL,
            quantity INTEGER,
            price REAL,
            currency TEXT DEFAULT 'MOP',
            requester TEXT,
            supplier TEXT,
            department TEXT,
            purchase_date TEXT,
            pr_created_at TEXT,
            po_created_at TEXT,
            expected_arrival_date TEXT,
            arrival_date TEXT,
            status TEXT NOT NULL DEFAULT 'Draft',
            received INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            event_date TEXT,
            details TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(item_id) REFERENCES procurement_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            summary TEXT,
            changes TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            reason TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    db.commit()
    migrate_existing_data()

    admin = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        db.execute(
            """
            INSERT INTO users (username, password_hash, role, active, created_at)
            VALUES (?, ?, 'manager', 1, ?)
            """,
            ("admin", generate_password_hash("admin123"), now_iso()),
        )
        db.commit()
        audit_log("system", "system", "create_default_admin", "user", "admin", "Default admin user created")

    count = db.execute("SELECT COUNT(*) AS count FROM procurement_items").fetchone()["count"]
    if count == 0:
        seed_demo_data()


def current_role():
    return session.get("role", "viewer")


def current_actor():
    return session.get("username", "viewer")


def is_manager():
    return current_role() == "manager"


@app.context_processor
def inject_context():
    return {
        "current_role": current_role(),
        "current_actor": current_actor(),
        "is_manager": is_manager(),
        "status_options": STATUS_OPTIONS,
        "currency_options": CURRENCY_OPTIONS,
    }


def manager_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_manager():
            audit_log(current_actor(), current_role(), "permission_denied", "route", request.path, "Manager access required")
            flash("Manager access is required for this action.", "warning")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def audit_log(actor, role, action, target_type, target_id=None, summary=None, changes=None):
    db = get_db()
    db.execute(
        """
        INSERT INTO audit_logs
            (actor, role, action, target_type, target_id, summary, changes, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor,
            role,
            action,
            target_type,
            str(target_id) if target_id is not None else None,
            summary,
            json.dumps(changes, ensure_ascii=True, default=str) if changes else None,
            request.headers.get("X-Forwarded-For", request.remote_addr) if request else None,
            now_iso(),
        ),
    )
    db.commit()


def backup_database(reason="daily", actor="system"):
    if not DB_PATH.exists():
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"procurement_{reason}_{stamp}.sqlite3"
    target = BACKUP_DIR / filename

    source = connect_db()
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    db = get_db()
    db.execute(
        "INSERT INTO backups (filename, reason, actor, created_at) VALUES (?, ?, ?, ?)",
        (filename, reason, actor, now_iso()),
    )
    db.execute(
        """
        INSERT OR REPLACE INTO app_meta (key, value)
        VALUES ('last_daily_backup_date', ?)
        """,
        (date.today().isoformat(),),
    )
    db.commit()
    audit_log(actor, current_role() if actor != "system" else "system", "backup_created", "database", filename, f"{reason.title()} backup created")
    return target


def ensure_daily_backup():
    db = get_db()
    last = db.execute("SELECT value FROM app_meta WHERE key = 'last_daily_backup_date'").fetchone()
    today = date.today().isoformat()
    if not last or last["value"] != today:
        backup_database("daily", "system")


def form_value(name, default=None):
    value = request.form.get(name, "").strip()
    return value if value != "" else default


def numeric_value(name):
    value = form_value(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def integer_value(name):
    value = form_value(name)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def validate_item_data(data):
    errors = []
    if data.get("mms_no") and not data["mms_no"].isdigit():
        errors.append("MMS No. must contain numbers only.")
    if data.get("currency") not in CURRENCY_OPTIONS:
        errors.append("Currency must be MOP, HKD, USD, or CNY.")
    return errors


def item_from_form(existing=None):
    existing = existing or {}
    data = {
        "mms_no": form_value("mms_no"),
        "item_name": form_value("item_name") or "Untitled item",
        "quantity": integer_value("quantity"),
        "currency": form_value("currency", "MOP"),
        "requester": form_value("requester"),
        "supplier": form_value("supplier"),
        "department": form_value("department"),
        "purchase_date": form_value("purchase_date"),
        "pr_created_at": form_value("pr_created_at"),
        "po_created_at": form_value("po_created_at"),
        "expected_arrival_date": form_value("expected_arrival_date"),
        "arrival_date": form_value("arrival_date"),
        "status": form_value("status", "Draft"),
        "received": 1 if request.form.get("received") == "on" else 0,
        "notes": form_value("notes"),
    }
    if is_manager():
        data["price"] = numeric_value("price")
    else:
        data["price"] = existing.get("price") if existing else None
    return data


def merge_item_for_form(existing, data):
    merged = dict(existing) if existing else {}
    merged.update(data)
    return merged


def migrate_existing_data():
    db = get_db()
    rows = db.execute("SELECT id, mms_no, currency, quantity FROM procurement_items").fetchall()
    for row in rows:
        updates = {}
        if row["currency"] in (None, "", "THB"):
            updates["currency"] = "MOP"
        if row["mms_no"] and not row["mms_no"].isdigit():
            updates["mms_no"] = "".join(ch for ch in row["mms_no"] if ch.isdigit())
        if row["quantity"] is not None:
            updates["quantity"] = int(row["quantity"])
        if updates:
            assignments = ", ".join(f"{field} = ?" for field in updates)
            db.execute(
                f"UPDATE procurement_items SET {assignments} WHERE id = ?",
                list(updates.values()) + [row["id"]],
            )
    db.commit()


def visible_item(row):
    item = dict(row)
    if not is_manager():
        item["price"] = None
    return item


def changes_between(before, after):
    changes = {}
    for key, value in after.items():
        old = before[key] if before and key in before.keys() else None
        if str(old or "") != str(value or ""):
            if key == "price" and not is_manager():
                continue
            changes[key] = {"from": old, "to": value}
    return changes


def sync_timeline_events(item_id, data, actor):
    generated = [
        ("pr_created", "PR created", data.get("pr_created_at"), "Purchase requisition was created."),
        ("po_created", "PO created", data.get("po_created_at"), "Purchase order was created."),
        ("ordered", "Purchase ordered", data.get("purchase_date"), "Order was placed with supplier."),
        ("expected_arrival", "Expected arrival", data.get("expected_arrival_date"), "Planned goods arrival date."),
        ("arrived", "Goods arrived", data.get("arrival_date"), "Goods have arrived.") if data.get("received") else None,
    ]
    db = get_db()
    for event in [e for e in generated if e]:
        event_type, title, event_date, details = event
        existing = db.execute(
            "SELECT id FROM timeline_events WHERE item_id = ? AND event_type = ?",
            (item_id, event_type),
        ).fetchone()
        if event_date:
            if existing:
                db.execute(
                    """
                    UPDATE timeline_events
                    SET title = ?, event_date = ?, details = ?, created_by = ?
                    WHERE id = ?
                    """,
                    (title, event_date, details, actor, existing["id"]),
                )
            else:
                db.execute(
                    """
                    INSERT INTO timeline_events
                        (item_id, event_type, title, event_date, details, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (item_id, event_type, title, event_date, details, actor, now_iso()),
                )
        elif existing and event_type != "arrived":
            db.execute("DELETE FROM timeline_events WHERE id = ?", (existing["id"],))
    db.commit()


def add_update_event(item_id, changes, actor):
    if not changes:
        return
    changed_fields = ", ".join(changes.keys())
    get_db().execute(
        """
        INSERT INTO timeline_events
            (item_id, event_type, title, event_date, details, created_by, created_at)
        VALUES (?, 'updated', 'Record updated', ?, ?, ?, ?)
        """,
        (item_id, date.today().isoformat(), f"Updated fields: {changed_fields}", actor, now_iso()),
    )
    get_db().commit()


def seed_demo_data():
    samples = [
        {
            "mms_no": "2406001",
            "item_name": "Stainless steel pipe DN50",
            "quantity": 48,
            "price": 62400,
            "currency": "MOP",
            "requester": "Narin",
            "supplier": "Thai Industrial Supply",
            "department": "Engineering",
            "purchase_date": "2026-06-18",
            "pr_created_at": "2026-06-14",
            "po_created_at": "2026-06-17",
            "expected_arrival_date": "2026-07-02",
            "arrival_date": "",
            "status": "Ordered",
            "received": 0,
            "notes": "Required for utility line maintenance.",
        },
        {
            "mms_no": "2406002",
            "item_name": "PLC input module",
            "quantity": 6,
            "price": 91500,
            "currency": "MOP",
            "requester": "Somchai",
            "supplier": "Automation Partner Co.",
            "department": "Maintenance",
            "purchase_date": "2026-06-08",
            "pr_created_at": "2026-06-03",
            "po_created_at": "2026-06-07",
            "expected_arrival_date": "2026-06-26",
            "arrival_date": "2026-06-25",
            "status": "Received",
            "received": 1,
            "notes": "Critical spare for line 2.",
        },
        {
            "mms_no": "2406003",
            "item_name": "Safety light curtain",
            "quantity": 2,
            "price": 43800,
            "currency": "MOP",
            "requester": "Maya",
            "supplier": "Pending sourcing",
            "department": "EHS",
            "purchase_date": "",
            "pr_created_at": "2026-06-20",
            "po_created_at": "",
            "expected_arrival_date": "",
            "arrival_date": "",
            "status": "PR Created",
            "received": 0,
            "notes": "Waiting for final quotation.",
        },
    ]

    db = get_db()
    for sample in samples:
        columns = ", ".join(sample.keys()) + ", created_by, created_at, updated_by, updated_at"
        placeholders = ", ".join(["?"] * (len(sample) + 4))
        values = list(sample.values()) + ["system", now_iso(), "system", now_iso()]
        cursor = db.execute(f"INSERT INTO procurement_items ({columns}) VALUES ({placeholders})", values)
        sync_timeline_events(cursor.lastrowid, sample, "system")
    db.commit()
    audit_log("system", "system", "seed_demo_data", "database", None, "Demo procurement records created")


def stats():
    db = get_db()
    rows = db.execute("SELECT * FROM procurement_items").fetchall()
    total = len(rows)
    received = sum(1 for row in rows if row["received"])
    pending = total - received
    delayed = 0
    today = date.today().isoformat()
    for row in rows:
        if not row["received"] and row["expected_arrival_date"] and row["expected_arrival_date"] < today:
            delayed += 1
    total_value = sum((row["price"] or 0) for row in rows)
    pending_pr = sum(1 for row in rows if not row["po_created_at"])
    return {
        "total": total,
        "received": received,
        "pending": pending,
        "delayed": delayed,
        "total_value": total_value,
        "pending_pr": pending_pr,
    }


@app.before_request
def prepare_app():
    init_db()
    ensure_daily_backup()


@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    sql = "SELECT * FROM procurement_items WHERE 1=1"
    params = []
    if search:
        sql += " AND (mms_no LIKE ? OR item_name LIKE ? OR requester LIKE ? OR supplier LIKE ? OR department LIKE ?)"
        needle = f"%{search}%"
        params.extend([needle] * 5)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY COALESCE(expected_arrival_date, '9999-12-31'), updated_at DESC"
    rows = get_db().execute(sql, params).fetchall()
    return render_template("index.html", items=[visible_item(row) for row in rows], stats=stats(), search=search, status=status)


@app.route("/items/new", methods=["GET", "POST"])
def new_item():
    if request.method == "POST":
        data = item_from_form()
        errors = validate_item_data(data)
        if errors:
            for error in errors:
                flash(error, "warning")
            return render_template("item_form.html", item=data, mode="create")
        db = get_db()
        columns = ", ".join(data.keys()) + ", created_by, created_at, updated_by, updated_at"
        placeholders = ", ".join(["?"] * (len(data) + 4))
        values = list(data.values()) + [current_actor(), now_iso(), current_actor(), now_iso()]
        cursor = db.execute(f"INSERT INTO procurement_items ({columns}) VALUES ({placeholders})", values)
        item_id = cursor.lastrowid
        db.commit()
        sync_timeline_events(item_id, data, current_actor())
        audit_log(current_actor(), current_role(), "create_item", "procurement_item", item_id, f"Created {data['item_name']}", data)
        flash("Procurement item created.", "success")
        return redirect(url_for("item_detail", item_id=item_id))
    return render_template("item_form.html", item=None, mode="create")


@app.route("/items/<int:item_id>")
def item_detail(item_id):
    row = get_db().execute("SELECT * FROM procurement_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        flash("Item not found.", "warning")
        return redirect(url_for("index"))
    events = get_db().execute(
        "SELECT * FROM timeline_events WHERE item_id = ? ORDER BY COALESCE(event_date, created_at), created_at",
        (item_id,),
    ).fetchall()
    return render_template("item_detail.html", item=visible_item(row), events=events)


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@manager_required
def edit_item(item_id):
    db = get_db()
    row = db.execute("SELECT * FROM procurement_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        flash("Item not found.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        data = item_from_form(row)
        errors = validate_item_data(data)
        if errors:
            for error in errors:
                flash(error, "warning")
            return render_template("item_form.html", item=merge_item_for_form(row, data), mode="edit")
        changes = changes_between(row, data)
        assignments = ", ".join([f"{field} = ?" for field in data.keys()])
        values = list(data.values()) + [current_actor(), now_iso(), item_id]
        db.execute(
            f"UPDATE procurement_items SET {assignments}, updated_by = ?, updated_at = ? WHERE id = ?",
            values,
        )
        db.commit()
        sync_timeline_events(item_id, data, current_actor())
        add_update_event(item_id, changes, current_actor())
        audit_log(current_actor(), current_role(), "update_item", "procurement_item", item_id, f"Updated {data['item_name']}", changes)
        flash("Procurement item updated.", "success")
        return redirect(url_for("item_detail", item_id=item_id))
    return render_template("item_form.html", item=dict(row), mode="edit")


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@manager_required
def delete_item(item_id):
    db = get_db()
    row = db.execute("SELECT * FROM procurement_items WHERE id = ?", (item_id,)).fetchone()
    if row:
        db.execute("DELETE FROM procurement_items WHERE id = ?", (item_id,))
        db.commit()
        audit_log(current_actor(), current_role(), "delete_item", "procurement_item", item_id, f"Deleted {row['item_name']}", dict(row))
        flash("Procurement item deleted.", "success")
    return redirect(url_for("index"))


@app.route("/items/<int:item_id>/events", methods=["POST"])
@manager_required
def add_event(item_id):
    row = get_db().execute("SELECT id FROM procurement_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        flash("Item not found.", "warning")
        return redirect(url_for("index"))

    title = form_value("title") or "Timeline event"
    event_date = form_value("event_date")
    details = form_value("details")
    get_db().execute(
        """
        INSERT INTO timeline_events
            (item_id, event_type, title, event_date, details, created_by, created_at)
        VALUES (?, 'custom', ?, ?, ?, ?, ?)
        """,
        (item_id, title, event_date, details, current_actor(), now_iso()),
    )
    get_db().commit()
    audit_log(current_actor(), current_role(), "create_timeline_event", "procurement_item", item_id, title, {"event_date": event_date, "details": details})
    flash("Timeline event added.", "success")
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = form_value("username", "")
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? AND active = 1",
            (username,),
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["username"] = user["username"]
            session["role"] = user["role"]
            audit_log(user["username"], user["role"], "login_success", "session", None, "Manager login successful")
            return redirect(url_for("index"))
        audit_log(username or "unknown", "unknown", "login_failed", "session", None, "Login failed")
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    actor = current_actor()
    role = current_role()
    session.clear()
    audit_log(actor, role, "logout", "session", None, "User logged out")
    flash("Returned to viewer mode.", "success")
    return redirect(url_for("index"))


@app.route("/users", methods=["GET", "POST"])
@manager_required
def users():
    db = get_db()
    if request.method == "POST":
        username = form_value("username", "")
        password = request.form.get("password", "")
        role = form_value("role", "manager")
        if not username or not password:
            flash("Username and password are required.", "warning")
        else:
            try:
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, role, active, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (username, generate_password_hash(password), role, now_iso()),
                )
                db.commit()
                audit_log(current_actor(), current_role(), "create_user", "user", username, f"Created user {username}", {"role": role})
                flash("User created.", "success")
            except sqlite3.IntegrityError:
                flash("Username already exists.", "warning")
    user_rows = db.execute("SELECT id, username, role, active, created_at FROM users ORDER BY username").fetchall()
    return render_template("users.html", users=user_rows)


@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@manager_required
def toggle_user(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row:
        active = 0 if row["active"] else 1
        db.execute("UPDATE users SET active = ? WHERE id = ?", (active, user_id))
        db.commit()
        audit_log(current_actor(), current_role(), "toggle_user", "user", row["username"], f"Set active={active}", {"active": active})
    return redirect(url_for("users"))


@app.route("/audit")
@manager_required
def audit():
    rows = get_db().execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 300").fetchall()
    return render_template("audit.html", logs=rows)


@app.route("/settings", methods=["GET", "POST"])
@manager_required
def settings():
    if request.method == "POST":
        target = backup_database("manual", current_actor())
        flash(f"Backup created: {target.name}", "success")
        return redirect(url_for("settings"))
    backups = get_db().execute("SELECT * FROM backups ORDER BY created_at DESC").fetchall()
    return render_template("settings.html", backups=backups, backup_dir=BACKUP_DIR)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
