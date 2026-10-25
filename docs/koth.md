# King of the Hill

A challenge type, `koth`, scored from an external ranking instead of flags.
Every interval the plugin reads a JSON endpoint and sets each team's points on
the challenge to the value it reports. Each team has **one** award per KotH
challenge, updated in place, so the scoreboard always shows the current
ranking. Points may go up or down.

The endpoint is internal configuration: players never receive it (nor the
token) in the challenge page or the API. Admins see it in the challenge form.

## challenge.yml

```yaml
name: "Golf"
category: koth
description: "Envie a menor solução em https://golf-koth.desafio.idp-ctf.site"
value: 0                     # only shown on the card
type: koth
connection_info: https://golf-koth.desafio.idp-ctf.site
extra:
    koth_url: http://10.0.0.5:8080/api/ranking
    koth_interval: 600       # seconds, at least 60 (default 600)
    # koth_stop_before: 60                # last tick N minutes before the end (default 60)
    # koth_token: "Bearer ..."            # sent as the Authorization header
    # koth_results_key: results           # where the list is ("" = the JSON itself)
    # koth_name_field: display_name
    # koth_points_field: total_points
state: hidden
```

Accepted responses, with the defaults above:

```json
{"results": [{"display_name": "Time Alfa", "total_points": 200}, ...]}
```

or, with `koth_results_key: ""`, a plain object:

```json
{"Time Alfa": 200, "Time Beta": 80}
```

Other fields in the entries are ignored. Team names follow the team flag rule:
case and repeated spaces do not matter (user names in user mode).

## How a tick behaves

- It runs only while the CTF is running: not before the start, while paused,
  or after the scoreboard freeze. The last tick is `koth_stop_before` minutes
  (default 60) before the CTF end, so the ranking is final for the last hour
  and nothing changes after the end. A hidden challenge is skipped.
- Every CTFd worker runs the job, but only one of them fetches each tick.
- A team in the response gets its award set to the points (created on the
  first tick, with the challenge name and a crown icon). The award date is the
  last change, which is the tiebreak, like a solve.
- A team missing from the response keeps its last value. A name that matches
  no team is listed in the challenge's status (`unknown teams: ...`).
- A failing endpoint (timeout of 10 seconds, HTTP error, bad JSON) keeps every
  value. The error shows in the challenge form and goes to the Discord webhook
  once, when it starts failing.
- Flag submissions answer "This challenge is scored automatically".
- Deleting the challenge deletes its awards.

The scoreboard graph shows each award at its last change, not the history of
the ranking.

`GET /api/v1/containers/koth/scores` returns `{challenge_id: {account_id:
points}}` with the scoreboard rules (score and account visibility, hidden
challenges and accounts, freeze). The IDP theme uses it to show the points in
the KotH column of the scoreboard matrix.
