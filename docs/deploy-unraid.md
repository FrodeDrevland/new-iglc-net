# Preview on the Unraid server (iglc.drevland.net)

A password-protected preview of the new site, for showing it to the IGLC before switch-over.
It runs as two containers (`iglc-web` and `iglc-db`) behind SWAG. Paper PDFs stay in Azure blob storage.
This is a preview, not the production home of iglc.net.

## 1. Get the code onto the server

The code is in the private repository https://github.com/FrodeDrevland/new-iglc-net. The server reads it
with a deploy key: read-only access to this one repository.

In the Unraid terminal:

```sh
mkdir -p /mnt/user/appdata/iglc/import
ssh-keygen -t ed25519 -f /mnt/user/appdata/iglc/deploy_key -N "" -C "unraid iglc preview"
cat /mnt/user/appdata/iglc/deploy_key.pub
```

On GitHub, open the repository's **Settings > Deploy keys > Add deploy key**, paste the key and leave
"Allow write access" unticked. Then:

```sh
export GIT_SSH_COMMAND="ssh -i /mnt/user/appdata/iglc/deploy_key -o IdentitiesOnly=yes"
git clone git@github.com:FrodeDrevland/new-iglc-net.git /mnt/user/appdata/iglc/src
cd /mnt/user/appdata/iglc/src
git config core.sshCommand "$GIT_SSH_COMMAND"
```

The database export is not in the repository. Copy it to `/mnt/user/appdata/iglc/import/`
(for example through the `appdata` share, `\\<server>\appdata\iglc\import`):
`iglc_db-2026-9-23-18-7.bacpac`.

## 2. Settings

In `/mnt/user/appdata/iglc/src`, copy `.env.prod.example` to `.env.prod` and fill in:

- `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`: two different long random strings, for example from
  `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
- `PROXY_NETWORK`: the Docker network SWAG is on. Find it with `docker inspect swag --format '{{json .NetworkSettings.Networks}}'`.

## 3. Build and start

In the Unraid terminal (needs `docker compose`, for example from the Compose Manager plugin):

```sh
cd /mnt/user/appdata/iglc/src
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

The web container runs the database migrations each time it starts.

## 4. Load the data (first time only)

```sh
docker exec -it iglc-web python manage.py import_legacy /import/iglc_db-2026-9-23-18-7.bacpac
docker exec -it iglc-web python manage.py import_legacy_pages
docker exec -it iglc-web python manage.py createsuperuser
```

## 5. SWAG

1. Make sure `iglc` is covered by SWAG's certificate: add it to `SUBDOMAINS` in the SWAG container settings
   (not needed with a wildcard certificate), and point `iglc.drevland.net` at your home IP like the other subdomains.
2. Copy `deploy/unraid/iglc.subdomain.conf` to SWAG's `/config/nginx/proxy-confs/`.
3. Create the preview login (you are asked for a password):
   `docker exec -it swag htpasswd -c /config/nginx/.htpasswd-iglc iglc`
4. For the conference sites (conference.iglc.drevland.net, the same container): add `conference.iglc` to
   `SUBDOMAINS` as well (a wildcard `*.drevland.net` certificate does not cover a name two levels down),
   point `conference.iglc.drevland.net` at your home IP, and copy `deploy/unraid/conference-iglc.subdomain.conf`
   to `/config/nginx/proxy-confs/`. It uses the same preview login. Nothing changes in `.env.prod`: the
   host name follows `SITE_URL`.
5. For the programme at the venue (program.iglc.drevland.net, the same container): the same as step 4
   with `program.iglc` and `deploy/unraid/program-iglc.subdomain.conf`. Its host name also follows
   `SITE_URL`.
6. Restart SWAG.

Then open https://iglc.drevland.net and log in with `iglc` and the password. Give that login to whoever should see the preview.
The back office is at `/manage/` (pages, archive, committees, proceedings production, users), with the account from `createsuperuser`. Django's own admin is at `/django-admin/`, for superusers only, as a fallback.

## Conference sites

After an update that adds a conference, create its website in the back office (Conferences → All conferences → the conference →
Add child page → Conference home page), or for a quick start:
`docker exec -it iglc-web python manage.py seed_conference_site 35 --current`
(the conference must be in the archive with its dates). See `docs/conference-sites.md`.

## Updating

In `/mnt/user/appdata/iglc/src`, run `git pull`, then the `up -d --build` command again.
```sh
cd /mnt/user/appdata/iglc/src
git pull 
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

## Backups

The database lives in `/mnt/user/appdata/iglc/postgres` and uploaded files in `/mnt/user/appdata/iglc/media`;
an appdata backup covers both. For a portable copy of the database:
`docker exec iglc-db pg_dump -U iglc iglc > iglc-backup.sql`.
