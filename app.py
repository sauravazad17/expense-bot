from flask import Flask, request, jsonify, render_template
import re
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# ================= GOOGLE SHEET =================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

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
def extract_category(text):
    for k, v in CATEGORY_MAP.items():
        if re.search(rf"\b{k}\b", text):
            return v
    return None

# ================= SUMMARY =================
def build_summary(start_date, end_date, category_filter=None):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)

    total = 0
    table_rows = []

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

            table_rows.append(
                f"<tr>"
                f"<td style='border:1px solid #000;padding:8px'>{r['Date']}</td>"
                f"<td style='border:1px solid #000;padding:8px'>{cat}</td>"
                f"<td style='border:1px solid #000;padding:8px'>₹{amt}</td>"
                f"<td style='border:1px solid #000;padding:8px'>{r['Things Details']}</td>"
                f"</tr>"
            )
        except:
            continue

    if not table_rows:
        return "<p>No expenses found for this period.</p>"

    return f"""
<h3>Summary: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}</h3>

<table style="border-collapse:collapse;width:100%">
<tr style="background:#add8e6;font-weight:bold">
<th style="border:1px solid #000;padding:8px">Date</th>
<th style="border:1px solid #000;padding:8px">Category</th>
<th style="border:1px solid #000;padding:8px">Amount</th>
<th style="border:1px solid #000;padding:8px">Details</th>
</tr>
{''.join(table_rows)}
</table>

<p><b>Total Spent: ₹{total}</b></p>
"""

def handle_summary(msg):
    today = datetime.today().date()
    category = extract_category(msg)

    # ----- FIXED DATE LOGIC -----
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

    # ----- SPECIFIC DATE RANGE (dec 10 to dec 15) -----
    m = re.findall(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*(\d{1,2})',
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

    if "summary" in msg:
        return jsonify({"reply": handle_summary(msg)})

    if any(w in msg for w in ["last", "when"]):
        return jsonify({"reply": handle_last_spend(msg)})

    return jsonify({"reply": "You can add expenses or ask for summaries."})

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
