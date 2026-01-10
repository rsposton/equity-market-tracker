from __future__ import annotations

import logging
from datetime import date

from compliance import check_safety, record_harvest


def test_wash_sale_boundary_days(tmp_path):
    db_path = tmp_path / "wash_sale.db"
    record_harvest("AAPL", 10, date(2023, 1, 1), db_path=db_path)

    assert check_safety("AAPL", date(2023, 1, 31), db_path=db_path) is False
    assert check_safety("AAPL", date(2023, 2, 1), db_path=db_path) is True


def test_wash_sale_logs_on_day_30(tmp_path, caplog):
    db_path = tmp_path / "wash_sale.db"
    record_harvest("AAPL", 10, date(2023, 1, 1), db_path=db_path)

    caplog.set_level(logging.INFO)
    assert check_safety("AAPL", date(2023, 1, 31), db_path=db_path) is False

    assert "Wash sale lockout active for AAPL" in caplog.text
