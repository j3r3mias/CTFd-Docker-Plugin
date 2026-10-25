"""
King of the Hill challenge models
"""
from datetime import datetime

from CTFd.models import Challenges, db


class KothChallenge(Challenges):
    """
    A challenge scored from an external ranking endpoint instead of flags.

    Every tick the plugin reads the endpoint and sets each account's points
    for this challenge to the value it reports (one award per account, updated
    in place). The endpoint fields are admin only: players never receive them.
    """
    __tablename__ = 'koth_challenges'
    __mapper_args__ = {"polymorphic_identity": "koth"}

    id = db.Column(
        db.Integer,
        db.ForeignKey("challenges.id", ondelete="CASCADE"),
        primary_key=True
    )

    koth_url = db.Column(db.Text, default='')
    koth_token = db.Column(db.Text, default='')        # sent as the Authorization header
    koth_interval = db.Column(db.Integer, default=600)  # seconds between ticks
    # The last tick is this many minutes before the CTF end; the ranking is
    # final from then on
    koth_stop_before = db.Column(db.Integer, default=60)

    # Where the scores are in the JSON. With the defaults:
    #   {"results": [{"display_name": "Team", "total_points": 200}, ...]}
    # An object of {"Team": points} also works (koth_results_key may be empty).
    koth_results_key = db.Column(db.String(64), default='results')
    koth_name_field = db.Column(db.String(64), default='display_name')
    koth_points_field = db.Column(db.String(64), default='total_points')

    koth_last_check = db.Column(db.DateTime)
    koth_last_error = db.Column(db.Text, default='')


class KothScore(db.Model):
    """The award that holds one account's points on one KotH challenge."""
    __tablename__ = 'koth_scores'

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer,
        db.ForeignKey('challenges.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    account_id = db.Column(db.Integer, nullable=False)
    award_id = db.Column(db.Integer, db.ForeignKey('awards.id', ondelete='SET NULL'))
    points = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('challenge_id', 'account_id', name='uq_koth_score_account'),
    )
