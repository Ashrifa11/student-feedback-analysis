import csv
import io
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, session, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "feedback.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

COURSES = [
    "Computer Science 101",
    "Data Structures",
    "Database Systems",
    "Web Development",
    "Machine Learning",
    "Engineering Mathematics",
]

# ---------------------------------------------------------------- analysis
POSITIVE = set("""good great excellent amazing awesome helpful clear engaging
fun interesting useful inspiring supportive friendly patient organized
well best love loved enjoy enjoyed enjoyable easy understandable knowledgeable
perfect fantastic wonderful improved responsive brilliant practical valuable
smooth effective""".split())
NEGATIVE = set("""bad poor terrible awful boring confusing unclear difficult
hard slow rushed late disorganized unhelpful useless waste worst hate hated
stressful overwhelming outdated broken noisy unfair lacking lack boring
dull frustrating confused messy crowded""".split())
NEGATIONS = {"not", "no", "never", "isn't", "wasn't", "don't", "didn't",
             "doesn't", "cannot", "can't", "hardly", "without"}
INTENSIFIERS = {"very", "really", "extremely", "super", "too", "so", "highly"}

TOPICS = {
    "Teaching": ["teach", "lecture", "instructor", "professor", "explain",
                 "faculty", "teacher", "pace"],
    "Course content": ["content", "syllabus", "topic", "curriculum", "material",
                       "slides", "notes", "project"],
    "Assessment": ["exam", "test", "assignment", "grade", "grading", "quiz",
                   "homework", "marks", "deadline"],
    "Facilities": ["lab", "classroom", "wifi", "internet", "library",
                   "equipment", "room", "campus", "projector"],
    "Support": ["support", "doubt", "help", "mentor", "guidance", "office hours",
                "feedback", "response"],
}


def analyze(comment, rating):
    tokens = re.findall(r"[a-z']+", comment.lower())
    total = 0.0
    for i, word in enumerate(tokens):
        value = 1.0 if word in POSITIVE else -1.0 if word in NEGATIVE else 0.0
        if value == 0.0:
            continue
        window = tokens[max(0, i - 2):i]
        if any(w in NEGATIONS for w in window):
            value = -value
        if any(w in INTENSIFIERS for w in window):
            value *= 1.5
        total += value
    text_score = total / (abs(total) + 2.0)
    rating_score = (rating - 3) / 2.0
    score = round(0.6 * text_score + 0.4 * rating_score, 3)
    label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
    lowered = comment.lower()
    topics = [name for name, words in TOPICS.items()
              if any(w in lowered for w in words)]
    return score, label, topics


# ---------------------------------------------------------------- database
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_name TEXT,
        course TEXT NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT NOT NULL,
        score REAL NOT NULL,
        sentiment TEXT NOT NULL,
        topics TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL)""")
    conn.commit()
    conn.close()


init_db()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify(error="Please sign in."), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ------------------------------------------------------------------ pages
@app.route("/")
def index():
    return render_template("index.html", courses=COURSES)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("dashboard"))
        error = "Incorrect password. Try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@admin_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/healthz")
def healthz():
    return "ok", 200


# -------------------------------------------------------------------- API
@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    data = request.get_json(silent=True) or {}
    name = str(data.get("student_name", "")).strip()[:80]
    course = str(data.get("course", "")).strip()
    comment = str(data.get("comment", "")).strip()
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if course not in COURSES:
        return jsonify(error="Choose a course from the list."), 400
    if rating < 1 or rating > 5:
        return jsonify(error="Select a rating from 1 to 5."), 400
    if len(comment) < 5:
        return jsonify(error="Write at least a few words of feedback."), 400
    comment = comment[:1500]

    score, label, topics = analyze(comment, rating)
    conn = get_db()
    conn.execute(
        "INSERT INTO feedback (student_name, course, rating, comment, score,"
        " sentiment, topics, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (name, course, rating, comment, score, label, ",".join(topics),
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    return jsonify(ok=True, sentiment=label, score=score, topics=topics), 201


@app.route("/api/stats")
@admin_required
def stats():
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM feedback ORDER BY id DESC").fetchall()]
    conn.close()

    total = len(rows)
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    ratings = {str(i): 0 for i in range(1, 6)}
    topic_counts, by_course = {}, {}
    for r in rows:
        sentiments[r["sentiment"]] += 1
        ratings[str(r["rating"])] += 1
        c = by_course.setdefault(r["course"], {"count": 0, "sum": 0, "score": 0.0})
        c["count"] += 1
        c["sum"] += r["rating"]
        c["score"] += r["score"]
        for t in filter(None, r["topics"].split(",")):
            topic_counts[t] = topic_counts.get(t, 0) + 1

    courses = [{"course": k, "count": v["count"],
                "avg_rating": round(v["sum"] / v["count"], 2),
                "avg_score": round(v["score"] / v["count"], 2)}
               for k, v in by_course.items()]
    courses.sort(key=lambda c: c["avg_rating"], reverse=True)
    avg = round(sum(r["rating"] for r in rows) / total, 2) if total else 0
    recent = [{k: r[k] for k in ("id", "student_name", "course", "rating",
                                  "comment", "sentiment", "topics", "created_at")}
              for r in rows[:25]]
    return jsonify(total=total, average_rating=avg, sentiments=sentiments,
                   ratings=ratings, topics=topic_counts, courses=courses,
                   recent=recent)


@app.route("/export.csv")
@admin_required
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM feedback ORDER BY id").fetchall()
    conn.close()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "student_name", "course", "rating", "comment",
                     "score", "sentiment", "topics", "created_at"])
    for r in rows:
        writer.writerow([r["id"], r["student_name"], r["course"], r["rating"],
                         r["comment"], r["score"], r["sentiment"], r["topics"],
                         r["created_at"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=feedback.csv"})


@app.errorhandler(404)
def not_found(_):
    return render_template("login.html", error="That page does not exist."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
