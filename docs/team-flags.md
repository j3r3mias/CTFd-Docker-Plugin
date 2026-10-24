# Team flags

A flag type, `team`, for challenges that are **not** containers: the files are
the same for everyone, but each team ends up with its own predetermined flag.
Each flag row holds one team's flag and that team's name. A submission only
counts when it is the submitter's own team flag.

Submitting another team's flag gets `Incorrect` and is handled like a reused
container flag: a row in the cheat log, a `flag_reuse_detected` audit entry,
the Discord alert and, if set, the auto-ban threshold. See
[anti-cheat.md](anti-cheat.md). A wrong flag that belongs to nobody is just
`Incorrect`, with no detection.

The type works with the `standard` and `dynamic` challenge types. Container
challenges validate their own flags and ignore it.

## Adding the flags

In the admin, **Flags, Add flag**, pick `team` and fill the flag and the team
name. Repeat for every team.

With ctfcli, one entry per team in `challenge.yml`:

```yaml
flags:
  - type: team
    content: "IDP{8f3a...}"
    data: "Nome do Time 1"
  - type: team
    content: "IDP{c71e...}"
    data: "Nome do Time 2"
```

- `data` is the team name as registered. Case and repeated spaces are ignored,
  the same rule the team registration script uses.
- In user mode, `data` is the user name.
- A team with no flag cannot solve the challenge. Add the flags after the teams
  exist, and check that every team has one.
- A flag that names a team that does not exist never matches. CTFd logs an
  error with the flag id.
- Give every team a different flag. If two teams share one, it still solves
  for both, but each submission also logs a false reuse against the other team.
