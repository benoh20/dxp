# Deploying Powerbuilder

This is the runbook for pushing changes from `main` to [powerbuilder.app](https://powerbuilder.app). It is deliberately short. If you find yourself needing more steps than what's here, something has drifted and the runbook should be updated to match.

## How the pieces fit together

| Piece | Role | Touched on deploy? |
|---|---|---|
| Squarespace | Domain registrar for `powerbuilder.app`. DNS is delegated to Google Cloud DNS nameservers (`ns-cloud-e[1-4].googledomains.com`). | No |
| DigitalOcean droplet (`167.99.225.6`) | Runs nginx + Django via a `powerbuilder` systemd unit. This is the only thing the deploy actually changes. | Yes |
| S3 bucket | Static asset storage (collected static files, research-memo PDFs). Only relevant when `static/` changes. | Sometimes, see below |

Squarespace is uninvolved at runtime. The domain points at the droplet via an A record, and Squarespace's servers never see a request. There's no reason to log into the Squarespace dashboard to deploy code.

## The happy path

Three commands on the droplet:

```bash
ssh <user>@powerbuilder.app
cd /var/www/powerbuilder/powerbuilder
git pull origin main
sudo systemctl restart powerbuilder
```

That's it for most changes. The Django process re-reads everything (Python modules, templates, settings) on restart.

### One-shot version

Paste-friendly into an open SSH session:

```bash
cd /var/www/powerbuilder/powerbuilder \
  && git pull origin main \
  && sudo systemctl restart powerbuilder \
  && sleep 2 \
  && sudo systemctl status powerbuilder --no-pager
```

The trailing `status` confirms the unit came back up `active (running)` instead of crashing on startup.

## When you also need `collectstatic`

`collectstatic` is **only** needed when files under `powerbuilder/static/` actually change. The decision rule:

| Change | Needs `collectstatic`? |
|---|---|
| `chat/agents/*.py` (any agent code) | No |
| `chat/views.py`, `urls.py`, settings | No |
| `templates/*.html` (Django templates with inline `<style>`) | No |
| `tool_templates/*.md` (LLM prompt templates) | No |
| `static/css/*.css`, new image assets, new JS bundles | **Yes** |
| `requirements.txt` changes | No (but see "Dependency changes" below) |

When in doubt, run it. It's cheap and idempotent:

```bash
cd /var/www/powerbuilder/powerbuilder
source venv/bin/activate
python manage.py collectstatic --noinput
sudo systemctl restart powerbuilder
```

## Dependency changes

If a PR touches `requirements.txt`:

```bash
cd /var/www/powerbuilder/powerbuilder
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart powerbuilder
```

## Database migrations

If a PR touches `chat/migrations/` or any other `migrations/` directory:

```bash
cd /var/www/powerbuilder/powerbuilder
source venv/bin/activate
python manage.py migrate
sudo systemctl restart powerbuilder
```

If you don't know whether a PR has migrations, `git diff --name-only origin/main..HEAD | grep migrations/` will tell you.

## Smoke test

After every deploy, from your laptop:

```bash
curl -I https://powerbuilder.app/
```

Expected: `HTTP/1.1 302 Found` redirecting to `/chat/`. If you get 502 or 504, the Django process didn't come back up, jump to "If something breaks".

For a deeper check, log in to the demo gate (password is in the team password manager) and confirm that:

1. The empty state renders without errors.
2. Sending a small query (e.g. one of the demo tiles) returns a response.

## If something breaks

The fastest signal is the systemd journal:

```bash
sudo journalctl -u powerbuilder -n 100 --no-pager
```

Common failure modes:

- **`ImportError` or `ModuleNotFoundError`** — a new dependency landed but `pip install -r requirements.txt` was skipped. Run it, restart.
- **`OperationalError: no such table`** — a migration landed but `python manage.py migrate` was skipped. Run it, restart.
- **`TemplateDoesNotExist`** — usually a path typo in a recent template change; check the journal for the exact template name.
- **502 Bad Gateway from nginx** — Django is down. The `status` command will show why.

To roll back in a hurry:

```bash
cd /var/www/powerbuilder/powerbuilder
git log --oneline -5            # find the last good commit
git checkout <sha>
sudo systemctl restart powerbuilder
```

Then open an issue with the journal output so the next deploy doesn't re-introduce the same failure.

## The `deploy.sh` script

A `deploy.sh` exists on the droplet from initial setup, but it prompts for a sudo password mid-run, so it's not automatable. The three-command flow above is what's actually used. If someone wants to harden `deploy.sh` later (cache sudo, add migration detection, integrate the smoke test), that's a worthwhile follow-up but not blocking.

## What deploys do not touch

- **Pinecone corpus.** Re-seeded only when `tool_templates/best_practices/*.md` changes, via `python scripts/seed_best_practices.py`. Not part of a normal deploy.
- **API keys.** Live in `.env` on the droplet, not in the repo. Rotated separately.
- **DNS.** Managed via Squarespace (registrar) → Google Cloud DNS. No deploy touches it.
- **The S3 bucket** for anything other than `collectstatic` output. Research-memo PDFs are pushed manually via `bulk_upload.py` when adding to the corpus.

## Who has access

SSH to the droplet is currently held by Ben. Rosario does not have direct shell access; deploys go through Ben. If we want to widen this, the right move is to add an additional public key to `/home/<user>/.ssh/authorized_keys` on the droplet rather than sharing a private key.
