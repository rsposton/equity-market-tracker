from decimal import Decimal

from engine import propose_trades


def _base_payload(lots, replacement_prices=None, portfolio_value=None):
    payload = {
        "lots": lots,
        "replacement_prices": replacement_prices or {},
    }
    if portfolio_value is not None:
        payload["portfolio_value"] = portfolio_value
    return payload


def test_turnover_clipping():
    lots = []
    losses = [50, 40, 30, 20, 10]
    for index, loss in enumerate(losses):
        lots.append(
            {
                "symbol": f"SYM{index}",
                "qty": 1,
                "cost_basis_per_share": 150,
                "current_price": 100,
                "unrealized_pl_pct": -0.3333,
                "sector": "Tech",
            }
        )
        lots[-1]["cost_basis_per_share"] = 100 + loss
    payload = _base_payload(lots, replacement_prices={"QQQ": 100}, portfolio_value=1000)

    result = propose_trades(payload)
    sells = [trade for trade in result["trades"] if trade["action"] == "sell"]

    assert len(sells) == 2
    assert {trade["symbol"] for trade in sells} == {"SYM0", "SYM1"}
    total_sell_value = sum(Decimal(trade["price"]) * Decimal(trade["qty"]) for trade in sells)
    assert total_sell_value == Decimal("200")


def test_excluded_sector_reinvestment(tmp_path):
    exclusions_path = tmp_path / "exclusions.json"
    exclusions_path.write_text('{"sectors": ["pharma"], "tickers": ["XYZ"]}')

    lots = [
        {
            "symbol": "PFE",
            "qty": 10,
            "cost_basis_per_share": 50,
            "current_price": 40,
            "unrealized_pl_pct": -0.2,
            "sector": "Pharma",
        }
    ]

    payload = _base_payload(lots, replacement_prices={"SCHX": 50}, portfolio_value=5000)
    result = propose_trades(payload, exclusions_path=exclusions_path)

    sells = [trade for trade in result["trades"] if trade["action"] == "sell"]
    buys = [trade for trade in result["trades"] if trade["action"] == "buy"]

    assert len(sells) == 1
    assert len(buys) == 1
    assert buys[0]["symbol"] == "SCHX"


def test_drawdown_toggle():
    lot = {
        "symbol": "ABC",
        "qty": 5,
        "cost_basis_per_share": 100,
        "current_price": 94,
        "unrealized_pl_pct": -0.055,
        "sector": "Industrials",
    }
    payload = _base_payload([lot], replacement_prices={"XLI": 50}, portfolio_value=5000)

    standard = propose_trades(payload, drawdown_mode=False)
    drawdown = propose_trades(payload, drawdown_mode=True)

    assert standard["trades"] == []
    assert len(drawdown["trades"]) == 2


def test_wash_sale_substantially_identical_blocks_buy():
    lot = {
        "symbol": "CORE",
        "qty": 2,
        "cost_basis_per_share": 120,
        "current_price": 100,
        "unrealized_pl_pct": -0.1667,
        "sector": "Broad",
    }
    payload = _base_payload([lot], replacement_prices={"SCHX": 50}, portfolio_value=200)

    registry = {
        "recent_sales": {"FNDX": "2025-01-01"},
        "substantially_identical": {"SCHX": ["FNDX"]},
    }

    result = propose_trades(payload, wash_sale_registry=registry)
    buys = [trade for trade in result["trades"] if trade["action"] == "buy"]

    assert buys == []


def test_share_precision_four_decimals():
    lot = {
        "symbol": "TECH",
        "qty": 3,
        "cost_basis_per_share": 50,
        "current_price": 33.3333,
        "unrealized_pl_pct": -0.3333,
        "sector": "Tech",
    }
    payload = _base_payload([lot], replacement_prices={"QQQ": 10}, portfolio_value=1000)

    result = propose_trades(payload)
    buy = next(trade for trade in result["trades"] if trade["action"] == "buy")

    assert buy["qty"].endswith("0000")


def test_drawdown_capacity():
    lots = []
    for i in range(4):
        lots.append(
            {
                "symbol": f"DD{i}",
                "qty": 5,
                "cost_basis_per_share": 106,
                "current_price": 100,
                "unrealized_pl_pct": -0.06,
                "sector": "Tech",
            }
        )
    payload = _base_payload(lots, replacement_prices={"QQQ": 100}, portfolio_value=5000)

    standard = propose_trades(payload, drawdown_mode=False)
    drawdown = propose_trades(payload, drawdown_mode=True)

    standard_sells = [trade for trade in standard["trades"] if trade["action"] == "sell"]
    drawdown_sells = [trade for trade in drawdown["trades"] if trade["action"] == "sell"]

    assert len(standard_sells) == 2
    assert len(drawdown_sells) == 4
