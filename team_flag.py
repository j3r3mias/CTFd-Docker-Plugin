"""
Team flag: a predetermined flag per team, on any challenge type.

Each flag row holds one team's flag (content) and the team's name (data). A
submission only matches the flag of the submitter's own team. Matching another
team's flag counts as flag reuse: "Incorrect" for the player, and the same
cheat log, Discord alert and auto-ban rule as the container challenges.
"""
import hmac
import logging
from types import SimpleNamespace

from flask import has_request_context, request

from CTFd.models import Challenges, Teams, Users
from CTFd.plugins.flags import BaseFlag
from CTFd.utils import get_config
from CTFd.utils.user import get_current_team, get_current_user

from .models.flag import ContainerFlagAttempt

logger = logging.getLogger(__name__)


def _key(name):
    """Same team-name normalization as the registration script (21)."""
    return ' '.join((name or '').split()).casefold()


class TeamFlag(BaseFlag):
    name = "team"
    templates = {
        "create": "/plugins/containers/assets/flags/team/create.html",
        "update": "/plugins/containers/assets/flags/team/edit.html",
    }

    #: Set by load(); reuse detection is skipped while it is missing.
    anticheat_service = None

    @staticmethod
    def _owner(flag, team_mode):
        model = Teams if team_mode else Users
        owner = model.query.filter_by(name=flag.data).first()
        if owner is None:
            wanted = _key(flag.data)
            owner = next((a for a in model.query.all() if _key(a.name) == wanted), None)
        return owner

    @staticmethod
    def compare(flag, provided):
        if not hmac.compare_digest(
            (flag.content or '').strip().encode(), (provided or '').strip().encode()
        ):
            return False

        team_mode = get_config('user_mode') == 'teams'
        user = get_current_user()
        account = get_current_team() if team_mode else user
        owner = TeamFlag._owner(flag, team_mode)

        if owner is None:
            logger.error(
                "Team flag %s of challenge %s names an unknown account: %r",
                flag.id, flag.challenge_id, flag.data,
            )
            return False
        if account is None or user is None:
            return False
        if account.id == owner.id:
            return True

        TeamFlag._report_reuse(flag, provided, user, account, owner)
        return False

    @staticmethod
    def _report_reuse(flag, provided, user, account, owner):
        service = TeamFlag.anticheat_service
        if service is None:
            logger.warning(
                "Account %s submitted the team flag of account %s (challenge %s)",
                account.id, owner.id, flag.challenge_id,
            )
            return

        ip = request.remote_addr if has_request_context() else None
        ua = request.headers.get('User-Agent') if has_request_context() else None
        attempt = ContainerFlagAttempt(
            challenge_id=flag.challenge_id,
            account_id=account.id,
            user_id=user.id,
            submitted_flag_hash=service.flag_service.hash_flag(provided.strip()),
            ip_address=ip,
            user_agent=ua,
        )
        challenge = Challenges.query.get(flag.challenge_id)
        # Same path as a reused container flag: log, alert and the auto-ban rule
        service._handle_flag_reuse(
            challenge,
            SimpleNamespace(account_id=owner.id, flag_status='team'),
            account.id, user.id, attempt, ip, ua, provided.strip(),
        )
