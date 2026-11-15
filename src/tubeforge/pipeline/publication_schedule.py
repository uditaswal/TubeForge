"""Cadence warnings and local slot defaults for reviewed deliveries."""
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select

from tubeforge.db.models import DestinationDeliveryRecord, SocialAccountRecord
from tubeforge.pipeline.channel_reports import ChannelSafetyConfig, cadence_report


class CadenceConfirmationRequired(ValueError):
    def __init__(self, warnings):
        super().__init__('cadence warnings require an explicit override')
        self.warnings = warnings


def default_slots(day: date) -> list[datetime]:
    timezone = ZoneInfo('Asia/Kolkata')
    return [datetime.combine(day, time(hour), tzinfo=timezone) for hour in (13, 19)]


def cadence_warnings(session, deliveries, scheduled_for: datetime, config: ChannelSafetyConfig):
    """Apply the M-S7 rules to scheduled delivery history per destination account."""
    account_ids = {item.account_id for item in deliveries}
    accounts = {account.id: account for account in session.scalars(select(SocialAccountRecord).where(SocialAccountRecord.id.in_(account_ids)))}
    prior = list(session.scalars(select(DestinationDeliveryRecord).where(
        DestinationDeliveryRecord.account_id.in_(account_ids),
        DestinationDeliveryRecord.scheduled_for.is_not(None),
        DestinationDeliveryRecord.state.not_in({'cancelled', 'missed', 'failed', 'draft'}),
        DestinationDeliveryRecord.id.not_in([item.id for item in deliveries]),
    )))
    effective = config.model_copy(update={'channels': {
        account_id: config.channels.get(accounts[account_id].display_name, config.defaults)
        for account_id in account_ids if account_id in accounts
    }})
    items = []
    for item in prior:
        stamp = item.scheduled_for
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        items.append({'id': item.id, 'channel': item.account_id, 'publish_at': stamp.isoformat()})
    for item in deliveries:
        items.append({'id': item.id, 'channel': item.account_id, 'publish_at': scheduled_for.isoformat()})
    candidates = {item.id for item in deliveries}
    return [warning for warning in cadence_report(items, effective)['warnings'] if candidates.intersection(warning['ids'])]
