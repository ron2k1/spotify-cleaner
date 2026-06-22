# spotify-cleaner

Find the songs you barely listen to and clear them out of your Liked Songs and
playlists.

Anyone can run this: you create your own free Spotify app (one dashboard click),
paste the two credentials into `.env`, and the tool talks only to your account.
Your login token stays on your machine in a gitignored cache. Nobody else, including
this project, ever sees it.

## The one thing you need to know first

**Spotify's API does not expose your personal play counts.** Your desktop app
shows them; the API hides them. So "least listened" has to come from one of
three sources, and you pick which one:

| `--source`   | True play counts?      | Setup                                   | Best for |
|--------------|------------------------|-----------------------------------------|----------|
| `toptracks`  | No (top-50 vs not)     | none                                    | a fast first pass right now |
| `gdpr`       | Yes (lifetime + dates) | request your data export, wait a bit    | the real, accurate cleanup |
| `lastfm`     | Yes (scrobbles only)   | needs prior Last.fm scrobbling          | if you already scrobble |

The reading and removing machinery is identical for all three. Only the
score source differs — that is the `Scorer` strategy you select.

## Install

```bash
cd spotify-cleaner
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e .
cp .env.example .env              # then fill in your Spotify app credentials
```

Create a Spotify app at <https://developer.spotify.com/dashboard>, and add the
redirect URI `http://127.0.0.1:8888/callback` exactly. Your developer account
must be Premium (a 2026 dev-mode requirement).

## Use

Everything is a **dry run by default** — it only prints candidates. Nothing is
deleted unless you pass `--apply` *and* type `DELETE` at the prompt.

```bash
# Zero-setup first look: liked songs that aren't in your all-time top tracks
spotify-cleaner --source toptracks

# The accurate version, once your export has arrived (see below)
spotify-cleaner --source gdpr --gdpr-dir ./streaming_history --min-plays 1 --stale-days 365

# If you scrobble to Last.fm
spotify-cleaner --source lastfm --lastfm-user yourname --min-plays 2

# Actually remove them (asks for confirmation):
spotify-cleaner --source gdpr --gdpr-dir ./streaming_history --min-plays 1 \
    --apply --unlike --remove-from-playlists
```

Useful flags: `--all-tracks` (consider playlist tracks too, not just Liked
Songs), `--limit N` (how many to print), `--time-range short_term|medium_term|long_term`.

## Getting the GDPR export (the accurate source)

1. <https://www.spotify.com/account/privacy/> → tick **only** "Extended
   streaming history" (not "Account data", which is just the last year).
2. Wait. Usually hours to a few days; Spotify quotes up to 30.
3. Unzip the email's download. Point `--gdpr-dir` at the folder of
   `Streaming_History_Audio_*.json` files.

It computes true lifetime play counts *and* last-played dates, so
`--min-plays` finds "added once, never played" and `--stale-days` finds
"used to love it, dead for years".

## Safety

- Dry run unless `--apply`; even then it requires typing `DELETE`.
- Only touches playlists **you own**.
- `--unlike` and `--remove-from-playlists` are independent opt-ins.
- Removed-from-playlist tracks are not deleted from Spotify; unliked tracks can
  be re-liked. Still: review the printed list before confirming.
- Every operation is idempotent. If a run is interrupted (network drop, rate
  limit), it prints how far it got — just re-run the exact same command to
  finish. Already-removed tracks are skipped, so nothing is double-handled.

## Develop

```bash
pip install -e ".[dev]"
pytest                            # logic + parser tests, no account needed
```

Layout: `auth`/`library` (Spotify I/O) · `scoring/` (the pluggable sources) ·
`planner` (pure candidacy logic, fully tested) · `cleaner` (the guarded
deletes) · `cli` (wiring).

## License

MIT. See [LICENSE](LICENSE). Not affiliated with or endorsed by Spotify.
