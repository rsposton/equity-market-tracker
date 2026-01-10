from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional
from urllib.request import urlopen


DEFAULT_EXCLUSIONS_PATH = Path(__file__).with_name("exclusions.json")
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
SP500_PROXY = "VOO"
BROAD_MARKET_ETF = "SCHX"

SECTOR_ETF_MAP = {
    "communication services": "XLC",
    "consumer discretionary": "XLY",
    "consumer staples": "XLP",
    "energy": "XLE",
    "financials": "XLF",
    "health care": "XLV",
    "healthcare": "XLV",
    "industrials": "XLI",
    "information technology": "XLK",
    "materials": "XLB",
    "real estate": "XLRE",
    "technology": "XLK",
    "utilities": "XLU",
}


@dataclass(frozen=True)
class Allocation:
    symbol: str
    weight: Decimal
    sector: str
    is_etf: bool


def _as_decimal(value: float | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _format_shares(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):.4f}"


def _load_exclusions(path: Path = DEFAULT_EXCLUSIONS_PATH) -> dict:
    if not path.exists():
        return {"sectors": [], "tickers": []}
    return json.loads(path.read_text())


def _normalize_sector(sector: Optional[str]) -> str:
    return str(sector or "").strip().lower()


def _sector_etf(sector: str) -> str:
    return SECTOR_ETF_MAP.get(sector, BROAD_MARKET_ETF)


def _holding_symbol(holding: dict) -> str:
    return str(holding.get("symbol", "")).strip().upper()


def _holding_weight(holding: dict) -> Decimal:
    weight = holding.get("weightPercentage")
    if weight is None:
        weight = holding.get("weight")
    return _as_decimal(weight or 0)


def _holding_sector(holding: dict) -> str:
    return _normalize_sector(holding.get("sector"))


def _holding_price(holding: dict) -> Optional[Decimal]:
    if holding.get("price") not in (None, ""):
        return _as_decimal(holding.get("price"))
    market_value = holding.get("marketValue")
    shares = holding.get("sharesNumber")
    if market_value and shares:
        return _as_decimal(market_value) / _as_decimal(shares)
    return None


def _is_excluded(holding: dict, exclusions: dict) -> bool:
    symbol = _holding_symbol(holding)
    sector = _holding_sector(holding)
    excluded_tickers = {
        ticker.strip().upper() for ticker in exclusions.get("tickers", [])
    }
    excluded_sectors = {
        sector.strip().lower() for sector in exclusions.get("sectors", [])
    }
    return symbol in excluded_tickers or sector in excluded_sectors


def fetch_sp500_holdings(api_key: str, symbol: str = SP500_PROXY) -> list[dict]:
    url = f"{FMP_BASE_URL}/etf-holder/{symbol}?apikey={api_key}"
    with urlopen(url) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list):
        raise ValueError("Unexpected response payload from FMP")
    return payload


def fetch_quotes(api_key: str, symbols: Iterable[str]) -> dict[str, Decimal]:
    symbol_list = ",".join(sorted({symbol for symbol in symbols if symbol}))
    if not symbol_list:
        return {}
    url = f"{FMP_BASE_URL}/quote/{symbol_list}?apikey={api_key}"
    with urlopen(url) as response:
        payload = json.loads(response.read())
    prices: dict[str, Decimal] = {}
    for item in payload if isinstance(payload, list) else []:
        symbol = str(item.get("symbol", "")).upper()
        if not symbol:
            continue
        price = item.get("price")
        if price is None:
            continue
        prices[symbol] = _as_decimal(price)
    return prices


def build_genesis_portfolio(
    total_cash: float | Decimal,
    cash_buffer: float | Decimal = Decimal("0.005"),
    api_key: Optional[str] = None,
    exclusions_path: Path = DEFAULT_EXCLUSIONS_PATH,
) -> dict:
    api_key = api_key or os.getenv("FMP_API_KEY")
    if not api_key:
        raise ValueError("FMP_API_KEY is required to fetch holdings")
    holdings = fetch_sp500_holdings(api_key)
    return build_genesis_portfolio_from_holdings(
        holdings=holdings,
        total_cash=total_cash,
        cash_buffer=cash_buffer,
        exclusions_path=exclusions_path,
        api_key=api_key,
    )


def build_genesis_portfolio_from_holdings(
    holdings: Iterable[dict],
    total_cash: float | Decimal,
    cash_buffer: float | Decimal = Decimal("0.005"),
    exclusions_path: Path = DEFAULT_EXCLUSIONS_PATH,
    price_lookup: Optional[dict[str, float | Decimal]] = None,
    api_key: Optional[str] = None,
) -> dict:
    exclusions = _load_exclusions(exclusions_path)
    holdings_list = list(holdings)
    sorted_holdings = sorted(holdings_list, key=_holding_weight, reverse=True)

    top_holdings = sorted_holdings[:120]
    tail_holdings = sorted_holdings[120:]

    total_market_weight = sum((_holding_weight(item) for item in sorted_holdings), Decimal("0"))
    top_weight = sum((_holding_weight(item) for item in top_holdings), Decimal("0"))
    tail_weight = sum((_holding_weight(item) for item in tail_holdings), Decimal("0"))

    allocations: dict[str, Allocation] = {}
    redirected: list[dict] = []

    for holding in top_holdings:
        weight = _holding_weight(holding)
        if weight <= 0:
            continue
        symbol = _holding_symbol(holding)
        sector = _holding_sector(holding)
        if _is_excluded(holding, exclusions):
            etf = _sector_etf(sector)
            existing = allocations.get(etf)
            allocations[etf] = Allocation(
                symbol=etf,
                weight=(existing.weight if existing else Decimal("0")) + weight,
                sector=sector,
                is_etf=True,
            )
            redirected.append(
                {
                    "symbol": symbol,
                    "sector": sector,
                    "etf": etf,
                    "weight": weight,
                }
            )
        else:
            allocations[symbol] = Allocation(
                symbol=symbol,
                weight=weight,
                sector=sector,
                is_etf=False,
            )

    if tail_weight > 0:
        existing = allocations.get(BROAD_MARKET_ETF)
        allocations[BROAD_MARKET_ETF] = Allocation(
            symbol=BROAD_MARKET_ETF,
            weight=(existing.weight if existing else Decimal("0")) + tail_weight,
            sector="broad",
            is_etf=True,
        )

    price_lookup = {
        symbol.upper(): _as_decimal(value) for symbol, value in (price_lookup or {}).items()
    }
    prices: dict[str, Decimal] = dict(price_lookup)

    for holding in holdings_list:
        symbol = _holding_symbol(holding)
        if symbol in prices:
            continue
        price = _holding_price(holding)
        if price:
            prices[symbol] = price

    missing_prices = [symbol for symbol in allocations if symbol not in prices]
    if missing_prices:
        if not api_key:
            raise ValueError("Missing prices for allocations and no API key provided")
        prices.update(fetch_quotes(api_key, missing_prices))

    still_missing = [symbol for symbol in allocations if symbol not in prices]
    if still_missing:
        raise ValueError(f"Missing prices for allocations: {', '.join(still_missing)}")

    target_cash = _as_decimal(total_cash) * (Decimal("1") - _as_decimal(cash_buffer))
    total_weight = sum((allocation.weight for allocation in allocations.values()), Decimal("0"))
    if total_weight <= 0:
        raise ValueError("Total allocation weight must be greater than zero")

    allocation_items = sorted(
        allocations.values(),
        key=lambda item: (item.symbol == BROAD_MARKET_ETF, -item.weight),
    )

    orders = []
    running_total = Decimal("0")
    for index, allocation in enumerate(allocation_items):
        if index == len(allocation_items) - 1:
            dollar_amount = target_cash - running_total
        else:
            dollar_amount = (
                target_cash * allocation.weight / total_weight
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            running_total += dollar_amount
        price = prices[allocation.symbol]
        qty = (dollar_amount / price).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        orders.append(
            {
                "symbol": allocation.symbol,
                "action": "Buy",
                "qty": _format_shares(qty),
                "price": float(price),
                "dollar_amount": float(dollar_amount),
                "is_etf": allocation.is_etf,
            }
        )

    redirected_dollars = []
    for item in redirected:
        weight = item["weight"]
        amount = (
            target_cash * weight / total_weight
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        redirected_dollars.append(
            {
                "symbol": item["symbol"],
                "sector": item["sector"],
                "etf": item["etf"],
                "dollar_amount": float(amount),
            }
        )

    report = {
        "market_cap_capture_pct": float(
            (top_weight / total_market_weight) * Decimal("100")
            if total_market_weight
            else Decimal("0")
        ),
        "stock_lots": sum(1 for order in orders if not order["is_etf"]),
        "etf_lots": sum(1 for order in orders if order["is_etf"]),
        "redirected": redirected_dollars,
        "total_allocated": float(target_cash),
    }

    return {"orders": orders, "report": report}


def write_genesis_trades_csv(
    orders: Iterable[dict],
    output_path: Path | str = Path("genesis_trades.csv"),
    account_number: str = "",
) -> Path:
    output_path = Path(output_path)
    with output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Account Number",
                "Symbol",
                "Action",
                "Quantity",
                "Order Type",
                "Timing",
            ]
        )
        for order in orders:
            writer.writerow(
                [
                    account_number,
                    order["symbol"],
                    order.get("action", "Buy"),
                    order["qty"],
                    "Market",
                    "Day",
                ]
            )
    return output_path
