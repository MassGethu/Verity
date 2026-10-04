# Vercel + Supabase deployment

The application keeps its Django templates and local SQLite mode. Vercel uses `config.wsgi.application`, PostgreSQL uses Supabase transaction pooling, and PDFs live in a private `resumes` bucket. No local database or media directory is shipped. Runtime migrations are not performed on every request.

## Supabase

Create a separate Verity project. Create a private bucket named `resumes`, limit uploads to 5 MB, and allow `application/pdf`. Do not add anonymous read/write policies. The server holds the service-role key; browser uploads use short-lived signed object URLs, never that key. Retrieve the transaction-pooler connection URI (port 6543) from Connect. Replace the password placeholder and URL-encode reserved characters in the password.

Add these to `.env` locally for connection checks, and later as private Vercel environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase transaction-pooler PostgreSQL URI |
| `SUPABASE_URL` | Project URL, `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only service-role key from project API settings |
| `SUPABASE_STORAGE_BUCKET` | `resumes` |
| `DJANGO_SECRET_KEY` | A new long random value |
| `VERITY_JUDGE_PASSWORD` | A strong shared workspace password supplied privately to judges |
| `DJANGO_ALLOWED_HOSTS` | Exact production hostname; optional custom hostnames comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact HTTPS production origins, comma-separated |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | Provider credentials |
| `GROQ_MODEL` / `GEMINI_MODEL` | Configured model IDs |
| `GITHUB_TOKEN` | Optional server-side GitHub token |

Keep `VERITY_USE_SUPABASE=0` locally unless testing the hosted backend. Vercel sets `VERCEL=1`, which enables production mode automatically. For a production check locally set `VERITY_PRODUCTION=1` for that command. Do not paste credentials into chat or commit `.env`.

## Prepare the database once

After verifying that the URI points to the new Verity project:

```sh
VERITY_USE_SUPABASE=1 .venv/bin/python manage.py migrate
# Optional labelled synthetic examples, without AI calls:
VERITY_USE_SUPABASE=1 .venv/bin/python manage.py seed_demo
```

This creates a separate cloud database. It does not upload the laptop SQLite database or real candidate data. Cloud seeded PDF storage must be reachable before seeding; otherwise postpone the seed and use the upload UI.

## Vercel

Push the reviewed code to the connected GitHub repository. In the project import screen choose Django, root `./`, and the default requirements install command. Leave Build Command and Output Directory at their defaults: Vercel's Django integration collects static files automatically. Add the private environment variables above, then deploy. Prefer Production-only database/provider secrets; previews should use a separate test database or remain undeployed.

`vercel.json` configures the WSGI function for 120 seconds. Enable Fluid Compute and confirm that the account supports this duration before judging. An operation has at most two 30-second provider calls; GitHub has a bounded inspection budget. Static files are served by the Vercel CDN. Keep the private PDFs outside the function response: the PDF view authorises the request and redirects to a five-minute signed storage URL.

The public landing page and `/health/` are open. Every recruiter route requires the shared workspace password in hosted mode. Sessions use signed HttpOnly cookies, HTTPS is required, DEBUG is disabled, and password rotation invalidates existing workspace access. This is a single shared judging workspace, not a multi-user product. Use synthetic résumés only.

## Direct upload flow

The browser submits only file metadata to Django, uploads each raw PDF to its signed private-storage URL, then sends a signed completion ticket. Django checks job approval, ticket age/job, actual size, PDF signature/parser limits, extracted text and SHA-256 deduplication before storing an application. Batch files are handled sequentially with per-file errors. Hosted uploads require JavaScript. Files rejected after storage upload can remain orphaned; remove unused objects from the private bucket after the demo. Do not remove objects referenced by applications.

## Final checks before submitting the URL

- HTTPS landing page and local Motion/static assets load without login.
- Workspace and PDF/application routes redirect unauthorised visitors to login.
- Login, job creation, rubric approval, direct batch upload and duplicate handling work.
- A live synthetic résumé analysis validates, ranks and explains sources; provider failure leaves it retryable and unranked.
- Shortlist, guide edits, GitHub inspection and editable feedback work.
- PDF view/download works without passing large files through Vercel.
- Database records and PDFs survive a deployment/restart.
- Include the canonical production URL and workspace password in the submission instructions.

Useful references: [Vercel Django](https://vercel.com/docs/frameworks/full-stack/django), [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [private storage buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals).
