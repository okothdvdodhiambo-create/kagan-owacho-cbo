# DEPLOYMENT — putting Kagan Owacho CBO on the internet

This file takes the site from "running on my laptop" to "live on a real address", including the
three outside services (M-Pesa, SMS, e-mail) and the safety checklist to run once it is public.

Read **[README.md](README.md)** first if you have never run the project.

---

## 0. The five things that must be true before any host

Open your `.env` (copy `.env.example` to `.env` if it does not exist) and set:

```ini
DEBUG=False
SECRET_KEY=<a new long random string, never the sample one>
ALLOWED_HOSTS=kaganowacho.org,www.kaganowacho.org
CSRF_TRUSTED_ORIGINS=https://kaganowacho.org,https://www.kaganowacho.org
```

Generate a key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

`DEBUG=False` switches on the production hardening already written in `config/settings.py`:
HTTPS redirect, HSTS, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`
and `X_FRAME_OPTIONS=DENY`. (`SECURE_REFERRER_POLICY=same-origin` is always on.)

Check the server is clean before you publish:

```powershell
python manage.py check --deploy
python manage.py collectstatic --noinput
```

`check --deploy` should report **0 errors**. The only warning you may see is about the key length if
you left the sample `SECRET_KEY` in place.

---

## 1. PythonAnywhere (easiest for a Kenyan CBO, free tier works)

1. Register, choose **Manual Web application**, Python **3.11+**, Web framework **Django**.
2. Upload the project (git clone, or a zip you unpack in the Bash console). **Do not upload `.env`
   or `venv/`** — put the settings in the web app's environment instead, or upload `.env` separately
   and keep it out of git.
3. Open a Bash console:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```

4. On the **Web** tab, edit the WSGI file:

   ```python
   import os, sys
   path = '/home/<your-username>/kagan-owacho-cbo'
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
   from config.wsgi import application  # noqa
   ```

5. Still on the **Web** tab, set **Static files**:
   * URL `/static/` → directory `<your-project>/staticfiles`
   * URL `/media/` → directory `<your-project>/media`
6. Add your domain to `ALLOWED_HOSTS` (PythonAnywhere gives you `<username>.pythonanywhere.com`),
   then **Reload**.
7. Log in once over HTTPS and confirm the header, the slider and the admin dashboard all appear.

The free tier only allows your own domain to be visited; that is fine here.

---

## 2. Render (free tier, auto-deploys from git)

`render.yaml` in this repository is a Render **Blueprint**: one dashboard action creates the web
service *and* its PostgreSQL database and wires `DATABASE_URL` between them. You do not type the
build command, the start command, the secret key or the database URL by hand.

```
Render dashboard → New → Blueprint → (authorise GitHub) → pick okothdvdodhiambo-create/kagan-owacho-cbo
→ Advanced → fill the four ADMIN* values → Apply
```

| Variable in the Blueprint | Where it comes from |
| --- | --- |
| `DEBUG` | fixed to `False` in `render.yaml` |
| `SECRET_KEY` | `generateValue: true` — Render makes one and reuses it on every deploy |
| `DATABASE_URL` | `fromDatabase` — Render fills it from the database it creates |
| `PYTHON_VERSION` | pinned to `3.12.11` so the Postgres and Pillow wheels install cleanly |
| `MEDIA_STORAGE` | `database` — see "uploaded files" below |
| `ADMIN1_EMAIL`, `ADMIN1_PASSWORD`, `ADMIN2_EMAIL`, `ADMIN2_PASSWORD` | **you type these**, `sync: false`, never stored in git |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | not needed: `config/settings.py` adds `RENDER_EXTERNAL_HOSTNAME` automatically |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` **or** `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | **you type these in the Environment tab** — see section 7. Without them a new member never receives their code. 587 → TLS, 465 → SSL, never both |

The build runs `pip install -r requirements.txt`, `collectstatic`, then `migrate`. That `migrate`
fires `apps/core/signals.py` → `bootstrap_site`, which creates both administrator accounts from the
environment variables, the navigation, the dropdown lists and the sample content — so no paid
Render Shell is ever needed. `bootstrap_site` refuses an account whose password is still the
placeholder from `config/settings.py`, and refuses an empty password, so a live site cannot be
reachable through the credentials printed in the README.

The same `migrate` also runs `membership.0003`, which brings the old two-step data into the single
flow: members who were already verified are linked to the account that shares their e-mail, accounts
left half-registered are allowed to sign in again, and any account without a membership row is given
a pending one so its owner is asked to complete their details after logging in. Nobody who could use
the site before loses access.

**Uploaded files.** Render gives free instances **no persistent disk**, so anything written to
`MEDIA_ROOT` disappears at the next restart or deploy. This project therefore stores uploads —
profile photos, slider photos, the logo, receipt images, incident attachments — as rows in the same
PostgreSQL database as every other record (`MEDIA_STORAGE=database`, `apps/core/storage.py`, served
back by the `/media/...` view). One backup then carries the members *and* their photos. The trade
off: the free database holds 1 GB, and each photo is resized to at most 1400 px / about 200-400 KB,
so plan for a few thousand uploads before you need more room.

If you later move to a paid Render instance you can switch to a real disk instead:

1. Add to `render.yaml`: `disks: [{name: media, mountPath: /opt/render/project/src/media, sizeGB: 1}]`
   (paid instance types only — a free one rejects the key).
2. Set `MEDIA_STORAGE` to `filesystem` (or delete it) and restart.
3. Copy the existing rows out first: `python manage.py dumpdata core.StoredFile > uploads.json`,
   then `loaddata` them into the disk with `MEDIA_STORAGE=filesystem`, or re-upload the logo and
   slider photos from the dashboard.

Cloudinary (or any S3-style bucket) is the third option: it needs an account, an API secret in
Render, and a storage backend of your own, so it is only worth it when uploads outgrow the database.

**What the free tier costs you in practice**

* A free web service **spins down after 15 minutes without traffic**; the next request waits roughly
  30-90 seconds while gunicorn starts. Every later request is normal speed.
* A free Render PostgreSQL **expires 30 days after it is created** and its data is deleted. Before
  day 30 either upgrade the database (paid, from its **Details** tab, keeping the same host) or take
  a dump and restore it into a fresh one:

  ```bash
  python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission > backup.json
  python manage.py loaddata backup.json
  ```

* One database, 512 MB RAM, 0.1 CPU: fine for a ward-sized membership, not for a county-wide one.

**Your own domain.** Add it under the service's **Info** tab → *Custom Domains*, then set
`ALLOWED_HOSTS=kaganowacho.org,www.kaganowacho.org` and
`CSRF_TRUSTED_ORIGINS=https://kaganowacho.org,https://www.kaganowacho.org` in the Environment tab and
restart. The `*.onrender.com` address keeps working without any of that.

---

## 3. Docker

```bash
docker build -t kagan-cbo .
docker run -d --name kagan-cbo -p 8000:8000 \
  --env-file .env \
  -v "$PWD/media:/app/media" \
  kagan-cbo
```

The image runs `migrate`, then `collectstatic`, then gunicorn on port 8000. Put it behind any
HTTPS-terminating proxy (Caddy, Nginx, a PaaS) and set `SECURE_SSL_REDIRECT=False` there if the
proxy already handles HTTPS.

---

## 4. A VPS (Ubuntu + Nginx + gunicorn + systemd)

```bash
sudo apt install python3-venv python3-pip nginx
sudo useradd -m -s /bin/bash kagan
sudo -u kagan python3 -m venv /home/kagan/venv
sudo -u kagan /home/kagan/venv/bin/pip install -r requirements.txt
sudo -u kagan /home/kagan/venv/bin/python manage.py migrate
sudo -u kagan /home/kagan/venv/bin/python manage.py collectstatic --noinput
```

`/etc/systemd/system/kagan-cbo.service`:

```ini
[Unit]
Description=Kagan Owacho CBO
After=network.target

[Service]
User=kagan
WorkingDirectory=/home/kagan/kagan-owacho-cbo
ExecStart=/home/kagan/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

Nginx: `proxy_pass http://127.0.0.1:8000;`, `client_max_body_size 10M;` (so photo uploads are not
refused), and `location /media/ { alias /home/kagan/kagan-owacho-cbo/media/; }`. Then
`sudo certbot --nginx` for HTTPS.

---

## 5. M-Pesa (Daraja) — turning the phone prompt on

1. Create an app at <https://developer.safaricom.co.ke> and subscribe it to **Lipa na M-Pesa Online**.
2. Fill in `.env`:

   ```ini
   MPESA_ENV=sandbox            # switch to "production" when live
   MPESA_CONSUMER_KEY=...
   MPESA_CONSUMER_SECRET=...
   MPESA_SHORTCODE=174379        # sandbox paybill; use your real paybill/till in production
   MPESA_PASSKEY=...
   MPESA_CALLBACK_URL=https://your-domain.com/contributions/mpesa/callback/
   MPESA_TRANSACTION_TYPE=CustomerPayBillOnline
   ```

3. **The callback address must be exactly** `/contributions/mpesa/callback/`, public, and HTTPS —
   Safaricom posts JSON there. It is CSRF-exempt on purpose and answers `{"ResultCode":0}`.
4. Restart the server, send a test payment, and check **Admin → Contributions** and
   **Admin → Audit log**. Every raw callback Safaricom sends is also stored in the database and can
   be read under `/django-admin/` → **M-Pesa callbacks** (read-only, added there for engineers
   tracing a failed payment).
5. Until steps 1–3 are done, nothing is broken: the site prints "M-Pesa online prompts are not
   configured yet" and members use the manual code form.

---

## 6. SMS (Africa's Talking) — optional extra copy of the code

Verification codes go to the member's **e-mail** by default. SMS is only sent *in addition* when all
three of a named provider and its keys are present:

```ini
SMS_PROVIDER=africastalking
AFRICASTALKING_USERNAME=<your username>
AFRICASTALKING_API_KEY=<your API key>
AFRICASTALKING_SENDER_ID=KAGANOWACHO   # or a short code you have been given
```

Leave `SMS_PROVIDER=console` (the default) and registration still works end to end on e-mail alone —
nothing in the site waits on SMS or on Daraja.

---

## 7. E-mail (SMTP) — the verification code, receipts, announcements

**This is the one service a public site must have configured**, because the 6-digit code that opens a
new member's account is sent by e-mail. On Render: the service → **Environment** tab → add each line
below → **Save Changes** → **Deploy** (the values are read at boot, so a deploy is what applies them).

Gmail example (use an **App Password**, not your real password):

```ini
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=kaganowacho@gmail.com
EMAIL_HOST_PASSWORD=<16-character app password>
DEFAULT_FROM_EMAIL=Kagan Owacho CBO <kaganowacho@gmail.com>
ADMIN_INBOX_EMAIL=admin1@kaganowacho.org
EMAIL_TIMEOUT=10
```

`DEFAULT_FROM_EMAIL` must use the **same address** as `EMAIL_HOST_USER`. Gmail rewrites or refuses a
sender it does not own, so a mismatched `From` can be accepted by SMTP and still never reach an inbox.

**Port 465 instead of 587?** Set `EMAIL_PORT=465`, `EMAIL_USE_SSL=True` and `EMAIL_USE_TLS=False`.
Exactly one of the two flags may be on: 465 is implicit TLS, 587 is STARTTLS. Setting
`EMAIL_USE_SSL=True` on its own is enough — TLS then defaults to off. If both are ever `True` the site
keeps SSL, switches TLS off and logs a warning instead of failing every send. Port 25 is blocked by
Render; do not use it.

`EMAIL_TIMEOUT` is how many seconds the registration page will wait on the mail server. A slow or
unreachable server therefore delays the page briefly and then tells the member what happened instead
of hanging the request; the account stays inactive until a code actually arrives.

Test it and get the exact error:

```bash
python manage.py send_test_email you@example.com
```

It prints the effective settings (the password is shown as *set, N characters*, never as a value),
warns about anything it can see is wrong, then reports `ACCEPTED by host:port in N.NNs` or the
exception type, the SMTP response code, the server's own words and the likely fix. It exits non-zero
when nothing was delivered.

Render's **free plan has no Shell tab**. There, read **your service → Logs** instead: every start
prints an `Email configuration | …` line showing exactly which values the app received, and every
send prints `Email sent …` or `Email FAILED … <exception>: <server response> | Fix: …`. Trigger a
registration or a **Resend code** to produce one. If `EMAIL_HOST` shows `localhost` or the backend
shows `console`, the variables never reached the app — check they are on the **web service** (not the
database), spelled exactly, and that you deployed after saving them.

If `EMAIL_HOST` is empty, e-mails are printed to the console. On a laptop that is convenient — while
`DEBUG=True` the code is also echoed on the screen — but on Render nobody receives anything. The
registration page, the resend page and the admin panel's *Resend code* button all say plainly that
the site cannot send e-mail yet rather than claiming a code is on its way. Until SMTP is set, verify
new members by hand from the admin panel (**Members → Verify this member by hand**).

Full walkthrough and an error-by-error table: README section 18,
*When a verification e-mail does not arrive*.

---

## 8. PostgreSQL (recommended once you have real members)

```ini
DATABASE_URL=postgres://kagan:password@localhost:5432/kagan_cbo
```

```bash
pip install "psycopg[binary]"   # requirements.txt installs it on Linux only; on Windows run this
python manage.py migrate
```

To move existing data out of SQLite:

```bash
python manage.py dumpdata --natural-foreign --natural-extra -e contenttypes -e auth.permission -e sessions -o backup.json
# switch DATABASE_URL in .env, then:
python manage.py migrate
python manage.py loaddata backup.json
```

---

## 9. Backups

The entire site is two things:

* the database (`db.sqlite3`, or a PostgreSQL dump), and
* the `media/` folder (logo, slider photos, bank slips, report galleries).

```bash
# nightly example for a VPS
tar czf /backups/kagan-$(date +%F).tgz /home/kagan/kagan-owacho-cbo/db.sqlite3 /home/kagan/kagan-owacho-cbo/media
```

Restore = copy both back and restart. Test a restore once; an untested backup is not a backup.

---

## 10. Go-live checklist

- [ ] `SECRET_KEY` replaced with a fresh random value, `.env` never committed
- [ ] `DEBUG=False`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` set to the real domain
- [ ] `python manage.py check --deploy` → no errors
- [ ] `python manage.py migrate` and `collectstatic` ran on the server
- [ ] Both admin passwords changed from the samples in `.env.example`
- [ ] HTTPS works and HTTP redirects to it
- [ ] Logo, three slider photos, motto, bank details, paybill, WhatsApp number, social links filled in
- [ ] Dropdown options (gender / role / occupation) match the ward
- [ ] SMTP settings saved in the Render **Environment** tab (the code that opens a new account is e-mailed)
- [ ] One real registration done end to end: one form, code received by e-mail, verified, KOC number given, dashboard reachable
- [ ] An account created by the old two-step flow can still log in and is asked to complete its membership details
- [ ] One real payment confirmed, and the PDF statement downloaded and printed
- [ ] SMTP and (if used) SMS and Daraja keys verified in production mode
- [ ] Audit log shows the actions above with the right admin and IP
- [ ] Backup job scheduled and one restore tested
- [ ] `/admin-panel/` refuses a member account with the friendly 403 page

---

## 11. When something goes wrong

| Symptom | Cause and fix |
|---|---|
| `DisallowedHost at /` | The host you typed is not in `ALLOWED_HOSTS`. Add it (with and without `www`). |
| CSS/images missing, 404 on `/static/...` | `collectstatic` was not run, or the host serves a different folder. Run it; on PythonAnywhere re-check the `/static/` mapping. |
| Forms bounce back to the login page | The domain is missing from `CSRF_TRUSTED_ORIGINS`, or the site is behind a proxy that hides HTTPS. |
| Verification code never arrives | Read **Logs**: the `Email configuration` line shows what the app received, and each send writes `Email sent` or `Email FAILED` with the exact SMTP error. `localhost`/`console` means the variables never reached the app — re-check the Environment tab and deploy again. Otherwise run `python manage.py send_test_email you@example.com`, or see README section 18. SMS is only an extra copy and only when `SMS_PROVIDER=africastalking` with its keys. |
| The page said the code was sent but nothing arrives | The console backend reports success without delivering. A live site now says it cannot send e-mail instead; if you still see this, `EMAIL_HOST` is set but `DEFAULT_FROM_EMAIL` is an address the provider does not own — make it match `EMAIL_HOST_USER`. |
| Mail times out or the connection is closed | Port/flag mismatch: 587 needs `EMAIL_USE_TLS=True`, 465 needs `EMAIL_USE_SSL=True`, never both. Port 25 is blocked. |
| Login says the account is not verified | Correct behaviour: the e-mailed code has not been entered yet. Use **Resend verification code** on the login page, or verify the member by hand in the admin panel once you have checked their ID. |
| A new member is stuck on "Complete your membership" | Their account came from the old two-step flow and has no member details. Fill the form once; a code is e-mailed and the membership then confirms as usual. |
| STK push says "not configured" | Daraja keys missing or `MPESA_ENV` does not match the keys (sandbox keys only work against sandbox). |
| Payment stays "awaiting" forever | Safaricom cannot reach `MPESA_CALLBACK_URL` — it must be public HTTPS with no auth; the members' page also polls the status, so check the callback log. |
| `500` after a settings change | Read the server log; the styled 500 page is intentionally generic. Re-run `python manage.py check`. |
| Upload "did not look like a valid image" | The file really is not a JPEG/PNG/WebP/GIF, or it is over `MAX_UPLOAD_SIZE_MB`. |
| Login says "too many attempts" | The 5-strike lockout is doing its job; wait `LOGIN_LOCKOUT_MINUTES` (15) or raise it in `.env`. |
