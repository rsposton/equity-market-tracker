from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Lot:
    ticker: str
    quantity: float
    cost_basis_per_share: float
    current_price: float
    sector: str | None = None

    @property
    def unrealized_pl_pct(self) -> float:
        if self.cost_basis_per_share == 0:
            return 0.0
        return (self.current_price - self.cost_basis_per_share) / self.cost_basis_per_share

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price


def _should_harvest(lot: Lot, drawdown_mode: bool) -> bool:
    loss_threshold = -0.05 if drawdown_mode else -0.06
    if lot.unrealized_pl_pct > loss_threshold:
        return False
    loss_value = (lot.current_price - lot.cost_basis_per_share) * lot.quantity
    return loss_value <= -25.0


def _replacement_ticker(
    lot: Lot,
    replacement_map: dict[str, str],
    default_replacement: str,
) -> str:
    ticker_key = lot.ticker.upper()
    sector_key = (lot.sector or "").strip().lower()
    return (
        replacement_map.get(ticker_key)
        or replacement_map.get(sector_key)
        or default_replacement
    )


def _clip_turnover(trades: Iterable[dict], account_value: float, drawdown_mode: bool) -> list[dict]:
    cap = 0.6 if drawdown_mode else 0.2
    cap_value = account_value * cap
    clipped: list[dict] = []
    used = 0.0
    for trade in trades:
        sell_value = float(trade.get("sell_value", 0.0))
        if used >= cap_value:
            break
        remaining = cap_value - used
        if sell_value <= remaining:
            clipped.append(dict(trade))
            used += sell_value
            continue
        if sell_value > 0:
            ratio = remaining / sell_value
            partial = dict(trade)
            partial["sell_value"] = round(sell_value * ratio, 2)
            partial["buy_value"] = round(float(trade.get("buy_value", 0.0)) * ratio, 2)
            clipped.append(partial)
            used = cap_value
    return clipped


def generate_tlh_trades(
    lots: Iterable[Lot],
    account_value: float,
    *,
    drawdown_mode: bool,
    excluded_tickers: set[str],
    wash_sale_locked: set[str],
    replacement_map: dict[str, str],
    default_replacement: str = "SCHX",
) -> list[dict]:
    excluded_lookup = {ticker.upper() for ticker in excluded_tickers}
    trades: list[dict] = []
    for lot in lots:
        ticker = lot.ticker.upper()
        if ticker in wash_sale_locked:
            continue
        if not _should_harvest(lot, drawdown_mode):
            continue
        replacement = _replacement_ticker(lot, replacement_map, default_replacement).upper()
        sell_value = lot.market_value
        buy_ticker = replacement if replacement not in excluded_lookup else None
        buy_value = sell_value if buy_ticker else 0.0
        trades.append(
            {
                "sell_ticker": ticker,
                "sell_value": sell_value,
                "buy_ticker": buy_ticker,
                "buy_value": buy_value,
            }
        )

    return _clip_turnover(trades, account_value, drawdown_mode)
