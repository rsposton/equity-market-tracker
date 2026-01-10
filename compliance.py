from __future__ import annotations

import logging
from datetime import date


COMPLIANCE_DUMMY = True


logger = logging.getLogger(__name__)
logger.warning("Using dummy compliance module; check_safety always returns True.")


def check_safety(ticker: str, as_of: date) -> bool:
    """Placeholder compliance check; returns True for all tickers."""
    return True
