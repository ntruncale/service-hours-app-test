# Service Hours

A Django web app for logging student community service. Students sign in with their school
Microsoft account and log hours. Supervisors confirm by email with no account needed, and
grade-level teachers track progress on a dashboard. It runs in iPad Safari and can be added
to the home screen as an app icon.

> **Teacher's note:** this is a complete reference version. Keep it out of the students'
> repository if they are building their own. You can use it as an answer key, to check
> their design choices, or to unblock a team that is stuck.

## Run it on your computer

You need Python 3.12 or newer and Git.

```bash
git clone <this repo> service-hours
cd service-hours
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # local settings; never commit .env
python manage.py migrate
python manage.py seed_demo         # fake teachers, 32 students, ~140 entries
python manage.py runserver
```

Open http://localhost:8000. Choose **Sign in as a test user** to act as a student, a teacher
(one per grade), or the principal (all grades plus the admin site). Emails are printed in the
terminal, so you can copy a supervisor link from there and open it in a private window.

To test on a real iPad on the same Wi-Fi, run `python manage.py runserver 0.0.0.0:8000` and
add your computer's IP address to `ALLOWED_HOSTS` in `.env`.

## Run the tests

```bash
pytest                    # 105 unit, permission and flow tests (about 2 seconds)
pytest -m e2e             # browser test at iPad size: student -> supervisor -> teacher
ruff check . && ruff format --check .
```

The first time you run the e2e test, run `python -m playwright install chromium`.
GitHub Actions runs everything on each push (`.github/workflows/ci.yml`).

## What's where

| Path | What it does |
| --- | --- |
| `config/settings.py` | All settings. School-specific values come from environment variables |
| `accounts/` | User model with roles, Microsoft sign-in (`microsoft.py`), grade assignments, school-year math (`school_year.py`) |
| `hours/models.py` | `Requirement`, `ServiceEntry`, `ApprovalRequest` (hashed one-time tokens), `AuditLog` |
| `hours/services.py` | Business rules: submit, flags, supervisor and teacher decisions, reminders, progress |
| `hours/views.py` | Student pages and the public supervisor approval page |
| `dashboard/` | Teacher views: roster and filters, student detail, waiting, flagged, summary, organizations, supervisor lookup, CSV export |
| `notifications/` | Email templates helper and the Microsoft Graph email backend |
| `hours/management/commands/` | `send_reminders` (run daily) and `seed_demo` |
| `templates/`, `static/` | HTML pages, CSS and app icons |
| `tests/` | pytest suite. `test_permissions.py` lists the ways a student might try to break in |

## How the main rules work

- **Who sees what:** students see only their own entries. A teacher sees students in the grade
  levels assigned to them in the admin site (Grade assignments). An admin sees all grades.
- **Requirement:** set hours per grade under Admin > Requirements. Progress compares approved
  hours across all years with the total required through the student's current grade. For
  "10 per year" enter 10/10/10/10. For "40 by graduation" enter 0/0/0/40.
- **Grade level** is calculated from the graduation year and the date. The school year starts in
  `SCHOOL_YEAR_START_MONTH` (July by default). Teachers stay with a grade level; to have a
  teacher follow a class instead, change their grade assignment each summer.
- **Supervisor approval:** each link is a random 43-character token. Only its SHA-256 hash is
  stored. Opening the link never approves anything, because school email scanners open links
  automatically. The supervisor must type their name and press a button. A link works once and
  expires after `APPROVAL_LINK_DAYS`. Editing an entry or resending replaces the old link.
- **Reminders:** `python manage.py send_reminders` emails a reminder on the days listed in
  `REMINDER_AFTER_DAYS`, then marks unanswered entries expired. Schedule it once a day.
- **Flags** (shown to teachers, never blocking): supervisor shares the student's last name, more
  than `MAX_HOURS_PER_DAY` hours on one day, or the supervisor uses a school email address.
- **Blocked supervisor emails:** the student's own email, other students' emails, and any domain
  in `BLOCKED_SUPERVISOR_DOMAINS` (put your student email domain here).
- **Teacher override:** on a student's page, open "History and teacher actions" to approve or
  decline with a required reason. Every change is in the audit log.

## Going live

See [docs/SETUP-IT.md](docs/SETUP-IT.md) for the Microsoft setup IT must do, and
[docs/DEPLOY.md](docs/DEPLOY.md) for hosting and putting the icon on student iPads.
