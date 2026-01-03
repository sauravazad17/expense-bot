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

if os.getenv("GOOGLE_CREDS"):
    creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", scope
    )

client = gspread.authorize(creds)
sheet = client.open("Personal Expenses by Saurav").worksheet("Budget Expenses")

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
    "other": "Other Groceries Items",
    "extra": "Extra/Additional Expenses"
}

MONTH_MAP = {
    "jan":1,"january":1,
    "feb":2,"february":2,
    "mar":3,"march":3,
    "apr":4,"april":4,
    "may":5,
    "jun":6,"june":6,
    "jul":7,"july":7,
    "aug":8,"august":8,
    "sep":9,"september":9,
    "oct":10,"october":10,
    "nov":11,"november":11,
    "dec":12,"december":12
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

    fillers = ["add","on","in","me","mein","do","kar","items","item","rs","rupees"]
    for f in fillers:
        clean = re.sub(rf'\b{f}\b', '', clean)

    return " ".join(clean.split()).title()

# ================= SUMMARY =================
def build_summary(start_date, end_date, category=None):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)

    total = 0
    table = []

    for r in rows:
        try:
            d = datetime.strptime(r["Date"], "%d/%m/%Y").date()
            if not (start_date <= d <= end_date):
                continue
            if category and r["Category"] != category:
                continue

            amt = int(r["Price/Amount"])
            total += amt

            table.append(
                f"<tr>"
                f"<td>{r['Date']}</td>"
                f"<td>{r['Category']}</td>"
                f"<td>₹{amt}</td>"
                f"<td>{r['Things Details']}</td>"
                f"</tr>"
            )
        except:
            continue

    if not table:
        return "<p>No expenses found for this period.</p>"

    return f"""
<b>Summary: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}</b>
<table border="1" cellpadding="5" cellspacing="0" style="margin-top:8px;font-size:12px">
<tr><th>Date</th><th>Category</th><th>Amount</th><th>Details</th></tr>
{''.join(table)}
</table>
<b>Total Spent: ₹{total}</b>
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
        last_end = today.replace(day=1) - timedelta(days=1)
        last_start = last_end.replace(day=1)
        return build_summary(last_start, last_end, category)

    # RANGE (YEAR-AWARE)
    m = re.findall(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s*(\d{1,2})',
        msg
    )

    if len(m) == 2:
        sm, sd = m[0]
        em, ed = m[1]

        sm_i = MONTH_MAP[sm]
        em_i = MONTH_MAP[em]

        if sm_i > em_i:
            start_year = today.year - 1
            end_year = today.year
        else:
            start_year = end_year = today.year

        d1 = datetime(start_year, sm_i, int(sd)).date()
        d2 = datetime(end_year, em_i, int(ed)).date()

        return build_summary(d1, d2, category)

    return "Please specify a valid summary period."

# ================= ROUTE =================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    msg = request.form.get("message", "").strip().lower()

    if "summary" in msg:
        return jsonify({"reply": handle_summary(msg)})

    if any(w in msg for w in ["add","jod","daal"]):
        reset_session()
        SESSION["mode"] = "add"

    if SESSION["mode"] == "add":
        SESSION["amount"] = SESSION["amount"] or extract_amount(msg)
        SESSION["category"] = SESSION["category"] or extract_category(msg)
        SESSION["date"] = SESSION["date"] or extract_date(msg)
        SESSION["details"] = SESSION["details"] or extract_details(msg)

        if SESSION["amount"] is None:
            return jsonify({"reply": "Please tell the amount."})
        if SESSION["category"] is None:
            return jsonify({"reply": "Please tell the category."})
        if SESSION["date"] is None:
            return jsonify({"reply": "On what date did this expense occur?"})
        if SESSION["details"] is None:
            return jsonify({"reply": "Please tell the details."})

        SESSION["mode"] = "confirm"

        return jsonify({
            "reply":
            f"Please confirm:<br>"
            f"Amount: ₹{SESSION['amount']}<br>"
            f"Category: {SESSION['category']}<br>"
            f"Date: {SESSION['date'].strftime('%d %b %Y')}<br>"
            f"Details: {SESSION['details']}<br><br>"
            f"Reply YES or NO."
        })

    if SESSION["mode"] == "confirm":
        if msg in ["yes","y"]:
            sheet.append_row([
                SESSION["date"].year,
                SESSION["date"].strftime("%b"),
                SESSION["date"].strftime("%d/%m/%Y"),
                SESSION["category"],
                SESSION["amount"],
                SESSION["details"],
                "Saurav"
            ], value_input_option="USER_ENTERED")
            reset_session()
            return jsonify({"reply": "Expense saved successfully."})

        if msg in ["no","n"]:
            reset_session()
            return jsonify({"reply": "Expense cancelled."})

        return jsonify({"reply": "Please reply YES or NO."})

    return jsonify({"reply": "You can add expenses or ask for summaries."})

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
