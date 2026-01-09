import json
from pathlib import Path

import pytest

from ingestor import parse_schwab_positions


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
