from __future__ import annotations

from datetime import date, timedelta

from compliance import WASH_SALE_WINDOW, check_safety, get_locked_tickers, record_harvest


def test_exact_window_unlock(tmp_path):
    db_path = tmp_path / "wash_sale.db"
    sell_date = date(2023, 1, 1)
    record_harvest("AAPL", 10, sell_date, db_path=db_path)

    assert check_safety("AAPL", date(2023, 1, 31), db_path=db_path) is False
    assert check_safety("AAPL", date(2023, 2, 1), db_path=db_path) is True


def test_multiple_harvests(tmp_path):
    db_path = tmp_path / "wash_sale.db"
    first_sell = date(2023, 1, 10)
    second_sell = date(2023, 2, 15)

    record_harvest("AAPL", 5, first_sell, db_path=db_path)
    record_harvest("AAPL", 7, second_sell, db_path=db_path)

    latest_unlock = second_sell + timedelta(days=WASH_SALE_WINDOW)

    assert check_safety("AAPL", latest_unlock - timedelta(days=1), db_path=db_path) is False
    assert check_safety("AAPL", latest_unlock, db_path=db_path) is True
    assert check_safety("AAPL", latest_unlock + timedelta(days=1), db_path=db_path) is True


def test_database_persistence(tmp_path):
    db_path = tmp_path / "wash_sale.db"
    record_harvest("MSFT", 12, date(2023, 6, 1), db_path=db_path)

    assert db_path.exists()
    assert check_safety("MSFT", date(2023, 6, 15), db_path=db_path) is False

    locked = get_locked_tickers(current_date=date(2023, 6, 15), db_path=db_path)
    assert locked == ["MSFT"]
