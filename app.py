from flask import Flask, request, jsonify, render_template
import re
import os, json
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# ================= GOOGLE SHEET =================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

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

def reset_session():
    for k in SESSION:
        SESSION[k] = None

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
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12
}

STOP_WORDS = {
    "last", "time", "when", "did", "i",
    "spent", "spend", "on", "kab", "hua", "to"
}

# ================= HELPERS =================
def extract_amount(text):
    m = re.search(r'\b(\d{1,6})\b', text)
    return int(m.group(1)) if m else None

def extract_category(text):
    for k, v in CATEGORY_MAP.items():
        if re.search(rf"\b{k}\b", text):
            return v
    return None

def extract_date(text):
    today = datetime.today()

    if "today" in text:
        return today

    if "yesterday" in text:
        return today - timedelta(days=1)

    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*(\d{1,2})', text)
    if m:
        mon, day = m.groups()
        return datetime(today.year, MONTH_MAP[mon], int(day))

    return None

def extract_details(text):
    clean = re.sub(r'\d+', '', text)

    for k in CATEGORY_MAP:
        clean = re.sub(rf'\b{k}\b', '', clean)

    fillers = ["add", "in", "on", "rs", "rupees"]
    for f in fillers:
        clean = re.sub(rf'\b{f}\b', '', clean)

    return " ".join(clean.split()).title()

# ================= SUMMARY =================
def build_summary(start_date, end_date, category_filter=None):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)
    total = 0
    table_rows = []

    for r in rows:
        try:
            d = datetime.strptime(r["Date"], "%d/%m/%Y").date()
            if not (start_date <= d <= end_date):
                continue

            if category_filter and r["Category"] != category_filter:
                continue

            amt = int(r["Price/Amount"])
            total += amt

            table_rows.append(
                f"<tr><td>{r['Date']}</td><td>{r['Category']}</td>"
                f"<td>₹{amt}</td><td>{r['Things Details']}</td></tr>"
            )
        except:
            continue

    if not table_rows:
        return "<p>No expenses found.</p>"

    return f"""
<h3>Summary: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}</h3>
<table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
<tr style="background:#add8e6;font-weight:bold">
<th>Date</th><th>Category</th><th>Amount</th><th>Details</th>
</tr>
{''.join(table_rows)}
</table>
<p><b>Total Spent: ₹{total}</b></p>
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

    return "Please specify a valid summary period."

# ================= LAST SPEND =================
def handle_last_spend(msg):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)
    words = [w for w in re.findall(r'\w+', msg) if w not in STOP_WORDS]
    latest = None

    for r in rows:
        if any(w in r["Things Details"].lower() for w in words):
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
        f"<b>Last time spent on {latest['details']}</b><br>"
        f"📅 Date: {latest['date'].strftime('%d %b %Y')}<br>"
        f"📂 Category: {latest['category']}<br>"
        f"💰 Amount: ₹{latest['amount']}"
    )

# ================= ROUTE =================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    msg = request.form.get("message", "").strip().lower()

    # 🔥 ADD HAS HIGHEST PRIORITY
    if any(msg.startswith(w) for w in ["add", "jod", "daal"]):
        reset_session()
        SESSION["mode"] = "add"

    # CONFIRM
    if SESSION["mode"] == "confirm":
        if msg in ["yes", "y"]:
            row = [
                SESSION["date"].year,
                SESSION["date"].strftime("%b"),
                SESSION["date"].strftime("%d/%m/%Y"),
                SESSION["category"],
                SESSION["amount"],
                SESSION["details"],
                "Saurav"
            ]
            sheet.append_row(row)
            reset_session()
            return jsonify({"reply": "✅ Expense saved."})

        if msg in ["no", "n"]:
            reset_session()
            return jsonify({"reply": "❌ Cancelled."})

    # ADD FLOW
    if SESSION["mode"] == "add":
        SESSION["amount"] = SESSION["amount"] or extract_amount(msg)
        SESSION["category"] = SESSION["category"] or extract_category(msg)
        SESSION["date"] = SESSION["date"] or extract_date(msg)
        SESSION["details"] = SESSION["details"] or extract_details(msg)

        if SESSION["amount"] is None:
            return jsonify({"reply": "Tell amount."})
        if SESSION["category"] is None:
            return jsonify({"reply": "Tell category."})
        if SESSION["date"] is None:
            return jsonify({"reply": "Tell date."})
        if SESSION["details"] is None:
            return jsonify({"reply": "Tell details."})

        SESSION["mode"] = "confirm"

        return jsonify({
            "reply":
            f"Confirm:\n₹{SESSION['amount']} | {SESSION['category']} | "
            f"{SESSION['date'].strftime('%d %b %Y')} | {SESSION['details']}\n\nYES / NO"
        })

    if "summary" in msg:
        return jsonify({"reply": handle_summary(msg)})

    if msg.startswith("last"):
        return jsonify({"reply": handle_last_spend(msg)})

    return jsonify({"reply": "You can add expenses or ask for summaries."})

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
