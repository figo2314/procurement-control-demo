import configparser
import json
import os
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "procurement.sqlite3"
CONFIG_PATH = BASE_DIR / "config.ini"

APP_FIELDS = [
    "mms_no",
    "item_name",
    "quantity",
    "price",
    "currency",
    "requester",
    "request_date",
    "owner",
    "priority",
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
PRIORITY_OPTIONS = ["Normal", "Urgent", "Critical"]


app = Flask(__name__)
app.secret_key = os.environ.get("PROCUREMENT_SECRET", "demo-secret-change-me")


EMBEDDED_STYLES = ':root {\n    --bg: #f6f7f9;\n    --panel: #ffffff;\n    --text: #18202b;\n    --muted: #6b7280;\n    --line: #e3e7ee;\n    --accent: #176b87;\n    --accent-strong: #0f5268;\n    --good: #176f4d;\n    --warn: #a75d12;\n    --danger: #b42318;\n    --shadow: 0 16px 40px rgba(21, 31, 46, 0.08);\n}\n\n* {\n    box-sizing: border-box;\n}\n\nbody {\n    margin: 0;\n    background: var(--bg);\n    color: var(--text);\n    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;\n    font-size: 14px;\n}\n\na {\n    color: inherit;\n    text-decoration: none;\n}\n\nbutton,\ninput,\nselect,\ntextarea {\n    font: inherit;\n}\n\n.topbar {\n    position: sticky;\n    top: 0;\n    z-index: 10;\n    display: flex;\n    align-items: center;\n    gap: 24px;\n    min-height: 68px;\n    padding: 0 28px;\n    background: rgba(255, 255, 255, 0.94);\n    border-bottom: 1px solid var(--line);\n    backdrop-filter: blur(12px);\n}\n\n.brand {\n    display: flex;\n    align-items: center;\n    gap: 12px;\n    min-width: 260px;\n}\n\n.brand-mark {\n    display: grid;\n    place-items: center;\n    width: 38px;\n    height: 38px;\n    border-radius: 8px;\n    background: #12313e;\n    color: #fff;\n    font-weight: 700;\n}\n\n.brand strong,\n.brand small {\n    display: block;\n}\n\n.brand small {\n    margin-top: 2px;\n    color: var(--muted);\n    font-size: 12px;\n}\n\n.nav {\n    display: flex;\n    align-items: center;\n    gap: 6px;\n    flex: 1;\n}\n\n.nav a,\n.ghost-button,\n.ghost-link {\n    color: var(--muted);\n    border: 0;\n    background: transparent;\n    padding: 9px 11px;\n    border-radius: 7px;\n    cursor: pointer;\n}\n\n.nav a:hover,\n.ghost-button:hover,\n.ghost-link:hover {\n    background: #eef2f6;\n    color: var(--text);\n}\n\n.mode-panel,\n.action-row,\n.filter-form,\n.toolbar {\n    display: flex;\n    align-items: center;\n    gap: 10px;\n}\n\n.role-badge {\n    display: inline-flex;\n    align-items: center;\n    height: 30px;\n    padding: 0 10px;\n    border: 1px solid var(--line);\n    border-radius: 999px;\n    font-size: 12px;\n    font-weight: 700;\n}\n\n.role-badge.manager {\n    color: var(--accent-strong);\n    background: #e8f3f6;\n    border-color: #b9dbe4;\n}\n\n.role-badge.viewer {\n    color: #495261;\n    background: #f3f5f7;\n}\n\n.page {\n    max-width: 1440px;\n    margin: 0 auto;\n    padding: 28px;\n}\n\n.page-heading {\n    display: flex;\n    align-items: flex-end;\n    justify-content: space-between;\n    gap: 20px;\n    margin-bottom: 22px;\n}\n\n.eyebrow {\n    margin: 0 0 8px;\n    color: var(--accent);\n    font-size: 12px;\n    font-weight: 700;\n    text-transform: uppercase;\n}\n\nh1,\nh2,\nh3,\np {\n    margin-top: 0;\n}\n\nh1 {\n    margin-bottom: 0;\n    font-size: 30px;\n    font-weight: 680;\n}\n\nh2 {\n    font-size: 18px;\n}\n\nh3 {\n    font-size: 15px;\n}\n\n.stats-grid {\n    display: grid;\n    grid-template-columns: repeat(6, minmax(150px, 1fr));\n    gap: 12px;\n    margin-bottom: 18px;\n}\n\n.stat {\n    color: inherit;\n    min-height: 92px;\n    padding: 18px;\n    background: var(--panel);\n    border: 1px solid var(--line);\n    border-radius: 8px;\n}\n\n.stat.active,\n.stat:hover {\n    border-color: #9ccbd8;\n    background: #f2fafc;\n}\n\n.stat span {\n    display: block;\n    color: var(--muted);\n    font-size: 12px;\n}\n\n.stat strong {\n    display: block;\n    margin-top: 12px;\n    font-size: 28px;\n}\n\n.stat.risk strong {\n    color: var(--warn);\n}\n\n.stat.value strong {\n    color: var(--accent-strong);\n}\n\n.toolbar,\n.table-shell,\n.detail-panel,\n.timeline-panel,\n.form-panel,\n.login-panel {\n    background: var(--panel);\n    border: 1px solid var(--line);\n    border-radius: 8px;\n    box-shadow: var(--shadow);\n}\n\n.toolbar {\n    padding: 14px;\n    margin-bottom: 14px;\n    justify-content: space-between;\n}\n\n.filter-form {\n    flex: 1;\n    min-width: 0;\n}\n\n.filter-form input {\n    flex: 1;\n    min-width: 360px;\n}\n\n.filter-form select {\n    flex: 0 0 190px;\n}\n\ninput,\nselect,\ntextarea {\n    width: 100%;\n    min-height: 40px;\n    padding: 9px 11px;\n    color: var(--text);\n    background: #fff;\n    border: 1px solid #ccd3dd;\n    border-radius: 7px;\n    outline: none;\n}\n\ntextarea {\n    resize: vertical;\n}\n\ninput:focus,\nselect:focus,\ntextarea:focus {\n    border-color: var(--accent);\n    box-shadow: 0 0 0 3px rgba(23, 107, 135, 0.14);\n}\n\n.primary-button,\n.secondary-button,\n.danger-button {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    min-height: 40px;\n    padding: 0 14px;\n    border-radius: 7px;\n    border: 1px solid transparent;\n    font-weight: 650;\n    cursor: pointer;\n}\n\n.primary-button {\n    background: var(--accent);\n    color: #fff;\n}\n\n.primary-button:hover {\n    background: var(--accent-strong);\n}\n\n.secondary-button {\n    background: #fff;\n    color: var(--text);\n    border-color: #cfd6df;\n}\n\n.secondary-button:hover {\n    background: #f1f4f7;\n}\n\n.danger-button {\n    background: #fff;\n    color: var(--danger);\n    border-color: #e5b7b3;\n}\n\n.danger-button:hover {\n    background: #fff1f0;\n}\n\n.compact {\n    min-height: 32px;\n    padding: 0 10px;\n    font-size: 13px;\n}\n\n.full {\n    width: 100%;\n}\n\n.table-shell {\n    overflow: auto;\n}\n\n.data-table {\n    width: 100%;\n    border-collapse: collapse;\n    min-width: 980px;\n}\n\n.data-table th,\n.data-table td {\n    padding: 14px 15px;\n    border-bottom: 1px solid var(--line);\n    text-align: left;\n    vertical-align: top;\n}\n\n.data-table th {\n    color: var(--muted);\n    background: #fbfcfd;\n    font-size: 12px;\n    font-weight: 700;\n    text-transform: uppercase;\n}\n\n.data-table tbody tr {\n    transition: background 0.16s ease;\n}\n\n.data-table tbody tr:hover {\n    background: #f5f8fa;\n}\n\n.data-table tbody tr[onclick] {\n    cursor: pointer;\n}\n\n.item-title,\n.data-table small {\n    display: block;\n}\n\n.data-table small {\n    margin-top: 4px;\n    color: var(--muted);\n}\n\n.pill,\n.status,\n.priority {\n    display: inline-flex;\n    align-items: center;\n    min-height: 24px;\n    padding: 0 9px;\n    border-radius: 999px;\n    font-size: 12px;\n    font-weight: 650;\n}\n\n.pill.ok {\n    color: var(--good);\n    background: #eaf7f0;\n}\n\n.pill.muted,\n.status {\n    color: #4b5563;\n    background: #eef2f6;\n}\n\n.status-draft {\n    color: #526071;\n    background: #eef2f6;\n}\n\n.status-pr-created {\n    color: #7a4d00;\n    background: #fff3cf;\n}\n\n.status-po-created {\n    color: #245a8d;\n    background: #e8f2fb;\n}\n\n.status-ordered {\n    color: #0f5268;\n    background: #e3f2f6;\n}\n\n.status-partially-received {\n    color: #7a4d00;\n    background: #fff3cf;\n}\n\n.status-received {\n    color: var(--good);\n    background: #eaf7f0;\n}\n\n.status-delayed {\n    color: var(--danger);\n    background: #fff0ef;\n}\n\n.priority-normal {\n    color: #4b5563;\n    background: #eef2f6;\n}\n\n.priority-urgent {\n    color: #7a4d00;\n    background: #fff3cf;\n}\n\n.priority-critical {\n    color: var(--danger);\n    background: #fff0ef;\n}\n\n.detail-grid,\n.settings-grid,\n.split-layout {\n    display: grid;\n    grid-template-columns: minmax(320px, 0.8fr) minmax(480px, 1.2fr);\n    gap: 18px;\n    align-items: start;\n}\n\n.detail-panel,\n.timeline-panel,\n.form-panel,\n.login-panel {\n    padding: 22px;\n}\n\n.details {\n    display: grid;\n    grid-template-columns: repeat(2, minmax(0, 1fr));\n    gap: 14px 22px;\n    margin: 0;\n}\n\n.details div {\n    min-width: 0;\n}\n\n.details dt {\n    color: var(--muted);\n    font-size: 12px;\n    font-weight: 700;\n    text-transform: uppercase;\n}\n\n.details dd {\n    margin: 5px 0 0;\n    overflow-wrap: anywhere;\n}\n\n.compact-details {\n    grid-template-columns: 1fr;\n}\n\n.notes {\n    margin-top: 22px;\n    padding-top: 18px;\n    border-top: 1px solid var(--line);\n}\n\n.notes p,\n.plain-text {\n    color: var(--muted);\n    line-height: 1.6;\n}\n\n.timeline {\n    position: relative;\n    list-style: none;\n    margin: 0;\n    padding: 0 0 0 4px;\n}\n\n.timeline li {\n    position: relative;\n    display: flex;\n    gap: 14px;\n    padding: 0 0 20px;\n}\n\n.timeline li::before {\n    content: "";\n    position: absolute;\n    left: 7px;\n    top: 15px;\n    bottom: 0;\n    width: 1px;\n    background: var(--line);\n}\n\n.timeline li:last-child::before {\n    display: none;\n}\n\n.dot {\n    flex: 0 0 auto;\n    width: 15px;\n    height: 15px;\n    margin-top: 4px;\n    border: 3px solid #cae3ea;\n    border-radius: 50%;\n    background: var(--accent);\n}\n\n.timeline time {\n    display: block;\n    color: var(--muted);\n    font-size: 12px;\n    font-weight: 700;\n}\n\n.timeline strong {\n    display: block;\n    margin-top: 3px;\n}\n\n.timeline p {\n    margin: 6px 0;\n    color: var(--muted);\n    line-height: 1.45;\n}\n\n.timeline small {\n    color: #8b94a2;\n}\n\n.event-form {\n    margin-top: 20px;\n    padding-top: 18px;\n    border-top: 1px solid var(--line);\n}\n\n.form-panel {\n    max-width: 980px;\n}\n\n.form-panel.slim {\n    max-width: none;\n}\n\n.form-grid {\n    display: grid;\n    grid-template-columns: repeat(3, minmax(0, 1fr));\n    gap: 16px;\n}\n\nlabel {\n    display: grid;\n    gap: 7px;\n    color: #3e4653;\n    font-size: 13px;\n    font-weight: 650;\n}\n\n.checkbox-row {\n    display: flex;\n    align-items: center;\n    gap: 10px;\n    margin: 18px 0;\n}\n\n.checkbox-row input {\n    width: 18px;\n    min-height: 18px;\n}\n\n.privacy-note {\n    margin: 16px 0;\n    padding: 12px 14px;\n    color: #495261;\n    background: #f3f6f8;\n    border: 1px solid var(--line);\n    border-radius: 8px;\n}\n\n.login-shell {\n    display: grid;\n    place-items: center;\n    min-height: calc(100vh - 160px);\n}\n\n.login-panel {\n    width: min(420px, 100%);\n}\n\n.login-panel h1 {\n    margin-bottom: 20px;\n}\n\n.login-panel label {\n    margin-bottom: 14px;\n}\n\n.hint {\n    margin: 14px 0 0;\n    color: var(--muted);\n    font-size: 12px;\n}\n\n.grow {\n    min-width: 0;\n}\n\n.audit-table {\n    min-width: 1160px;\n}\n\ndetails {\n    margin-top: 6px;\n}\n\npre {\n    max-width: 520px;\n    white-space: pre-wrap;\n    overflow-wrap: anywhere;\n    padding: 10px;\n    background: #f4f6f8;\n    border-radius: 7px;\n}\n\n.flash-stack {\n    display: grid;\n    gap: 8px;\n    margin-bottom: 16px;\n}\n\n.flash {\n    padding: 12px 14px;\n    border-radius: 8px;\n    border: 1px solid var(--line);\n    background: #fff;\n}\n\n.flash.success {\n    color: var(--good);\n    border-color: #bfe3cf;\n    background: #eff9f3;\n}\n\n.flash.warning {\n    color: var(--warn);\n    border-color: #eed0a9;\n    background: #fff8ed;\n}\n\n.flash.danger {\n    color: var(--danger);\n    border-color: #efc2bf;\n    background: #fff3f2;\n}\n\n.empty,\n.empty-line {\n    color: var(--muted);\n    text-align: center;\n}\n\n@media (max-width: 1100px) {\n    .topbar {\n        flex-wrap: wrap;\n        padding: 14px 18px;\n    }\n\n    .brand {\n        min-width: 0;\n    }\n\n    .stats-grid {\n        grid-template-columns: repeat(3, 1fr);\n    }\n\n    .detail-grid,\n    .settings-grid,\n    .split-layout {\n        grid-template-columns: 1fr;\n    }\n}\n\n@media (max-width: 760px) {\n    .page {\n        padding: 18px;\n    }\n\n    .page-heading,\n    .filter-form,\n    .toolbar,\n    .mode-panel {\n        align-items: stretch;\n        flex-direction: column;\n    }\n\n    .filter-form input,\n    .filter-form select {\n        min-width: 0;\n        flex-basis: auto;\n    }\n\n    .nav {\n        order: 3;\n        width: 100%;\n        overflow-x: auto;\n    }\n\n    .stats-grid,\n    .form-grid,\n    .details {\n        grid-template-columns: 1fr;\n    }\n\n    h1 {\n        font-size: 24px;\n    }\n}\n'

EMBEDDED_TEMPLATES = {'audit.html': '{% extends "base.html" %}\n{% block title %}Audit Log - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="page-heading">\n    <div>\n        <p class="eyebrow">Traceability</p>\n        <h1>Audit log</h1>\n    </div>\n</section>\n\n<section class="table-shell">\n    <table class="data-table audit-table">\n        <thead>\n            <tr>\n                <th>Time</th>\n                <th>Actor</th>\n                <th>Role</th>\n                <th>Action</th>\n                <th>Target</th>\n                <th>Summary</th>\n                <th>IP</th>\n            </tr>\n        </thead>\n        <tbody>\n            {% for log in logs %}\n                <tr>\n                    <td>{{ log.created_at }}</td>\n                    <td><strong>{{ log.actor }}</strong></td>\n                    <td>{{ log.role }}</td>\n                    <td><span class="status">{{ log.action }}</span></td>\n                    <td>{{ log.target_type }} {{ log.target_id or "" }}</td>\n                    <td>\n                        {{ log.summary or "-" }}\n                        {% if log.changes %}\n                            <details>\n                                <summary>Changes</summary>\n                                <pre>{{ log.changes }}</pre>\n                            </details>\n                        {% endif %}\n                    </td>\n                    <td>{{ log.ip_address or "-" }}</td>\n                </tr>\n            {% else %}\n                <tr><td colspan="7" class="empty">No audit records yet.</td></tr>\n            {% endfor %}\n        </tbody>\n    </table>\n</section>\n{% endblock %}\n', 'base.html': '<!doctype html>\n<html lang="en">\n<head>\n    <meta charset="utf-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1">\n    <title>{% block title %}Procurement Control{% endblock %}</title>\n    <link rel="stylesheet" href="{{ url_for(\'styles\') }}">\n</head>\n<body>\n    <header class="topbar">\n        <a class="brand" href="{{ url_for(\'index\') }}">\n            <span class="brand-mark">PC</span>\n            <span>\n                <strong>Procurement Control</strong>\n                <small>Engineering Materials</small>\n            </span>\n        </a>\n        <nav class="nav">\n            <a href="{{ url_for(\'index\') }}">Dashboard</a>\n            <a href="{{ url_for(\'new_item\') }}">New Request</a>\n            {% if is_manager %}\n                <a href="{{ url_for(\'audit\') }}">Audit Log</a>\n                <a href="{{ url_for(\'users\') }}">Users</a>\n                <a href="{{ url_for(\'settings\') }}">Settings</a>\n            {% endif %}\n        </nav>\n        <div class="mode-panel">\n            <span class="role-badge {{ current_role }}">{{ current_role|upper }}</span>\n            {% if is_manager %}\n                <form action="{{ url_for(\'logout\') }}" method="post">\n                    <button class="ghost-button" type="submit">Exit Manager</button>\n                </form>\n            {% else %}\n                <a class="primary-button compact" href="{{ url_for(\'login\') }}">Manager Login</a>\n            {% endif %}\n        </div>\n    </header>\n\n    <main class="page">\n        {% with messages = get_flashed_messages(with_categories=true) %}\n            {% if messages %}\n                <div class="flash-stack">\n                    {% for category, message in messages %}\n                        <div class="flash {{ category }}">{{ message }}</div>\n                    {% endfor %}\n                </div>\n            {% endif %}\n        {% endwith %}\n        {% block content %}{% endblock %}\n    </main>\n</body>\n</html>\n', 'index.html': '{% extends "base.html" %}\n{% block title %}Dashboard - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="stats-grid">\n    <a class="stat {% if not quick %}active{% endif %}" href="{{ url_for(\'index\') }}">\n        <span>Total Items</span>\n        <strong>{{ stats.total }}</strong>\n    </a>\n    <a class="stat {% if quick == \'pending\' %}active{% endif %}" href="{{ url_for(\'index\', quick=\'pending\') }}">\n        <span>Pending Arrival</span>\n        <strong>{{ stats.pending }}</strong>\n    </a>\n    <a class="stat {% if quick == \'received\' %}active{% endif %}" href="{{ url_for(\'index\', quick=\'received\') }}">\n        <span>Received</span>\n        <strong>{{ stats.received }}</strong>\n    </a>\n    <a class="stat risk {% if quick == \'late\' %}active{% endif %}" href="{{ url_for(\'index\', quick=\'late\') }}">\n        <span>Late Arrival</span>\n        <strong>{{ stats.delayed }}</strong>\n    </a>\n    <a class="stat {% if quick == \'open-pr\' %}active{% endif %}" href="{{ url_for(\'index\', quick=\'open-pr\') }}">\n        <span>Open PR / No PO</span>\n        <strong>{{ stats.pending_pr }}</strong>\n    </a>\n    {% if is_manager %}\n        <div class="stat value">\n            <span>Total Value</span>\n            <strong>{{ "%.2f"|format(stats.total_value) }}</strong>\n        </div>\n    {% endif %}\n</section>\n\n<section class="toolbar">\n    <form class="filter-form" id="global-search-form" action="{{ url_for(\'index\') }}" method="get">\n        {% if quick %}<input type="hidden" name="quick" value="{{ quick }}">{% endif %}\n        <input name="q" value="{{ search }}" placeholder="Search MMS, item, requester, supplier, department">\n        <select name="status">\n            <option value="">All status</option>\n            {% for option in status_options %}\n                <option value="{{ option }}" {% if status == option %}selected{% endif %}>{{ option }}</option>\n            {% endfor %}\n        </select>\n        <button class="secondary-button" type="submit">Filter</button>\n    </form>\n    <a class="primary-button" href="{{ url_for(\'new_item\') }}">New Request</a>\n</section>\n\n<section class="table-shell">\n    <table class="data-table">\n        <thead>\n            <tr>\n                <th>MMS No.</th>\n                <th>Item</th>\n                <th>Qty</th>\n                {% if is_manager %}<th>Price</th>{% endif %}\n                <th>Priority</th>\n                <th>Requester</th>\n                <th>Owner</th>\n                <th>PR Created</th>\n                <th>PO Created</th>\n                <th>Purchase Date</th>\n                <th>Received</th>\n                <th>Status</th>\n            </tr>\n        </thead>\n        <tbody>\n            {% for item in items %}\n                <tr onclick="window.location=\'{{ url_for(\'item_detail\', item_id=item.id) }}\'">\n                    <td><strong>{{ item.mms_no or "-" }}</strong></td>\n                    <td>\n                        <span class="item-title">{{ item.item_name }}</span>\n                        <small>{{ item.supplier or "Supplier not set" }}</small>\n                    </td>\n                    <td>{{ item.quantity|int if item.quantity is not none else "-" }}</td>\n                    {% if is_manager %}\n                        <td>{{ item.currency or "" }} {{ "%.2f"|format(item.price or 0) }}</td>\n                    {% endif %}\n                    <td><span class="priority priority-{{ item.priority|lower }}">{{ item.priority or "Normal" }}</span></td>\n                    <td>\n                        <span class="item-title">{{ item.requester or "-" }}</span>\n                        <small>Request Date: {{ item.request_date or "-" }}</small>\n                    </td>\n                    <td>{{ item.owner or "-" }}</td>\n                    <td>{{ item.pr_created_at or "-" }}</td>\n                    <td>{{ item.po_created_at or "-" }}</td>\n                    <td>{{ item.purchase_date or "-" }}</td>\n                    <td>\n                        {% if item.received %}\n                            <span class="pill ok">Yes</span>\n                        {% else %}\n                            <span class="pill muted">No</span>\n                        {% endif %}\n                    </td>\n                    <td><span class="status status-{{ item.status|lower|replace(\' \', \'-\') }}">{{ item.status }}</span></td>\n                </tr>\n            {% else %}\n                <tr>\n                    <td colspan="12" class="empty">No procurement records found.</td>\n                </tr>\n            {% endfor %}\n        </tbody>\n    </table>\n</section>\n<script>\n    const searchForm = document.getElementById("global-search-form");\n    const searchInput = searchForm?.querySelector("input[name=\'q\']");\n    const statusSelect = searchForm?.querySelector("select[name=\'status\']");\n    let searchTimer;\n\n    function submitWithDebounce() {\n        clearTimeout(searchTimer);\n        searchTimer = setTimeout(() => searchForm.requestSubmit(), 450);\n    }\n\n    searchInput?.addEventListener("input", submitWithDebounce);\n    statusSelect?.addEventListener("change", () => searchForm.requestSubmit());\n</script>\n{% endblock %}\n', 'item_detail.html': '{% extends "base.html" %}\n{% block title %}{{ item.item_name }} - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="page-heading">\n    <div>\n        <p class="eyebrow">{{ item.mms_no or "No MMS number" }}</p>\n        <h1>{{ item.item_name }}</h1>\n    </div>\n    <div class="action-row">\n        {% if is_manager %}\n            <a class="secondary-button" href="{{ url_for(\'edit_item\', item_id=item.id) }}">Edit</a>\n            <form action="{{ url_for(\'delete_item\', item_id=item.id) }}" method="post" onsubmit="return confirm(\'Delete this procurement item?\');">\n                <button class="danger-button" type="submit">Delete</button>\n            </form>\n        {% endif %}\n        <a class="ghost-link" href="{{ url_for(\'index\') }}">Back</a>\n    </div>\n</section>\n\n<section class="detail-grid">\n    <div class="detail-panel">\n        <h2>Record</h2>\n        <dl class="details">\n            <div><dt>Quantity</dt><dd>{{ item.quantity|int if item.quantity is not none else "-" }}</dd></div>\n            {% if is_manager %}\n                <div><dt>Price</dt><dd>{{ item.currency or "" }} {{ "%.2f"|format(item.price or 0) }}</dd></div>\n            {% endif %}\n            <div><dt>Requester</dt><dd>{{ item.requester or "-" }}</dd></div>\n            <div><dt>Request Date</dt><dd>{{ item.request_date or "-" }}</dd></div>\n            <div><dt>Owner</dt><dd>{{ item.owner or "-" }}</dd></div>\n            <div><dt>Priority</dt><dd><span class="priority priority-{{ item.priority|lower }}">{{ item.priority or "Normal" }}</span></dd></div>\n            <div><dt>Department</dt><dd>{{ item.department or "-" }}</dd></div>\n            <div><dt>Supplier</dt><dd>{{ item.supplier or "-" }}</dd></div>\n            <div><dt>Status</dt><dd><span class="status status-{{ item.status|lower|replace(\' \', \'-\') }}">{{ item.status }}</span></dd></div>\n            <div><dt>Received</dt><dd>{{ "Yes" if item.received else "No" }}</dd></div>\n            <div><dt>Purchase Date</dt><dd>{{ item.purchase_date or "-" }}</dd></div>\n            <div><dt>PR Created</dt><dd>{{ item.pr_created_at or "-" }}</dd></div>\n            <div><dt>PO Created</dt><dd>{{ item.po_created_at or "-" }}</dd></div>\n            <div><dt>Expected Arrival</dt><dd>{{ item.expected_arrival_date or "-" }}</dd></div>\n            <div><dt>Arrival Date</dt><dd>{{ item.arrival_date or "-" }}</dd></div>\n        </dl>\n        {% if item.notes %}\n            <div class="notes">\n                <strong>Notes</strong>\n                <p>{{ item.notes }}</p>\n            </div>\n        {% endif %}\n    </div>\n\n    <div class="timeline-panel">\n        <h2>Timeline</h2>\n        <ol class="timeline">\n            {% for event in events %}\n                <li>\n                    <span class="dot"></span>\n                    <div>\n                        <time>{{ event.event_date or event.created_at[:10] }}</time>\n                        <strong>{{ event.title }}</strong>\n                        {% if event.details %}<p>{{ event.details }}</p>{% endif %}\n                        <small>By {{ event.created_by or "system" }} - {{ event.created_at }}</small>\n                    </div>\n                </li>\n            {% else %}\n                <li class="empty-line">No timeline events yet.</li>\n            {% endfor %}\n        </ol>\n\n        {% if is_manager %}\n            <form class="event-form" action="{{ url_for(\'add_event\', item_id=item.id) }}" method="post">\n                <h3>Add timeline event</h3>\n                <div class="form-grid">\n                    <label>Title\n                        <input name="title" placeholder="Supplier confirmed delivery">\n                    </label>\n                    <label>Date\n                        <input type="date" name="event_date">\n                    </label>\n                </div>\n                <label>Details\n                    <textarea name="details" rows="3" placeholder="Add a concise operational note"></textarea>\n                </label>\n                <button class="secondary-button" type="submit">Add Event</button>\n            </form>\n        {% endif %}\n    </div>\n</section>\n{% endblock %}\n\n', 'item_form.html': '{% extends "base.html" %}\n{% block title %}{{ "Edit" if mode == "edit" else "New Request" }} - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="page-heading">\n    <div>\n        <p class="eyebrow">{{ "Manager maintenance" if mode == "edit" else "Procurement intake" }}</p>\n        <h1>{{ "Edit procurement item" if mode == "edit" else "New procurement request" }}</h1>\n    </div>\n    <a class="ghost-link" href="{{ url_for(\'index\') }}">Back</a>\n</section>\n\n<form class="form-panel" method="post">\n    <div class="form-grid">\n        <label>MMS No.\n            <input name="mms_no" inputmode="numeric" pattern="[0-9]*" value="{{ item.mms_no if item else \'\' }}" placeholder="2406004">\n        </label>\n        <label>Item Name *\n            <input name="item_name" required value="{{ item.item_name if item else \'\' }}" placeholder="Material or spare part name">\n        </label>\n        <label>Quantity\n            <input name="quantity" type="number" step="1" min="0" value="{{ item.quantity|int if item and item.quantity is not none else \'\' }}">\n        </label>\n        {% if is_manager %}\n            <label>Price\n                <input name="price" type="number" step="0.01" value="{{ item.price if item and item.price is not none else \'\' }}">\n            </label>\n            <label>Currency\n                <select name="currency">\n                    {% set selected_currency = item.currency if item and item.currency else "MOP" %}\n                    {% for currency in currency_options %}\n                        <option value="{{ currency }}" {% if selected_currency == currency %}selected{% endif %}>{{ currency }}</option>\n                    {% endfor %}\n                </select>\n            </label>\n        {% endif %}\n        <label>Requester\n            <input name="requester" value="{{ item.requester if item else \'\' }}" placeholder="Person who placed the request">\n        </label>\n        <label>Request Date\n            <input type="date" name="request_date" value="{{ item.request_date if item else \'\' }}">\n        </label>\n        <label>Owner\n            <input name="owner" value="{{ item.owner if item else \'\' }}" placeholder="Person responsible for follow-up">\n        </label>\n        <label>Priority\n            <select name="priority">\n                {% set selected_priority = item.priority if item and item.priority else "Normal" %}\n                {% for priority in priority_options %}\n                    <option value="{{ priority }}" {% if selected_priority == priority %}selected{% endif %}>{{ priority }}</option>\n                {% endfor %}\n            </select>\n        </label>\n        <label>Department\n            <input name="department" value="{{ item.department if item else \'\' }}" placeholder="Engineering, Maintenance, EHS">\n        </label>\n        <label>Supplier\n            <input name="supplier" value="{{ item.supplier if item else \'\' }}" placeholder="Supplier name">\n        </label>\n        <label>Purchase Date\n            <input type="date" name="purchase_date" value="{{ item.purchase_date if item else \'\' }}">\n        </label>\n        <label>PR Created\n            <input type="date" name="pr_created_at" value="{{ item.pr_created_at if item else \'\' }}">\n        </label>\n        <label>PO Created\n            <input type="date" name="po_created_at" value="{{ item.po_created_at if item else \'\' }}">\n        </label>\n        <label>Expected Arrival\n            <input type="date" name="expected_arrival_date" value="{{ item.expected_arrival_date if item else \'\' }}">\n        </label>\n        <label>Arrival Date\n            <input type="date" name="arrival_date" value="{{ item.arrival_date if item else \'\' }}">\n        </label>\n        <label>Status\n            <select name="status">\n                {% for option in status_options %}\n                    <option value="{{ option }}" {% if item and item.status == option %}selected{% endif %}>{{ option }}</option>\n                {% endfor %}\n            </select>\n        </label>\n    </div>\n\n    <label class="checkbox-row">\n        <input type="checkbox" name="received" {% if item and item.received %}checked{% endif %}>\n        <span>Goods have arrived</span>\n    </label>\n\n    <label>Notes\n        <textarea name="notes" rows="4" placeholder="Operational note, quotation status, delivery risk, or handover detail">{{ item.notes if item else \'\' }}</textarea>\n    </label>\n\n    {% if not is_manager %}\n        <div class="privacy-note">Viewer mode can create requests, but commercial fields are hidden and can only be maintained by a manager.</div>\n    {% endif %}\n\n    <div class="action-row">\n        <button class="primary-button" type="submit">{{ "Save Changes" if mode == "edit" else "Create Request" }}</button>\n        <a class="ghost-link" href="{{ url_for(\'index\') }}">Cancel</a>\n    </div>\n</form>\n{% endblock %}\n', 'login.html': '{% extends "base.html" %}\n{% block title %}Manager Login - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="login-shell">\n    <form class="login-panel" method="post">\n        <p class="eyebrow">Secure access</p>\n        <h1>Manager login</h1>\n        <label>Username\n            <input name="username" autocomplete="username" required>\n        </label>\n        <label>Password\n            <input name="password" type="password" autocomplete="current-password" required>\n        </label>\n        <button class="primary-button full" type="submit">Enable Manager Mode</button>\n        <p class="hint">Demo admin: admin / admin123</p>\n    </form>\n</section>\n{% endblock %}\n', 'settings.html': '{% extends "base.html" %}\n{% block title %}Settings - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="page-heading">\n    <div>\n        <p class="eyebrow">Data protection</p>\n        <h1>Settings and backups</h1>\n    </div>\n    <form method="post">\n        <button class="primary-button" type="submit">Create Manual Backup</button>\n    </form>\n</section>\n\n<section class="settings-grid">\n    <div class="detail-panel">\n        <h2>Backup policy</h2>\n        <p class="plain-text">The application creates one automatic database backup per day when it is opened. Manual backups are available here and every backup is recorded in the audit log.</p>\n        <dl class="details compact-details">\n            <div><dt>Database</dt><dd>data/procurement.sqlite3</dd></div>\n            <div><dt>Backup folder</dt><dd>{{ backup_dir }}</dd></div>\n        </dl>\n    </div>\n\n    <section class="table-shell">\n        <table class="data-table">\n            <thead>\n                <tr>\n                    <th>File</th>\n                    <th>Reason</th>\n                    <th>Actor</th>\n                    <th>Created</th>\n                </tr>\n            </thead>\n            <tbody>\n                {% for backup in backups %}\n                    <tr>\n                        <td><strong>{{ backup.filename }}</strong></td>\n                        <td>{{ backup.reason }}</td>\n                        <td>{{ backup.actor }}</td>\n                        <td>{{ backup.created_at }}</td>\n                    </tr>\n                {% else %}\n                    <tr><td colspan="4" class="empty">No backups recorded yet.</td></tr>\n                {% endfor %}\n            </tbody>\n        </table>\n    </section>\n</section>\n{% endblock %}\n', 'users.html': '{% extends "base.html" %}\n{% block title %}Users - Procurement Control{% endblock %}\n\n{% block content %}\n<section class="page-heading">\n    <div>\n        <p class="eyebrow">Access control</p>\n        <h1>Manager users</h1>\n    </div>\n</section>\n\n<section class="split-layout">\n    <form class="form-panel slim" method="post">\n        <h2>Add user</h2>\n        <label>Username\n            <input name="username" required>\n        </label>\n        <label>Password\n            <input name="password" type="password" required>\n        </label>\n        <label>Role\n            <select name="role">\n                <option value="manager">Manager</option>\n            </select>\n        </label>\n        <button class="primary-button" type="submit">Create User</button>\n    </form>\n\n    <section class="table-shell grow">\n        <table class="data-table">\n            <thead>\n                <tr>\n                    <th>User</th>\n                    <th>Role</th>\n                    <th>Status</th>\n                    <th>Created</th>\n                    <th>Action</th>\n                </tr>\n            </thead>\n            <tbody>\n                {% for user in users %}\n                    <tr>\n                        <td><strong>{{ user.username }}</strong></td>\n                        <td>{{ user.role }}</td>\n                        <td>{{ "Active" if user.active else "Disabled" }}</td>\n                        <td>{{ user.created_at }}</td>\n                        <td>\n                            <form action="{{ url_for(\'toggle_user\', user_id=user.id) }}" method="post">\n                                <button class="secondary-button compact" type="submit">{{ "Disable" if user.active else "Enable" }}</button>\n                            </form>\n                        </td>\n                    </tr>\n                {% endfor %}\n            </tbody>\n        </table>\n    </section>\n</section>\n{% endblock %}\n'}

app.jinja_loader = DictLoader(EMBEDDED_TEMPLATES)


@app.route("/styles.css")
def styles():
    return Response(EMBEDDED_STYLES, mimetype="text/css")


def load_config():
    config = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        config["server"] = {
            "host": "0.0.0.0",
            "port": "5000",
            "debug": "false",
        }
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            config.write(file)
    config.read(CONFIG_PATH, encoding="utf-8")
    server = config["server"] if config.has_section("server") else {}
    return {
        "host": server.get("host", "0.0.0.0"),
        "port": int(server.get("port", "5000")),
        "debug": server.get("debug", "false").lower() in ("1", "true", "yes", "on"),
    }


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
            request_date TEXT,
            owner TEXT,
            priority TEXT DEFAULT 'Normal',
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
    ensure_column("procurement_items", "request_date", "TEXT")
    ensure_column("procurement_items", "owner", "TEXT")
    ensure_column("procurement_items", "priority", "TEXT DEFAULT 'Normal'")
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
        "priority_options": PRIORITY_OPTIONS,
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


def ensure_column(table, column, definition):
    db = get_db()
    columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        db.commit()


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
    if data.get("priority") not in PRIORITY_OPTIONS:
        errors.append("Priority must be Normal, Urgent, or Critical.")
    return errors


def item_from_form(existing=None):
    existing = existing or {}
    data = {
        "mms_no": form_value("mms_no"),
        "item_name": form_value("item_name") or "Untitled item",
        "quantity": integer_value("quantity"),
        "currency": form_value("currency", "MOP"),
        "requester": form_value("requester"),
        "request_date": form_value("request_date"),
        "owner": form_value("owner"),
        "priority": form_value("priority", "Normal"),
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
    rows = db.execute(
        """
        SELECT id, mms_no, currency, quantity, request_date, owner, priority,
               requester, pr_created_at, created_at
        FROM procurement_items
        """
    ).fetchall()
    for row in rows:
        updates = {}
        if row["currency"] in (None, "", "THB"):
            updates["currency"] = "MOP"
        if row["mms_no"] and not row["mms_no"].isdigit():
            updates["mms_no"] = "".join(ch for ch in row["mms_no"] if ch.isdigit())
        if row["quantity"] is not None:
            updates["quantity"] = int(row["quantity"])
        if not row["request_date"]:
            updates["request_date"] = row["pr_created_at"] or row["created_at"][:10]
        if not row["owner"]:
            updates["owner"] = row["requester"]
        if not row["priority"]:
            updates["priority"] = "Normal"
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
            "request_date": "2026-06-12",
            "owner": "Anong",
            "priority": "Urgent",
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
            "request_date": "2026-06-01",
            "owner": "Kanda",
            "priority": "Critical",
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
            "request_date": "2026-06-18",
            "owner": "Maya",
            "priority": "Normal",
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
    quick = request.args.get("quick", "").strip()
    sql = "SELECT * FROM procurement_items WHERE 1=1"
    params = []
    if search:
        sql += """
            AND (
                mms_no LIKE ? OR item_name LIKE ? OR requester LIKE ? OR owner LIKE ?
                OR supplier LIKE ? OR department LIKE ? OR priority LIKE ?
            )
        """
        needle = f"%{search}%"
        params.extend([needle] * 7)
    if status:
        sql += " AND status = ?"
        params.append(status)
    today = date.today().isoformat()
    if quick == "pending":
        sql += " AND received = 0"
    elif quick == "received":
        sql += " AND received = 1"
    elif quick == "late":
        sql += " AND received = 0 AND expected_arrival_date IS NOT NULL AND expected_arrival_date != '' AND expected_arrival_date < ?"
        params.append(today)
    elif quick == "open-pr":
        sql += " AND (po_created_at IS NULL OR po_created_at = '')"
    sql += " ORDER BY COALESCE(expected_arrival_date, '9999-12-31'), updated_at DESC"
    rows = get_db().execute(sql, params).fetchall()
    return render_template(
        "index.html",
        items=[visible_item(row) for row in rows],
        stats=stats(),
        search=search,
        status=status,
        quick=quick,
    )


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
    server_config = load_config()
    app.run(debug=server_config["debug"], host=server_config["host"], port=server_config["port"])
