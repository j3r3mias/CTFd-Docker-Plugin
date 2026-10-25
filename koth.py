"""
King of the Hill: challenges scored from an external ranking endpoint.

Every koth_interval seconds the plugin GETs koth_url and sets each team's
points on the challenge to the value the endpoint reports. Each team has one
award per KotH challenge, updated in place, so the scoreboard always shows the
current ranking instead of a pile of awards. Nothing is solved and there are
no flags.

The tick only runs while the CTF is running (not before start, paused, or
after the scoreboard freeze), and the last one is koth_stop_before minutes
(default 60) before the CTF end: from then on the ranking is final. A failing
endpoint keeps the last values; a team missing from the response keeps its
last value too.
"""
import logging
import time
from datetime import datetime, timedelta

import requests
from CTFd.cache import clear_challenges, clear_standings
from CTFd.models import Awards, Challenges, Teams, Users, db
from CTFd.plugins.challenges import BaseChallenge
from CTFd.utils import get_config
from CTFd.utils.dates import ctf_paused, ctftime, unix_time_to_utc
from CTFd.utils.user import get_current_team, get_current_user, is_admin

from .models.koth import KothChallenge, KothScore
from .team_flag import _key

logger = logging.getLogger(__name__)

#: Fields of the challenge.yml "extra" section (ctfcli sends them as is)
KOTH_FIELDS = (
    'koth_url', 'koth_token', 'koth_interval', 'koth_stop_before',
    'koth_results_key', 'koth_name_field', 'koth_points_field',
)
MIN_INTERVAL = 60
UNKNOWN = 'unknown teams: '
REQUEST_TIMEOUT = 10


class KothChallengeType(BaseChallenge):
    id = "koth"
    name = "koth"
    templates = {
        "create": "/plugins/containers/assets/koth/create.html",
        "update": "/plugins/containers/assets/koth/update.html",
        "view": "/plugins/containers/assets/koth/view.html",
    }
    scripts = {
        "create": "/plugins/challenges/assets/create.js",
        "update": "/plugins/challenges/assets/update.js",
        "view": "/plugins/challenges/assets/view.js",
    }
    challenge_model = KothChallenge

    @staticmethod
    def _clean(data):
        data = {k: v for k, v in dict(data).items() if k not in ('initial', 'decay', 'minimum', 'function')}
        if 'koth_interval' in data:
            try:
                data['koth_interval'] = max(MIN_INTERVAL, int(data['koth_interval']))
            except (TypeError, ValueError):
                data['koth_interval'] = 600
        if 'koth_stop_before' in data:
            try:
                data['koth_stop_before'] = max(0, int(data['koth_stop_before']))
            except (TypeError, ValueError):
                data['koth_stop_before'] = 60
        for k in ('koth_url', 'koth_token', 'koth_results_key', 'koth_name_field', 'koth_points_field'):
            if k in data and data[k] is not None:
                data[k] = str(data[k]).strip()
        return data

    @classmethod
    def create(cls, request):
        data = cls._clean(request.form or request.get_json())
        challenge = cls.challenge_model(**data)
        db.session.add(challenge)
        db.session.commit()
        return challenge

    @classmethod
    def read(cls, challenge):
        data = super().read(challenge)
        # The endpoint is internal: only admins (and ctfcli with an admin
        # token) see it
        if is_admin():
            for k in KOTH_FIELDS:
                data[k] = getattr(challenge, k)
            data['koth_last_check'] = (
                challenge.koth_last_check.isoformat() if challenge.koth_last_check else None
            )
            data['koth_last_error'] = challenge.koth_last_error or ''
        return data

    @classmethod
    def update(cls, challenge, request):
        data = cls._clean(request.form or request.get_json())
        for attr, value in data.items():
            setattr(challenge, attr, value)
        db.session.commit()
        return challenge

    @classmethod
    def delete(cls, challenge):
        for score in KothScore.query.filter_by(challenge_id=challenge.id).all():
            if score.award_id:
                Awards.query.filter_by(id=score.award_id).delete()
        KothScore.query.filter_by(challenge_id=challenge.id).delete()
        db.session.commit()
        super().delete(challenge)
        clear_standings()

    @classmethod
    def attempt(cls, challenge, request):
        return False, "This challenge is scored automatically"


def current_points(challenge_id):
    """Points of the current account on a KotH challenge, for the view."""
    team_mode = get_config('user_mode') == 'teams'
    account = get_current_team() if team_mode else get_current_user()
    if account is None:
        return None
    score = KothScore.query.filter_by(challenge_id=challenge_id, account_id=account.id).first()
    return score.points if score else 0


class KothService:
    def __init__(self, notification_service=None):
        self.notification_service = notification_service

    # ------------------------------------------------------------------
    @staticmethod
    def _running():
        if not ctftime() or ctf_paused():
            return False
        freeze = get_config('freeze')
        if freeze and datetime.utcnow() >= unix_time_to_utc(freeze):
            return False
        return True

    @staticmethod
    def _closed(challenge):
        """True from koth_stop_before minutes before the CTF end onwards."""
        end = get_config('end')
        if not end:
            return False
        stop = challenge.koth_stop_before if challenge.koth_stop_before is not None else 60
        return time.time() >= int(end) - stop * 60

    @staticmethod
    def _claim(challenge, now):
        """
        Mark the tick as taken. Every CTFd worker runs this job; the
        conditional UPDATE lets only one of them fetch the endpoint.
        """
        due = now - timedelta(seconds=max(MIN_INTERVAL, challenge.koth_interval or 600) - 5)
        claimed = KothChallenge.query.filter(
            KothChallenge.id == challenge.id,
            db.or_(KothChallenge.koth_last_check.is_(None), KothChallenge.koth_last_check <= due),
        ).update({'koth_last_check': now}, synchronize_session=False)
        db.session.commit()
        return claimed == 1

    @staticmethod
    def parse(challenge, payload):
        """{normalized name: (name, points)} from the endpoint JSON."""
        entries = payload
        if challenge.koth_results_key:
            if not isinstance(payload, dict) or challenge.koth_results_key not in payload:
                raise ValueError(f'"{challenge.koth_results_key}" not found in the response')
            entries = payload[challenge.koth_results_key]

        if isinstance(entries, dict):
            pairs = entries.items()
        elif isinstance(entries, list):
            name_field = challenge.koth_name_field or 'display_name'
            points_field = challenge.koth_points_field or 'total_points'
            pairs = []
            for entry in entries:
                if not isinstance(entry, dict) or name_field not in entry or points_field not in entry:
                    raise ValueError(f'entry without "{name_field}"/"{points_field}": {str(entry)[:100]}')
                pairs.append((entry[name_field], entry[points_field]))
        else:
            raise ValueError('expected a list or an object of scores')

        scores = {}
        for name, points in pairs:
            try:
                scores[_key(str(name))] = (str(name), int(round(float(points))))
            except (TypeError, ValueError):
                raise ValueError(f'invalid points for "{name}": {points!r}')
        return scores

    def fetch(self, challenge):
        headers = {'Accept': 'application/json'}
        if challenge.koth_token:
            headers['Authorization'] = challenge.koth_token
        r = requests.get(challenge.koth_url, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return self.parse(challenge, r.json())

    @staticmethod
    def apply(challenge, scores):
        """Set each known account's award to its points. Returns unknown names."""
        team_mode = get_config('user_mode') == 'teams'
        model = Teams if team_mode else Users
        accounts = {_key(a.name): a for a in model.query.all()}
        existing = {s.account_id: s for s in KothScore.query.filter_by(challenge_id=challenge.id).all()}
        now = datetime.utcnow()
        unknown = []

        for key, (name, points) in scores.items():
            account = accounts.get(key)
            if account is None:
                unknown.append(name)
                continue

            score = existing.get(account.id)
            award = Awards.query.get(score.award_id) if score and score.award_id else None
            if award is not None and award.value == points:
                continue

            if award is None:
                if team_mode:
                    user_id = account.captain_id or next((m.id for m in account.members), None)
                    award = Awards(user_id=user_id, team_id=account.id)
                else:
                    award = Awards(user_id=account.id)
                award.name = challenge.name[:80]
                award.description = 'King of the Hill'
                award.category = (challenge.category or '')[:80]
                award.icon = 'crown'
                db.session.add(award)
                db.session.flush()

            # The date marks the last change: it is the tiebreak, like a solve
            award.value = points
            award.date = now
            if score is None:
                score = KothScore(challenge_id=challenge.id, account_id=account.id)
                db.session.add(score)
            score.award_id = award.id
            score.points = points
            score.updated_at = now

        db.session.commit()
        return unknown

    def tick(self):
        if not self._running():
            return
        now = datetime.utcnow()
        for challenge in KothChallenge.query.filter(KothChallenge.koth_url != '').all():
            if challenge.state == 'hidden' or self._closed(challenge):
                continue
            if not self._claim(challenge, now):
                continue
            previous_error = challenge.koth_last_error or ''
            try:
                scores = self.fetch(challenge)
                unknown = self.apply(challenge, scores)
                logger.info("KotH %s: %s scores read", challenge.id, len(scores))
                error = f'{UNKNOWN}{", ".join(sorted(unknown))}' if unknown else ''
                clear_standings()
                clear_challenges()
            except Exception as e:  # noqa: BLE001
                db.session.rollback()
                error = f'{type(e).__name__}: {e}'[:500]
                logger.error("KotH %s (%s): %s", challenge.id, challenge.koth_url, error)
                # Only on the transition to failing, not every tick
                failing = previous_error and not previous_error.startswith(UNKNOWN)
                if not failing and self.notification_service:
                    try:
                        self.notification_service.notify_error(f'KotH "{challenge.name}"', error)
                    except Exception:  # noqa: BLE001
                        pass

            if error != previous_error:
                KothChallenge.query.filter_by(id=challenge.id).update(
                    {'koth_last_error': error}, synchronize_session=False)
                db.session.commit()


def scoreboard_points():
    """
    {challenge_id: {account_id: points}} for the scoreboard matrix: the
    awards in the scoreboard data do not say which challenge they came from.

    Same rules as the CTFd scoreboard: hidden challenges and hidden or banned
    accounts are left out for players, and so is an award last changed at or
    after the freeze (the tick stops at the freeze, so this only matters if
    the freeze time is moved back).
    """
    admin = is_admin()
    team_mode = get_config('user_mode') == 'teams'
    model = Teams if team_mode else Users

    query = db.session.query(KothScore.challenge_id, KothScore.account_id, Awards.value, Awards.date) \
        .join(Awards, Awards.id == KothScore.award_id) \
        .join(Challenges, Challenges.id == KothScore.challenge_id) \
        .join(model, model.id == KothScore.account_id)
    if not admin:
        query = query.filter(Challenges.state == 'visible', model.hidden.is_(False), model.banned.is_(False))
        freeze = get_config('freeze')
        if freeze:
            query = query.filter(Awards.date < unix_time_to_utc(freeze))

    points = {}
    for challenge_id, account_id, value, _ in query.all():
        points.setdefault(challenge_id, {})[account_id] = value
    return points
