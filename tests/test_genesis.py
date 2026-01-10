from decimal import Decimal

from genesis import build_genesis_portfolio_from_holdings


def _make_holding(symbol, weight, sector):
    return {
        "symbol": symbol,
        "weightPercentage": weight,
        "sector": sector,
        "price": 100,
    }


def _build_holdings(count=130):
    holdings = []
    for idx in range(count):
        symbol = f"SYM{idx:03d}"
        weight = 1
        sector = "Information Technology" if idx % 2 == 0 else "Financials"
        holdings.append(_make_holding(symbol, weight, sector))
    return holdings


def test_genesis_math():
    holdings = _build_holdings(200)
    prices = {item["symbol"]: Decimal("100") for item in holdings}
    prices["SCHX"] = Decimal("100")

    result = build_genesis_portfolio_from_holdings(
        holdings=holdings,
        total_cash=250000,
        price_lookup=prices,
    )

    total = sum(Decimal(str(order["dollar_amount"])) for order in result["orders"])
    assert Decimal("248500") <= total <= Decimal("249000")


def test_exclusion_redirect(tmp_path):
    holdings = _build_holdings(130)
    holdings[0]["symbol"] = "EXCL"
    holdings[0]["weightPercentage"] = 2
    holdings[0]["sector"] = "Health Care"

    exclusions_path = tmp_path / "exclusions.json"
    exclusions_path.write_text('{"sectors": [], "tickers": ["EXCL"]}')

    prices = {item["symbol"]: Decimal("100") for item in holdings}
    prices["XLV"] = Decimal("100")
    prices["SCHX"] = Decimal("100")

    result = build_genesis_portfolio_from_holdings(
        holdings=holdings,
        total_cash=250000,
        exclusions_path=exclusions_path,
        price_lookup=prices,
    )

    symbols = {order["symbol"] for order in result["orders"]}
    assert "EXCL" not in symbols

    redirected = result["report"]["redirected"]
    assert redirected
    assert redirected[0]["symbol"] == "EXCL"
    assert redirected[0]["etf"] == "XLV"

    xlv_order = next(order for order in result["orders"] if order["symbol"] == "XLV")
    redirected_amount = Decimal(str(redirected[0]["dollar_amount"]))
    assert Decimal(str(xlv_order["dollar_amount"])) >= redirected_amount
