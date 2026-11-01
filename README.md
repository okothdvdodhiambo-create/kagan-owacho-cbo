# KAGAN OWACHO CBO — Members, Contributions, Events and Reports

A complete website for **Kagan Owacho CBO** (Kagan Ward, Rangwe Constituency, Homa Bay County, Kenya).
The CBO was formed to pay school fees for needy students and to support the community, and this
system keeps a record of every member, every shilling received, every sponsored event and every
problem a member reports.

This README is written for the person who will **run** the site, not only for a programmer.
If you only want to start it on a laptop, go straight to
[Running it on your own computer](#running-it-on-your-own-computer-windows).

---

## 1. What the system does

| Area | What a member sees | What the committee sees |
|---|---|---|
| Public pages | Home page with the photo slider, About, Events Sponsored, Event Calendar, Register | Same pages, plus drafts that are not published |
| Membership | Register, then enter the code sent by email/SMS, then a member dashboard with their KOC number | Full member list, search, filters, view/suspend/activate/delete, CSV & Excel export |
| Money | Pay by M-Pesa prompt, record an M-Pesa code, or upload a bank slip; see their transcript; download a signed PDF statement | Every payment with status, confirm or reject with a reason, totals, filters, export |
| Events | Calendar (month + list), event pages, written reports with photos | Create/edit/delete events and reports, upload photo galleries, email a report to all members |
| Problems | Report an incident with an attachment, see the committee's reply | Inbox of incidents, reply, change status, assign themselves |
| Communication | "Chat with us" WhatsApp link, e-mail-us form inside the member area | Send an announcement to all verified members, read and answer member messages |
| Site content | — | Logo, organisation name, motto, home/about text, bank details, paybill, slider photos, social links, navigation buttons, dropdown options |
| Safety | — | Audit log of every important action, with the admin's name, what they did and their IP address |

Everything is in one design (green and gold), works on a phone, and never shows a member another
member's information.

---

## 2. Who can log in

| Type | How they get it | Where they land after login |
|---|---|---|
| **Administrator** | Two accounts are created automatically from the `.env` file | `/admin-panel/` (the full committee dashboard) |
| **Member** | Registers on the site, then confirms the code | Home page, then `/member/dashboard/` |
| **Visitor** | No login | Public pages only |

A normal member who types an admin address gets a friendly "This area is for the committee" page
(HTTP 403). The check is on the `is_admin` flag, not on Django's staff flag, so nobody can slip in
through the back door.

---

## 3. Technology

* **Python 3.14** and **Django 5.2** (Long-term support release)
* **SQLite** by default — one file, `db.sqlite3`, nothing to install. **PostgreSQL** is a one-line
  change (see [section 12](#12-switching-to-postgresql)).
* **python-decouple** — all passwords, keys and hosts live in `.env`, never in the code
* **dj-database-url** — reads the optional `DATABASE_URL`
* **WhiteNoise** — the site serves its own CSS, JS and icons, so no web server is needed for static
  files (uploaded photos in `media/` are mapped by the host — see DEPLOYMENT.md)
* **Pillow** — photos are resized and compressed on upload (a 5 MB phone photo becomes ~200 KB)
* **xhtml2pdf** — the PDF statement. Pure Python, so it works on Windows with no extra system library
* **openpyxl** — Excel exports for the treasurer
* **Bootstrap 5.3, Font Awesome 6, FullCalendar 6** — loaded from the jsDelivr/Cloudflare CDNs, so the
  visitor needs internet for the icons and the calendar grid (see [honest notes](#14-what-was-tested-and-what-was-not))
* No payment or SMS library is required while testing: both have a **development fallback** built in.

---

## 4. Running it on your own computer (Windows)

Open **PowerShell** or **Command Prompt**, go to the folder, and type these lines one at a time.
You only need the first five steps once.

```powershell
cd C:\path\to\this\folder

# 1. create a private copy of Python for this project
python -m venv venv

# 2. switch to that copy
venv\Scripts\activate

# 3. install the libraries
pip install -r requirements.txt

# 4. copy the settings template and open it in Notepad to fill it in
copy .env.example .env
notepad .env

# 5. build the database (this also creates the admins, menus and demo photos)
python manage.py migrate

# 6. start the site
python manage.py runserver
```

Now open **<http://127.0.0.1:8000/>** in your browser.

To stop the server press `Ctrl+C`. To start it again later you only need steps 2 and 6.

### If `python` is not recognised

Install Python from <https://www.python.org/downloads/> and tick **"Add python.exe to PATH"** during
installation. Check with `python --version` (3.11 or newer works; this project was built on 3.14).

---

## 5. Logging in as an administrator

The two admin accounts are taken from your `.env` file, so **change them there before you go live**.
As delivered, `.env.example` (and therefore your new `.env`) contains:

| | |
|---|---|
| Address 1 | `admin1@kaganowacho.org` / `AdminOne#2026` |
| Address 2 | `admin2@kaganowacho.org` / `AdminTwo#2026` |

Those two passwords are development placeholders. They work while `DEBUG=True`. Once `DEBUG=False`,
`bootstrap_site` refuses to create an account that still uses one (and refuses an empty password) and
prints the reason in the deploy log — so a public site can never be reachable through a password that
is printed in this file.

Go to **/accounts/login/** (the *Log in* button at the top right), enter one of those pairs, and you
land on the committee dashboard at **/admin-panel/**.

* Forgot the password? Use **Forgot password?** — a reset link is emailed. While `EMAIL_HOST` is
  empty in `.env`, the email is printed in the terminal running `runserver` instead of being sent.
* Five wrong passwords lock that address for 15 minutes (`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`).
* The Django technical screens are at `/django-admin/`. They are only for engineers; the committee
  never needs them, and they use the same admin accounts.

---

## 6. The first ten minutes after installing

Do these in the **Site settings** section of the dashboard. Nothing breaks if you skip one — the
pages fall back to the text that was written for you.

1. **Site text, logo & photos** — upload the CBO logo, confirm the name and write the motto.
   The logo appears in the header, the footer and on the PDF statement.
2. **Slider photos** — upload three pictures of what the CBO does (fee handover, a meeting, a
   thank-you event). They rotate automatically on the home page; the demo pictures that were
   generated for you can be deleted here.
3. **Bank & M-Pesa details** — bank name, account name, account number, branch, and the paybill if
   you have one. Members see exactly this when they go to pay.
4. **Social links** — Facebook, X, Instagram, YouTube, TikTok, WhatsApp. They appear as icons in the footer.
5. **Navigation buttons** — rename or reorder the menu, or hide a button.
6. **Dropdown options** — the genders, roles and occupations offered on the registration form.
   Add "Boda Rider" or remove anything that does not fit the ward.
7. **Contact & location** — WhatsApp number, e-mail, postal address, and (optional) the Google Maps
   embed address, which shows the ward map on the location page inside the member area.

Then delete the demo records you do not want: the demo member (`jane@example.org`), the three demo
events, and the demo reports. They exist only so that every page has something to show.

---

## 7. How a member joins

1. They press **Register as a Member** and fill in name, phone, e-mail, gender, role, location,
   sub-location and (optional) occupation. Gender and role must be values from the dropdown options.
2. The phone number is normalised to `+2547...` — `0712 345 678`, `+254712345678` and
   `00254712345678` all mean the same person.
3. They get a **6-digit code** by e-mail and/or SMS and are sent to the "check your code" page.
   * The code is valid for **10 minutes**, allows **5 guesses**, and can be re-sent once a minute.
   * Only the **hash** of the code is stored in the database, not the code itself.
   * With no SMS/e-mail configured the code is printed in the terminal (and logged), so you can
     always finish the flow while testing.
4. On the right code they are logged in, given the next number (`KOC-0001`, `KOC-0002`, …) and marked
   active. Numbers never repeat, even if two people register in the same second.
5. Until the code is confirmed they are *pending* and cannot pay or post incidents; the admin can
   also see who is waiting.

---

## 8. How money comes in

| Route | When it is used | What happens |
|---|---|---|
| **M-Pesa prompt (STK Push)** | Only when the Daraja keys are in `.env` | The phone rings with the KSh ask. The page waits and updates itself when Safaricom answers. |
| **Record an M-Pesa code** | Always available | The member sends to the paybill/till normally and types the M-Pesa code (e.g. `H30ABCD12`). |
| **Bank deposit** | Always available | The member types the slip number and uploads a photo of the slip. |

Everything starts as **Awaiting verification**. The treasurer confirms or rejects (a reason is
required to reject); the member is told by e-mail either way. The PDF statement only counts
confirmed gifts, and shows the pending ones separately so nothing looks like money it is not.

**Statement:** `/contributions/statement/` opens it, `?download=1` saves it. It carries the logo,
the member's KOC number, every payment with its method, reference and status, the total given, the
treasurer's signature block and the "computer generated" note.

Without Daraja keys the M-Pesa prompt page shows a clear notice and offers the manual code route —
the site never dies just because a key is missing.

---

## 9. Events, calendar and reports

* **Events Sponsored** (`/events/`) is the accountability page: what the members paid for, newest
  first, filterable by type, each event with its report and photos.
* **Event Calendar** (`/events/calendar/`) is a month grid plus a list view. It reads
  `/events/feed/`, and always shows **East Africa Time** even for a visitor in another country.
  Clicking a box opens a small popup with the time, venue and a link to the full page.
* **Reports** are written by the committee after the event, with a photo gallery, and can be mailed
  to every verified member in one click from the dashboard.

---

## 10. Incident reports

A member reports a problem (a lost receipt, a wrong entry, a complaint) with an optional photo or
PDF. It appears in the admin **Inbox**, the admin replies from the incident page, the status moves
through *New → Under review → Resolved → Closed*, and the member sees the reply in their own
"Report an incident" page and is told by e-mail.

---

## 11. Keeping records safe

* **Audit log** (`/admin-panel/audit/`) — who did what, to which record, when, from which IP.
  Confirmed payments, deletions, suspensions, settings changes, announcements and event edits are
  all there. It is searchable and paginated.
* **Passwords** are hashed by Django (PBKDF2); nobody can read them out of the database.
* **CSRF protection** on every form, **XSS escaping** on every page (Django autoescape),
  session cookies marked HttpOnly, and in production (`DEBUG=False`) the cookies become
  secure-only, HTTPS is enforced and HSTS is switched on.
* **Uploads** are checked three ways: extension, size limit (`MAX_UPLOAD_SIZE_MB`, default 5 MB),
  and the file's actual header bytes — a `.jpg` that is really an `.exe` is refused.
* **Normal users never reach admin pages**: every admin view sits behind a decorator that checks
  `is_admin` and returns 403 otherwise.

---

## 12. Switching to PostgreSQL

1. `pip install "psycopg[binary]"` (a ready-made wheel — no compiler needed on Windows)
2. In `.env` set `DATABASE_URL=postgres://user:password@host:5432/dbname`
3. `python manage.py migrate`

That is the only change; nothing else in the code knows or cares which database is underneath.

---

## 13. Automated tests

```powershell
python manage.py test
```

The suite covers the flows the project brief asked for and more:

| Module | What it proves |
|---|---|
| `apps.accounts` | Sign-up rules, password hashing, photo resize, login redirects, case-insensitive e-mail, lockout after 5 failures, logout, password reset e-mail |
| `apps.membership` | Registration validation (Kenyan phone rules, dropdown-only choices), pending state, code issue/hash/expiry/attempts/resend, numbering, who may enter the member area |
| `apps.contributions` | Manual M-Pesa, bank slip, transcript totals, confirm/reject + e-mail, STK fallback when Daraja is off, Safaricom callback (success, failure, unknown, bad JSON, wrong verb), PDF statement content |
| `apps.admin_panel` | Permission matrix (anonymous/member/staff/admin/superuser), member search & filters, CSV/Excel export, suspend/delete + audit, payment decisions, incident replies, settings forms, navigation, dropdowns, announcements, event create/delete |
| `apps.core` | Settings singleton, phone normalisation, image validation, audit IP handling, home/about rendering, slider and navigation, `bootstrap_site` (admins from `.env`, placeholder-password refusal, idempotency), database-backed uploads and the `/media/` view |
| `apps.events` | The calendar feed's exact shape and time-zone handling, published vs draft, category filter, report pages |

Latest run: **126 tests, all passing** (`python manage.py test` prints `OK`).

Tests never touch your real data — they build a separate `test_db.sqlite3` and delete it afterwards.

---

## 14. What was tested and what was not

Honest notes for whoever marks or deploys this:

* **Verified by machine** — every automated test above, `manage.py check --deploy`,
  `collectstatic` (129 files, hashed manifest), the SQLite and PostgreSQL configuration paths,
  PDF generation, image resizing, CSV/Excel exports. Also a Render-shaped run of the whole site
  (`DEBUG=False`, `RENDER_EXTERNAL_HOSTNAME` set, uploads held in the database): both administrators
  bootstrapped from environment variables, the public pages, a photo saved by the slider form and
  served back through `/media/`, a committee login reaching the dashboard, and a statement PDF whose
  logo had to be copied out of the database first.
* **Verified by hand in a real browser** — home page with the animated header, slider (arrows, dots,
  auto-advance), mobile menu, member registration and login, member dashboard, the PDF statement as
  rendered by a PDF viewer, the calendar showing events on the correct EAT dates, the admin
  dashboard, and the styled 403 page for a member who opens an admin URL.
* **Not verified** — a live M-Pesa STK push (no Safaricom keys available), a real Africa's Talking
  SMS, a real SMTP delivery, a live PostgreSQL server, and a real Render account: `render.yaml`
  parses and the app runs in the exact configuration it describes, but only you can press
  *New → Blueprint*. The code paths exist and are exercised with development fallbacks and mocked
  responses; the handshake with those services can only be proven with real credentials.
* The calendar, Bootstrap and Font Awesome come from a CDN. On a machine with no internet the pages
  still work, but icons and the calendar grid look plain/empty. Vendoring those files locally is a
  small, self-contained change if you need a fully offline site.

---

## 15. What you must supply before going live

Nothing in the code has a secret in it. Fill these in `.env`:

| Setting | Where you get it | Needed for |
|---|---|---|
| `SECRET_KEY` | any long random string, e.g. `python -c "import secrets;print(secrets.token_urlsafe(50))"` | everything — **must** be changed |
| `DEBUG=False`, `ALLOWED_HOSTS=your-domain.com` | your domain | production security mode |
| `CSRF_TRUSTED_ORIGINS=https://your-domain.com` | your domain | forms to submit over HTTPS |
| `ADMIN1_*`, `ADMIN2_*` | you decide | the two committee logins — change the defaults |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Gmail app password, or your hosting SMTP | verification e-mails, receipts, announcements |
| `AFRICASTALKING_USERNAME`, `AFRICASTALKING_API_KEY`, `AFRICASTALKING_SENDER_ID`, `SMS_PROVIDER=africastalking` | africastalking.com | SMS verification codes |
| `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_ENV`, `MPESA_CALLBACK_URL` | developer.safaricom.co.ke (Daraja) | the "pay on my phone" prompt |
| `DATABASE_URL` | your database host | PostgreSQL instead of SQLite |
| Logo, three slider photos, motto, bank details, social links | the CBO's own material | uploaded in Site settings, not in `.env` |

While any of these are empty the site still runs: e-mails and SMS are printed to the terminal, and
the M-Pesa prompt falls back to the manual code form.

---

## 16. Deploying it

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for PythonAnywhere, Render, Docker and a VPS, including the
exact M-Pesa callback address and the checklist to run once the site is public.

For Render the repository carries a **`render.yaml` Blueprint**: one *New → Blueprint* action in the
dashboard creates the web service and its PostgreSQL database, generates the `SECRET_KEY`, and runs
`migrate` (which creates the two administrator accounts from the environment variables). Uploaded
photos go into the database rather than a folder, because Render's free instances have no persistent
disk — set `MEDIA_STORAGE=filesystem` if you mount a paid disk instead.

---

## 17. Where everything lives

```
manage.py                 the command you run
config/                   settings, main URLs, WSGI/ASGI entry points
apps/accounts/            login, sign-up, profile, password reset, throttling
apps/membership/          registration, verification codes, member dashboard
apps/contributions/       M-Pesa (Daraja), bank, transcript, PDF statement
apps/events/              events, calendar + JSON feed, reports and photos
apps/incidents/           member problems and committee replies
apps/communications/      announcements, member messages, e-mail + SMS services
apps/admin_panel/         the committee dashboard, settings, exports, audit views
apps/core/                site settings, navigation, slider, audit log, helpers,
                          and storage.py (uploads kept inside the database)
templates/                every HTML page (including 403/404/500)
static/                   the site's own CSS and JS
media/                    uploaded files when MEDIA_STORAGE=filesystem
render.yaml               one-click Render setup: the web service plus PostgreSQL
db.sqlite3                the database - delete it to start empty
.env                      your secrets - never share or commit this file
```

**Backup rule:** on a laptop, the whole site is `db.sqlite3` plus the `media/` folder. On Render
(`MEDIA_STORAGE=database`) the photos live inside the database, so **one database dump is the entire
site** - that is why the uploads were put there.
