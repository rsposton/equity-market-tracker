from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable


DEFAULT_REPLACEMENT = "SCHX"
SECTOR_REPLACEMENTS = {
    "tech": "QQQ",
    "technology": "QQQ",
    "financials": "XLF",
    "banks": "XLF",
    "energy": "XLE",
    "industrials": "XLI",
    "industrial": "XLI",
    "healthcare": "SCHX",
    "pharma": "SCHX",
    "biotech": "SCHX",
    "tobacco": "SCHX",
    "nicotine": "SCHX",
}


def _normalize_sector(sector: str | None) -> str:
    return (sector or "").strip().lower()


def _normalize_ticker(ticker: str | None) -> str:
    return str(ticker or "").strip().upper()


def _load_exclusions(exclusions_path: str | Path | None) -> tuple[set[str], set[str]]:
    if not exclusions_path:
        return set(), set()
    data = json.loads(Path(exclusions_path).read_text())
    sectors = {_normalize_sector(sector) for sector in data.get("sectors", [])}
    tickers = {_normalize_ticker(ticker) for ticker in data.get("tickers", [])}
    return sectors, tickers


def _is_tlh_eligible(lot: dict[str, Any], drawdown_mode: bool) -> bool:
    loss_threshold = Decimal("-0.05") if drawdown_mode else Decimal("-0.06")
    unrealized = lot.get("unrealized_pl_pct")
    if unrealized is None:
        cost_basis = Decimal(str(lot.get("cost_basis_per_share", 0)))
        current = Decimal(str(lot.get("current_price", 0)))
        if cost_basis == 0:
            return False
        unrealized = (current - cost_basis) / cost_basis
    unrealized = Decimal(str(unrealized))
    if unrealized > loss_threshold:
        return False
    qty = Decimal(str(lot.get("qty", 0)))
    cost_basis = Decimal(str(lot.get("cost_basis_per_share", 0)))
    current = Decimal(str(lot.get("current_price", 0)))
    loss_value = (current - cost_basis) * qty
    return loss_value <= Decimal("-25")


def _replacement_for_lot(lot: dict[str, Any]) -> str:
    sector = _normalize_sector(lot.get("sector"))
    return SECTOR_REPLACEMENTS.get(sector, DEFAULT_REPLACEMENT)


def _buy_blocked(
    replacement: str,
    excluded_tickers: set[str],
    wash_sale_registry: dict[str, Any] | None,
) -> bool:
    replacement = _normalize_ticker(replacement)
    if replacement in excluded_tickers:
        return True
    if not wash_sale_registry:
        return False
    recent_sales = {
        _normalize_ticker(ticker) for ticker in wash_sale_registry.get("recent_sales", {})
    }
    if replacement in recent_sales:
        return True
    substantially_identical = wash_sale_registry.get("substantially_identical", {})
    for alt in substantially_identical.get(replacement, []):
        if _normalize_ticker(alt) in recent_sales:
            return True
    return False


def _format_qty(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f"{quantized:.4f}"


def _format_price(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:.2f}"


def _clip_turnover(
    candidates: Iterable[tuple[dict[str, Any], dict[str, Any] | None]],
    portfolio_value: Decimal,
    drawdown_mode: bool,
) -> list[dict[str, Any]]:
    cap = Decimal("0.6") if drawdown_mode else Decimal("0.2")
    cap_value = portfolio_value * cap
    used = Decimal("0")
    trades: list[dict[str, Any]] = []
    for sell_trade, buy_trade in candidates:
        sell_value = Decimal(str(sell_trade["price"])) * Decimal(str(sell_trade["qty"]))
        if used + sell_value > cap_value:
            break
        used += sell_value
        trades.append(sell_trade)
        if buy_trade is not None:
            trades.append(buy_trade)
    return trades


def propose_trades(
    payload: dict[str, Any],
    *,
    drawdown_mode: bool = False,
    exclusions_path: str | Path | None = None,
    wash_sale_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lots = payload.get("lots", [])
    replacement_prices = payload.get("replacement_prices", {})
    portfolio_value = payload.get("portfolio_value")
    if portfolio_value is None:
        portfolio_value = sum(
            Decimal(str(lot.get("qty", 0))) * Decimal(str(lot.get("current_price", 0)))
            for lot in lots
        )
    portfolio_value = Decimal(str(portfolio_value))

    _, excluded_tickers = _load_exclusions(exclusions_path)
    candidates: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for lot in lots:
        ticker = _normalize_ticker(lot.get("symbol"))
        if not _is_tlh_eligible(lot, drawdown_mode):
            continue
        qty = Decimal(str(lot.get("qty", 0)))
        price = Decimal(str(lot.get("current_price", 0)))
        sell_trade = {
            "action": "sell",
            "symbol": ticker,
            "qty": _format_qty(qty),
            "price": _format_price(price),
        }
        replacement = _replacement_for_lot(lot)
        buy_trade = None
        replacement_price_raw = replacement_prices.get(replacement)
        if replacement_price_raw is not None and not _buy_blocked(
            replacement, excluded_tickers, wash_sale_registry
        ):
            replacement_price = Decimal(str(replacement_price_raw))
            sell_value = qty * price
            buy_qty = sell_value / replacement_price if replacement_price else Decimal("0")
            buy_trade = {
                "action": "buy",
                "symbol": _normalize_ticker(replacement),
                "qty": _format_qty(buy_qty),
                "price": _format_price(replacement_price),
            }
        candidates.append((sell_trade, buy_trade))

    trades = _clip_turnover(candidates, portfolio_value, drawdown_mode)
    return {"trades": trades}
