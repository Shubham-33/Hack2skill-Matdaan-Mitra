# Squad + Calendar + Share — Directive

> Implements the "team collaboration" feature using URL-spec dispatch (no OAuth) per hackathon-playbook rule #3.

## Goal
Let a user create a Voting Squad, share an invite via WhatsApp, track 3 checkboxes per member, and add the polling-day event to everyone's Google Calendar — all without a single OAuth flow.

## Inputs
- `POST /api/squad` body: `{ name, state, constituency, polling_date }` → creates row in `Squads` sheet, returns `squad_id`
- `GET /squad/<squad_id>` → join page
- `POST /api/squad/<squad_id>/checkin` body: `{ member_name, registered, researched, voted }`

## Tools
- `web/app.py` routes above
- Sheets API for `Squads` tab: `squad_id | name | state | constituency | polling_date | members_json | created_at`
- URL-spec dispatch (no OAuth, no SDK):
  - **Calendar**: `https://calendar.google.com/calendar/render?action=TEMPLATE&text=<title>&dates=<YYYYMMDDTHHMMSS>/<YYYYMMDDTHHMMSS>&details=<body>&location=<addr>`
  - **WhatsApp share**: `https://wa.me/?text=<encoded message>`
  - **Maps**: `https://maps.google.com/?q=<lat>,<lng>` or `?q=<address>`

## Outputs
- Squad join URL: `<base>/squad/<squad_id>`
- Calendar deeplink (opens user's logged-in tab, click Save)
- WhatsApp deeplink (opens user's WhatsApp with prefilled text)
- Maps deeplink (opens for the polling station)

## Edge cases & rules
- **Squad ID = auth**: 12-char URL-safe random token. No login required. Anyone with link can join. Acceptable trade-off for hackathon (privacy: nothing sensitive in squad).
- **Concurrent member updates**: Sheet writes aren't transactional. Use `range='Squads!F<row>:F<row>'` get-then-set with version field; on conflict, retry once. Acceptable race for demo (last-write-wins).
- **Polling date in past**: still allow squad creation (post-mortem use case), but show "election has passed" badge.
- **`wa.me` on desktop without WhatsApp Web**: opens web.whatsapp.com — works fine.
- **Calendar URL-spec date format**: `YYYYMMDDTHHMMSSZ` (UTC) — verify with a sample before demo.
- **Be honest in pitch**: per playbook, judges respect URL-spec dispatch. Don't pretend it's deep API integration.

## Self-anneal log
- (none yet)
