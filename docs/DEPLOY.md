# Deploying and putting it on iPads

## What any host needs

- Python 3.12+, a PostgreSQL database, and HTTPS.
- Build command: `pip install -r requirements.txt`
- Start command: `./startup.sh` (runs migrations, collects static files, starts gunicorn)
- A once-a-day job: `python manage.py send_reminders`
- Environment variables (see `.env.example`). In production, at least:

```
DEBUG=false
SECRET_KEY=<long random string: python -c "import secrets; print(secrets.token_urlsafe(50))">
ALLOWED_HOSTS=servicehours.yourschool.org
CSRF_TRUSTED_ORIGINS=https://servicehours.yourschool.org
SITE_URL=https://servicehours.yourschool.org
DATABASE_URL=postgres://...
SCHOOL_NAME=...
BLOCKED_SUPERVISOR_DOMAINS=students.yourschool.org
TEACHER_EMAILS=...
ADMIN_EMAILS=...
MS_TENANT_ID=... / MS_CLIENT_ID=... / MS_CLIENT_SECRET=...
EMAIL_PROVIDER=graph
DEFAULT_FROM_EMAIL=servicehours@yourschool.org
GRAPH_SENDER_MAILBOX=servicehours@yourschool.org
```

The developer sign-in page turns off automatically when `DEBUG=false`.

## Option A: Render (simplest)

1. Create a PostgreSQL database and copy its internal connection URL into `DATABASE_URL`.
2. Create a Web Service from the GitHub repo. Build: `pip install -r requirements.txt`.
   Start: `./startup.sh`. Add the environment variables.
3. Create a Cron Job from the same repo with schedule `0 14 * * *` (UTC) and command
   `python manage.py send_reminders`, using the same environment variables.
4. Add your custom domain and update the Microsoft redirect URI to match.

## Option B: Azure App Service (often free with Microsoft education credits)

1. Create an Azure Database for PostgreSQL (flexible server) and a Linux App Service using Python 3.12.
2. Under Configuration, set the startup command to `./startup.sh` and add the environment
   variables as App settings.
3. Deploy from GitHub with the Deployment Center.
4. For the daily reminder job, use an Azure Functions timer, a WebJob, or a scheduled GitHub
   Actions workflow that runs `python manage.py send_reminders` against the production database.

## After the first deploy

1. Create the first admin: sign in with an email listed in `ADMIN_EMAILS`.
2. In `/admin/`, set Requirements for grades 9 to 12 and add Grade assignments for the four teachers.
3. Pilot with one grade before turning it on for everyone.
4. Back up the database. Most managed Postgres services have daily backups; check that they're on.

## Putting it on student iPads

**Recommended: a web clip pushed by MDM.** In Jamf, Mosyle, Intune or similar, create a Web
Clip payload with URL `https://servicehours.yourschool.org`, label "Service Hours", and
"full screen" turned on. It uses the app icon automatically. Students tap the icon and sign in
with Microsoft. Updates go live as soon as you deploy, with no App Store review.

**Later, optional: a native app.** Wrap the site in a small native app that adds something
the web can't do well, such as push notifications or photo upload. Distribute it privately to
your school as a Custom App through Apple School Manager. You need a Mac with Xcode and the
school's Apple Developer account. Microsoft sign-in inside a native app must use the system
sign-in sheet (ASWebAuthenticationSession), not an embedded web view.
