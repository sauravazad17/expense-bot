from flask import Flask, request, jsonify, render_template
import re
import os
import json
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# ================= GOOGLE SHEET =================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Load Google credentials
if os.getenv("GOOGLE_CREDS"):
    creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", scope
    )

client = gspread.authorize(creds)

SPREADSHEET_NAME = "Personal Expenses by Saurav"
SHEET_NAME = "Budget Expenses"
sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)

EXPECTED_HEADERS = [
    "Year", "Month", "Date",
    "Category", "Price/Amount",
    "Things Details", "Name"
]

# ================= SESSION =================
SESSION = {
    "mode": None,
    "amount": None,
    "category": None,
    "date": None,
    "details": None
}

# ================= CONSTANTS =================
CATEGORY_MAP = {
    "basic": "Basic Fixed Expenses",
    "fixed": "Basic Fixed Expenses",
    "daily": "Daily Vegetables",
    "vegetable": "Daily Vegetables",
    "sabzi": "Daily Vegetables",
    "outdoor": "Outdoor Food Items",
    "food": "Outdoor Food Items",
    "grocery": "Other Groceries Items",
    "extra": "Extra/Additional Expenses"
}

MONTH_MAP = {
    "jan":1, "january":1,
    "feb":2, "february":2,
    "mar":3, "march":3,
    "apr":4, "april":4,
    "may":5,
    "jun":6, "june":6,
    "jul":7, "july":7,
    "aug":8, "august":8,
    "sep":9, "september":9,
    "oct":10, "october":10,
    "nov":11, "november":11,
    "dec":12, "december":12
}

STOP_WORDS = {
    "last", "time", "when", "did", "i",
    "spent", "spend", "on", "kab", "hua", "to"
}

# ================= HELPERS =================
def reset_session():
    for k in SESSION:
        SESSION[k] = None

def extract_amount(text):
    m = re.search(r'\b(\d{1,6})\b', text)
    return int(m.group(1)) if m else None

def extract_category(text):
    for k, v in CATEGORY_MAP.items():
        if re.search(rf"\b{k}\b", text):
            return v
    return None

def extract_date(text):
    t = text.lower()
    today = datetime.today()

    if "today" in t or "aaj" in t:
        return today

    if "yesterday" in t or "kal" in t:
        return today - timedelta(days=1)

    m = re.search(
        r'(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)\s*(\d{1,2})',
        t
    )
    if m:
        mon, day = m.groups()
        return datetime(today.year, MONTH_MAP[mon], int(day))

    return None

def extract_details(text):
    clean = text.lower()
    clean = re.sub(r'\d+', '', clean)

    for k in CATEGORY_MAP:
        clean = re.sub(rf'\b{k}\b', '', clean)

    for v in CATEGORY_MAP.values():
        for part in v.lower().split():
            clean = re.sub(rf'\b{part}\b', '', clean)

    for m in MONTH_MAP:
        clean = re.sub(rf'\b{m}\b', '', clean)

    fillers = ["add", "on", "in", "me", "mein", "do", "kar", "items", "item", "rupees", "rs"]
    for f in fillers:
        clean = re.sub(rf'\b{f}\b', '', clean)

    clean = " ".join(clean.split()).strip()
    return clean.title() if clean else None

# ================= SUMMARY =================
def build_summary(start_date, end_date, category_filter=None):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)

    total = 0
    table = []

    for r in rows:
        try:
            d = datetime.strptime(r["Date"], "%d/%m/%Y").date()
            cat = r["Category"]

            if not (start_date <= d <= end_date):
                continue

            if category_filter and cat != category_filter:
                continue

            amt = int(r["Price/Amount"])
            total += amt

            table.append(
                f"<tr>"
                f"<td style='border:1px solid #000;padding:6px'>{r['Date']}</td>"
                f"<td style='border:1px solid #000;padding:6px'>{cat}</td>"
                f"<td style='border:1px solid #000;padding:6px'>₹{amt}</td>"
                f"<td style='border:1px solid #000;padding:6px'>{r['Things Details']}</td>"
                f"</tr>"
            )
        except:
            continue

    if not table:
        return "<p style='font-size:12px'>No expenses found for this period.</p>"

    return f"""
<h3 style="font-size:14px">Summary: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}</h3>

<table style="border-collapse:collapse;width:100%;font-size:12px">
<tr style="background:#add8e6;font-weight:bold">
<th style="border:1px solid #000;padding:6px">Date</th>
<th style="border:1px solid #000;padding:6px">Category</th>
<th style="border:1px solid #000;padding:6px">Amount</th>
<th style="border:1px solid #000;padding:6px">Details</th>
</tr>
{''.join(table)}
</table>

<p style="font-size:12px"><b>Total Spent: ₹{total}</b></p>
"""

def handle_summary(msg):
    today = datetime.today().date()
    category = extract_category(msg)

    if "today" in msg:
        return build_summary(today, today, category)

    if "yesterday" in msg:
        y = today - timedelta(days=1)
        return build_summary(y, y, category)

    if "this month" in msg:
        return build_summary(today.replace(day=1), today, category)

    if "last month" in msg:
        first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last = today.replace(day=1) - timedelta(days=1)
        return build_summary(first, last, category)

    m = re.findall(
        r'(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)\s*(\d{1,2})',
        msg
    )

    if len(m) == 2:
        d1 = datetime(today.year, MONTH_MAP[m[0][0]], int(m[0][1])).date()
        d2 = datetime(today.year, MONTH_MAP[m[1][0]], int(m[1][1])).date()

        if d1 > d2:
            d1, d2 = d2, d1

        return build_summary(d1, d2, category)

    return "Please specify a valid summary period."

# ================= LAST SPEND =================
def handle_last_spend(msg):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)

    words = [
        w for w in re.findall(r'\w+', msg.lower())
        if w not in STOP_WORDS
    ]

    latest = None

    for r in rows:
        details = str(r["Things Details"]).lower()

        if any(w in details for w in words):
            try:
                d = datetime.strptime(r["Date"], "%d/%m/%Y")
                if not latest or d > latest["date"]:
                    latest = {
                        "date": d,
                        "amount": r["Price/Amount"],
                        "category": r["Category"],
                        "details": r["Things Details"]
                    }
            except:
                continue

    if not latest:
        return "No matching expense found."

    return (
        f"<div style='font-size:13px'>"
        f"<b>Last time spent on {latest['details']}</b><br>"
        f"📅 Date: {latest['date'].strftime('%d %b %Y')}<br>"
        f"📂 Category: {latest['category']}<br>"
        f"💰 Amount: ₹{latest['amount']}"
        f"</div>"
    )

# ================= ROUTE =================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    msg = request.form.get("message", "").strip().lower()

    # ---------- ADD ----------
    if any(w in msg for w in ["add", "jod", "daal"]):
        reset_session()
        SESSION["mode"] = "add"

    if SESSION["mode"] == "add":
        SESSION["amount"] = SESSION["amount"] or extract_amount(msg)
        SESSION["category"] = SESSION["category"] or extract_category(msg)
        SESSION["date"] = SESSION["date"] or extract_date(msg)
        SESSION["details"] = SESSION["details"] or extract_details(msg)

        if SESSION["amount"] is None:
            return jsonify({"reply": "💰 Please tell the amount."})

        if SESSION["category"] is None:
            return jsonify({"reply": "📂 Please tell the category."})

        if SESSION["date"] is None:
            return jsonify({"reply": "📅 On what date did this expense occur?"})

        if SESSION["details"] is None:
            return jsonify({"reply": "📝 Please tell the details."})

        SESSION["mode"] = "confirm"

        return jsonify({
            "reply":
            f"<div style='font-size:13px'>"
            f"<b>Please confirm:</b><br><br>"
            f"Amount: ₹{SESSION['amount']}<br>"
            f"Category: {SESSION['category']}<br>"
            f"Date: {SESSION['date'].strftime('%d %b %Y')}<br>"
            f"Details: {SESSION['details']}<br><br>"
            f"Reply <b>YES</b> to save or <b>NO</b> to cancel."
            f"</div>"
        })

    if SESSION["mode"] == "confirm":
        if msg in ["yes", "y"]:
            sheet.append_row(
                [
                    SESSION["date"].year,
                    SESSION["date"].strftime("%b"),
                    SESSION["date"].strftime("%d/%m/%Y"),
                    SESSION["category"],
                    SESSION["amount"],
                    SESSION["details"],
                    "Saurav"
                ],
                value_input_option="USER_ENTERED"
            )
            reset_session()
            return jsonify({"reply": "✅ Expense saved successfully."})

        if msg in ["no", "n"]:
            reset_session()
            return jsonify({"reply": "❌ Expense cancelled."})

        return jsonify({"reply": "Please reply YES or NO only."})

    # ---------- SUMMARY ----------
    if "summary" in msg:
        return jsonify({"reply": handle_summary(msg)})

    # ---------- LAST SPEND ----------
    if any(w in msg for w in ["last", "when"]):
        return jsonify({"reply": handle_last_spend(msg)})

    return jsonify({"reply": "You can add expenses or ask for summaries."})

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
