from flask import Flask, request, jsonify, render_template
import re, os, json
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
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

client = gspread.authorize(creds)

sheet = client.open("Personal Expenses by Saurav").worksheet("Budget Expenses")

EXPECTED_HEADERS = [
    "Year", "Month", "Date",
    "Category", "Price/Amount",
    "Things Details", "Name"
]

# ================= SESSION =================
SESSION = {
    "mode": None,   # add | confirm
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
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12
}

STOP_WORDS = {"last","time","when","did","i","spent","spend","on","kab","hua","to"}

# ================= HELPERS =================
def reset_session():
    for k in SESSION:
        SESSION[k] = None

def extract_amount(text):
    m = re.search(r'\b(\d{1,6})\b', text)
    return int(m.group(1)) if m else None

def extract_category(text):
    for k,v in CATEGORY_MAP.items():
        if re.search(rf"\b{k}\b", text):
            return v
    return None

def extract_date(text):
    t = text.lower()
    today = datetime.today()

    if "today" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)

    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*(\d{1,2})', t)
    if m:
        return datetime(today.year, MONTH_MAP[m.group(1)], int(m.group(2)))

    return None

def extract_details(text):
    clean = text.lower()

    clean = re.sub(r'\d+', '', clean)

    for k in CATEGORY_MAP:
        clean = re.sub(rf'\b{k}\b', '', clean)

    for m in MONTH_MAP:
        clean = re.sub(rf'\b{m}\b', '', clean)

    fillers = [
        "add","on","in","me","mein","do","kar",
        "rupees","rs","expense","spent","spend"
    ]

    for f in fillers:
        clean = re.sub(rf'\b{f}\b', '', clean)

    clean = " ".join(clean.split()).strip()
    return clean.title() if clean else None

# ================= SUMMARY =================
def build_summary(start, end, category=None):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)
    total = 0
    table = []

    for r in rows:
        try:
            d = datetime.strptime(r["Date"], "%d/%m/%Y").date()
            if not (start <= d <= end):
                continue
            if category and r["Category"] != category:
                continue

            amt = int(r["Price/Amount"])
            total += amt

            table.append(
                f"<tr>"
                f"<td style='border:1px solid #000;padding:8px'>{r['Date']}</td>"
                f"<td style='border:1px solid #000;padding:8px'>{r['Category']}</td>"
                f"<td style='border:1px solid #000;padding:8px'>₹{amt}</td>"
                f"<td style='border:1px solid #000;padding:8px'>{r['Things Details']}</td>"
                f"</tr>"
            )
        except:
            continue

    if not table:
        return "<p>No expenses found.</p>"

    return f"""
<h3>Summary: {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}</h3>
<table style="border-collapse:collapse;width:100%">
<tr style="background:#add8e6;font-weight:bold">
<th style="border:1px solid #000;padding:8px">Date</th>
<th style="border:1px solid #000;padding:8px">Category</th>
<th style="border:1px solid #000;padding:8px">Amount</th>
<th style="border:1px solid #000;padding:8px">Details</th>
</tr>
{''.join(table)}
</table>
<p><b>Total Spent: ₹{total}</b></p>
"""

def handle_summary(msg):
    today = datetime.today().date()
    cat = extract_category(msg)

    if "today" in msg:
        return build_summary(today, today, cat)
    if "yesterday" in msg:
        y = today - timedelta(days=1)
        return build_summary(y, y, cat)
    if "this month" in msg:
        return build_summary(today.replace(day=1), today, cat)
    if "last month" in msg:
        first = (today.replace(day=1)-timedelta(days=1)).replace(day=1)
        last = today.replace(day=1)-timedelta(days=1)
        return build_summary(first, last, cat)

    m = re.findall(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*(\d{1,2})', msg)
    if len(m) == 2:
        d1 = datetime(today.year, MONTH_MAP[m[0][0]], int(m[0][1])).date()
        d2 = datetime(today.year, MONTH_MAP[m[1][0]], int(m[1][1])).date()
        if d1 > d2:
            d1, d2 = d2, d1
        return build_summary(d1, d2, cat)

    return "Please specify a valid summary period."

# ================= LAST SPEND =================
def handle_last_spend(msg):
    rows = sheet.get_all_records(expected_headers=EXPECTED_HEADERS)
    words = [w for w in re.findall(r'\w+', msg) if w not in STOP_WORDS]
    latest = None

    for r in rows:
        if any(w in r["Things Details"].lower() for w in words):
            d = datetime.strptime(r["Date"], "%d/%m/%Y")
            if not latest or d > latest["date"]:
                latest = {
                    "date": d,
                    "amount": r["Price/Amount"],
                    "category": r["Category"],
                    "details": r["Things Details"]
                }

    if not latest:
        return "No matching expense found."

    return (
        f"<b>Last time spent on {latest['details']}</b><br>"
        f"📅 Date: {latest['date'].strftime('%d %b %Y')}<br>"
        f"📂 Category: {latest['category']}<br>"
        f"💰 Amount: ₹{latest['amount']}"
    )

# ================= ROUTE =================
@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    msg = request.form.get("message","").lower().strip()

    if "summary" in msg:
        return jsonify({"reply": handle_summary(msg)})

    if any(w in msg for w in ["last","when"]):
        return jsonify({"reply": handle_last_spend(msg)})

    if any(w in msg for w in ["add","jod","daal"]):
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
            f"Please confirm:\n\n"
            f"Amount: ₹{SESSION['amount']}\n"
            f"Category: {SESSION['category']}\n"
            f"Date: {SESSION['date'].strftime('%d %b %Y')}\n"
            f"Details: {SESSION['details']}\n\n"
            f"Reply YES to save or NO to cancel."
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
            ])
            reset_session()
            return jsonify({"reply":"✅ Expense saved successfully."})

        if msg in ["no","n"]:
            reset_session()
            return jsonify({"reply":"❌ Expense cancelled."})

        return jsonify({"reply":"Please reply YES or NO."})

    return jsonify({"reply":"You can add expenses or ask for summaries."})

if __name__ == "__main__":
    app.run(debug=True)
