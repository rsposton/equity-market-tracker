import json
from decimal import Decimal
from pathlib import Path

import pytest

from ingestor import WASH_SALE_INDEX, parse_schwab_positions, parse_schwab_transactions


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_standard_import():
    positions_path = FIXTURES_DIR / "mock_positions.csv"
    lots = parse_schwab_positions(str(positions_path))

    assert len(lots) == 3
    assert lots[0]["symbol"] == "AAPL"
    assert lots[0]["qty"] == 100.0
    assert lots[0]["acquisition_date"] == "2026-01-09"


def test_empty_file(tmp_path: Path):
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text(
        "Positions for Account XXXX-1234 as of 01/09/2026,,,\n"
        "Symbol,Description,Quantity,Price,Cost Basis Per Share,Total Cost Basis,Gain/Loss %\n"
    )

    with pytest.raises(ValueError, match="no position rows"):
        parse_schwab_positions(str(empty_path))


def test_data_integrity():
    positions_path = FIXTURES_DIR / "mock_positions.csv"
    lots = parse_schwab_positions(str(positions_path))

    for lot in lots:
        calculated = lot["qty"] * lot["cost_basis_per_share"]
        assert abs(calculated - lot["total_cost_basis"]) <= 0.01


def test_malformed_currency(tmp_path: Path):
    malformed_path = tmp_path / "malformed.csv"
    malformed_path.write_text(
        "Positions for Account XXXX-1234 as of 01/09/2026,,,\n"
        "Symbol,Description,Quantity,Price,Cost Basis Per Share,Total Cost Basis,Gain/Loss %\n"
        "TSLA,TESLA INC,5,195.00,200.00,\"1,000.00\",-2.5%\n"
    )

    lots = parse_schwab_positions(str(malformed_path))

    assert lots[0]["current_price"] == 195.0
    assert lots[0]["total_cost_basis"] == 1000.0


def test_golden_file_regression():
    positions_path = FIXTURES_DIR / "mock_positions.csv"
    golden_path = FIXTURES_DIR / "golden_positions.json"

    lots = parse_schwab_positions(str(positions_path))
    golden = json.loads(golden_path.read_text())

    assert lots == golden


def test_positions_with_preamble_and_alias_headers():
    positions_path = FIXTURES_DIR / "mock_positions_with_preamble.csv"
    lots = parse_schwab_positions(str(positions_path))

    assert len(lots) == 1
    assert lots[0]["symbol"] == "FNDX"
    assert lots[0]["acquisition_date"] == "2026-01-10"
    assert lots[0]["qty"] == 1488.0
    assert lots[0]["current_price"] == 28.12
    assert lots[0]["total_cost_basis"] == 25897.69
    assert lots[0]["unrealized_pl_pct"] == 0.6157


def test_dividend_reinvestment_loop(tmp_path: Path):
    payload = {
        "BrokerageTransactions": [
            {
                "Date": "03/03/2025",
                "Action": "Qualified Dividend",
                "Symbol": "FNDX",
                "Quantity": "",
                "Price": "",
                "Amount": "5.00",
                "ItemIssueId": "div-1",
            },
            {
                "Date": "03/03/2025",
                "Action": "Qual Div Reinvest",
                "Symbol": "FNDX",
                "Quantity": "0.5000",
                "Price": "10.00",
                "Amount": "5.00",
                "ItemIssueId": "reinv-1",
            },
        ]
    }
    path = tmp_path / "transactions.json"
    path.write_text(json.dumps(payload))

    adjustments = parse_schwab_transactions(str(path))

    assert adjustments[0]["cash_delta"] == Decimal("5.00")
    assert adjustments[1]["cash_delta"] == Decimal("-5.00")
    assert adjustments[1]["lot_delta"] == Decimal("0.5000")


def test_reverse_split(tmp_path: Path):
    payload = {
        "BrokerageTransactions": [
            {
                "Date": "04/01/2025",
                "Action": "Reverse Split",
                "Symbol": "XYZ",
                "Quantity": "-274",
                "Price": "",
                "Amount": "",
                "ItemIssueId": "split-1",
            },
            {
                "Date": "04/01/2025",
                "Action": "Reverse Split",
                "Symbol": "XYZ",
                "Quantity": "27",
                "Price": "",
                "Amount": "",
                "ItemIssueId": "split-2",
            },
        ]
    }
    path = tmp_path / "transactions.json"
    path.write_text(json.dumps(payload))

    adjustments = parse_schwab_transactions(str(path))

    assert len(adjustments) == 1
    assert adjustments[0]["cost_basis_multiplier"] == Decimal("10")
    assert adjustments[0]["quantity_before"] == Decimal("274")
    assert adjustments[0]["quantity_after"] == Decimal("27")


def test_merger_liquidation(tmp_path: Path):
    payload = {
        "BrokerageTransactions": [
            {
                "Date": "05/15/2025",
                "Action": "Cash Merger",
                "Symbol": "ABC",
                "Quantity": "10",
                "Price": "",
                "Amount": "123.45",
                "ItemIssueId": "merge-1",
            }
        ]
    }
    path = tmp_path / "transactions.json"
    path.write_text(json.dumps(payload))

    adjustments = parse_schwab_transactions(str(path))

    assert adjustments[0]["cash_delta"] == Decimal("123.45")
    assert adjustments[0]["lot_delta"] == Decimal("-10")


def test_wash_sale_indexing(tmp_path: Path):
    payload = {
        "BrokerageTransactions": [
            {
                "Date": "06/01/2025",
                "Action": "Sell",
                "Symbol": "AAPL",
                "Quantity": "5",
                "Price": "200.00",
                "Amount": "1000.00",
                "ItemIssueId": "sell-1",
            }
        ]
    }
    path = tmp_path / "transactions.json"
    path.write_text(json.dumps(payload))

    parse_schwab_transactions(str(path))

    assert WASH_SALE_INDEX["AAPL"][0]["quantity"] == Decimal("5")
