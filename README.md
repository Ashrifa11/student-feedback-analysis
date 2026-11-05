# Student Feedback Analysis System

Flask + SQLite app. Students submit ratings and comments; instructors sign in to see
sentiment, themes, per-course averages, recent comments, and a CSV export.
Sentiment is analysed with a built-in lexicon (no model downloads, so deploys are fast).

## Run locally
    pip install -r requirements.txt
    python app.py          # http://localhost:5000

## Deploy on Render
1. Push this folder to a GitHub repo.
2. Render dashboard > New > Blueprint > select the repo (uses `render.yaml`).
   Or New > Web Service with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
   - Health check path: `/healthz`
3. Set environment variables: `ADMIN_PASSWORD` (instructor login) and `SECRET_KEY` (any long random string).

## Notes
- Instructor page: `/login` (default password `admin123` if `ADMIN_PASSWORD` is not set; always set it).
- Render's free plan has an ephemeral disk, so the SQLite file resets on redeploy/restart.
  For permanent storage, add a Render Disk and set `DB_PATH=/var/data/feedback.db`.
- Edit the `COURSES` list in `app.py` to match your courses.
