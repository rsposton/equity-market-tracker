from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

import json
import logging

from compliance import COMPLIANCE_DUMMY, check_safety


DEFAULT_EXCLUSIONS_PATH = Path(__file__).with_name("exclusions.json")


REPLACEMENT_MAPPING = {
    "tech": "QQQ",
    "mega-cap growth": "QQQ",
    "financials": "XLF",
    "energy": "XLE",
    "industrials": "XLI",
    "broad": "SCHX",
    "general": "SCHX",
    "other": "SCHX",
    "value": "FNDX",
}


@dataclass(frozen=True)
class LossCandidate:
    symbol: str
    qty: Decimal
    current_price: Decimal
    loss_pct: Decimal
    dollar_loss: Decimal
    sector: str
    replacement: str

    @property
    def sale_value(self) -> Decimal:
        return self.qty * self.current_price


@dataclass(frozen=True)
class WashSaleRegistry:
    recent_sales: dict[str, str]
    substantially_identical: dict[str, list[str]]

    def is_blocked(self, ticker: str) -> bool:
        if ticker in self.recent_sales:
            return True
        for candidate in self.substantially_identical.get(ticker, []):
            if candidate in self.recent_sales:
                return True
        return False


def _as_decimal(value: float | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _format_shares(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):.4f}"


def _load_exclusions(path: Path = DEFAULT_EXCLUSIONS_PATH) -> dict:
    if not path.exists():
        return {"sectors": [], "tickers": []}
    return json.loads(path.read_text())


def _normalize_sector(sector: Optional[str]) -> str:
    return (sector or "").strip().lower()


def _replacement_for_sector(sector: str) -> str:
    if not sector:
        return REPLACEMENT_MAPPING["broad"]
    return REPLACEMENT_MAPPING.get(sector, REPLACEMENT_MAPPING["broad"])


def _build_registry(registry: Optional[dict]) -> WashSaleRegistry:
    if not registry:
        return WashSaleRegistry(recent_sales={}, substantially_identical={})
    return WashSaleRegistry(
        recent_sales=registry.get("recent_sales", {}),
        substantially_identical=registry.get("substantially_identical", {}),
    )


def _eligible_for_loss(lot: dict, drawdown_mode: bool) -> bool:
    loss_pct = -_as_decimal(lot.get("unrealized_pl_pct", 0))
    if loss_pct <= 0:
        return False
    if drawdown_mode:
        return loss_pct >= Decimal("0.05")
    dollar_loss = _as_decimal(lot.get("cost_basis_per_share")) - _as_decimal(
        lot.get("current_price")
    )
    dollar_loss *= _as_decimal(lot.get("qty"))
    return loss_pct >= Decimal("0.08") and dollar_loss >= Decimal("25")


def _loss_candidates(lots: Iterable[dict], drawdown_mode: bool) -> list[LossCandidate]:
    candidates: list[LossCandidate] = []
    for lot in lots:
        if not _eligible_for_loss(lot, drawdown_mode):
            continue
        sector = _normalize_sector(lot.get("sector"))
        replacement = _replacement_for_sector(sector)
        qty = _as_decimal(lot.get("qty"))
        current_price = _as_decimal(lot.get("current_price"))
        loss_pct = -_as_decimal(lot.get("unrealized_pl_pct"))
        dollar_loss = (_as_decimal(lot.get("cost_basis_per_share")) - current_price) * qty
        candidates.append(
            LossCandidate(
                symbol=str(lot.get("symbol")).upper(),
                qty=qty,
                current_price=current_price,
                loss_pct=loss_pct,
                dollar_loss=dollar_loss,
                sector=sector,
                replacement=replacement,
            )
        )
    return candidates


def _clip_turnover(
    candidates: list[LossCandidate], total_portfolio_value: Decimal
) -> list[LossCandidate]:
    cap = total_portfolio_value * Decimal("0.20")
    if cap <= 0:
        return []
    ordered = sorted(candidates, key=lambda item: item.dollar_loss, reverse=True)
    selected: list[LossCandidate] = []
    running_value = Decimal("0")
    for candidate in ordered:
        if running_value + candidate.sale_value > cap:
            continue
        selected.append(candidate)
        running_value += candidate.sale_value
    return selected


def _calculate_portfolio_value(lots: Iterable[dict]) -> Decimal:
    total = Decimal("0")
    for lot in lots:
        total += _as_decimal(lot.get("qty")) * _as_decimal(lot.get("current_price"))
    return total


def propose_trades(
    payload: dict,
    drawdown_mode: bool = False,
    dry_run: bool = False,
    wash_sale_registry: Optional[dict] = None,
    exclusions_path: Path = DEFAULT_EXCLUSIONS_PATH,
) -> dict:
    logger = logging.getLogger(__name__)
    if COMPLIANCE_DUMMY:
        logger.warning("Compliance check is using dummy implementation.")
    else:
        logger.info("Compliance check is using real implementation.")

    lots = payload.get("lots", [])
    replacement_prices = payload.get("replacement_prices", {})
    portfolio_value = payload.get("portfolio_value")
    total_portfolio_value = (
        _as_decimal(portfolio_value)
        if portfolio_value is not None
        else _calculate_portfolio_value(lots)
    )

    exclusions = _load_exclusions(exclusions_path)
    excluded_sectors = {
        sector.strip().lower() for sector in exclusions.get("sectors", [])
    }
    excluded_tickers = {
        ticker.strip().upper() for ticker in exclusions.get("tickers", [])
    }
    registry = _build_registry(wash_sale_registry)

    candidates = _loss_candidates(lots, drawdown_mode)
    potential_loss = sum((candidate.dollar_loss for candidate in candidates), Decimal("0"))
    selected = _clip_turnover(candidates, total_portfolio_value)

    trades = []
    harvested_loss = Decimal("0")
    total_sell_value = Decimal("0")

    for candidate in selected:
        harvested_loss += candidate.dollar_loss
        total_sell_value += candidate.sale_value
        trades.append(
            {
                "action": "sell",
                "symbol": candidate.symbol,
                "qty": _format_shares(candidate.qty),
                "price": str(candidate.current_price),
                "replacement": candidate.replacement,
            }
        )

        replacement = candidate.replacement
        replacement_sector_blocked = candidate.sector in excluded_sectors
        replacement_ticker_blocked = replacement in excluded_tickers
        if replacement_sector_blocked or replacement_ticker_blocked:
            continue
        if registry.is_blocked(replacement):
            continue
        if not check_safety(replacement, datetime.now(tz=timezone.utc).date()):
            continue

        replacement_price = _as_decimal(replacement_prices.get(replacement, "1"))
        buy_qty = candidate.sale_value / replacement_price
        trades.append(
            {
                "action": "buy",
                "symbol": replacement,
                "qty": _format_shares(buy_qty),
                "price": str(replacement_price),
                "replaces": candidate.symbol,
            }
        )

    summary = {
        "total_portfolio_value": str(total_portfolio_value),
        "potential_loss": str(potential_loss),
        "harvested_loss": str(harvested_loss),
        "total_sell_value": str(total_sell_value),
        "turnover_ratio": str(
            (total_sell_value / total_portfolio_value) if total_portfolio_value else 0
        ),
    }

    if dry_run:
        print(
            "Losses Harvested vs Potential Losses: "
            f"{harvested_loss} / {potential_loss}"
        )
        return {"summary": summary, "trades": []}

    return {"summary": summary, "trades": trades}


def mock_wash_sale_registry(
    recent_sales: Optional[dict[str, str]] = None,
    substantially_identical: Optional[dict[str, list[str]]] = None,
    as_of: Optional[datetime] = None,
) -> dict:
    cutoff = (as_of or datetime.utcnow()) - timedelta(days=90)
    cleaned_sales = {}
    for ticker, date_str in (recent_sales or {}).items():
        try:
            sold_date = datetime.fromisoformat(date_str)
        except ValueError:
            continue
        if sold_date >= cutoff:
            cleaned_sales[ticker.upper()] = sold_date.date().isoformat()
    return {
        "recent_sales": cleaned_sales,
        "substantially_identical": {
            key.upper(): [item.upper() for item in values]
            for key, values in (substantially_identical or {}).items()
        },
    }
