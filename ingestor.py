import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
from pydantic import BaseModel, Field, validator


HEADER_REQUIRED_COLUMNS = {"Symbol", "Quantity"}
DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"]
HEADER_ALIASES = {
    "Qty (Quantity)": "Quantity",
    "Qty": "Quantity",
    "Gain % (Gain/Loss %)": "Gain/Loss %",
    "Gain/Loss %": "Gain/Loss %",
    "Cost Basis": "Total Cost Basis",
    "Total Cost Basis": "Total Cost Basis",
    "Cost Basis Per Share": "Cost Basis Per Share",
    "Price": "Price",
    "Symbol": "Symbol",
    "Date Acquired": "Date Acquired",
    "Acquired": "Acquired",
}

ACTION_CATEGORIES = {
    "buy": "acquisition",
    "reinvest shares": "acquisition",
    "qual div reinvest": "acquisition",
    "sell": "disposal",
    "qualified dividend": "cash_flow",
    "cash dividend": "cash_flow",
    "non-qualified div": "cash_flow",
    "credit interest": "cash_flow",
    "promotional award": "cash_flow",
    "cash in lieu": "cash_flow",
    "reverse split": "corporate_action",
    "cash merger": "corporate_action",
    "cash merger adj": "corporate_action",
    "journal": "admin",
    "security transfer": "admin",
}

ACTION_CANONICAL = {
    "qual div reinvest": "qual div reinvest",
    "qualified dividend": "qualified dividend",
    "cash dividend": "cash dividend",
    "non-qualified div": "non-qualified div",
    "reinvest shares": "reinvest shares",
    "credit interest": "credit interest",
    "promotional award": "promotional award",
    "cash in lieu": "cash in lieu",
    "reverse split": "reverse split",
    "cash merger": "cash merger",
    "cash merger adj": "cash merger adj",
    "journal": "journal",
    "security transfer": "security transfer",
    "buy": "buy",
    "sell": "sell",
}

WASH_SALE_INDEX: dict[str, list[dict]] = {}


class Lot(BaseModel):
    symbol: str = Field(..., min_length=1)
    qty: float
    acquisition_date: date
    cost_basis_per_share: float
    total_cost_basis: float
    current_price: float
    unrealized_pl_pct: float

    @validator("qty", "cost_basis_per_share", "total_cost_basis", "current_price")
    def must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("numeric values must be non-negative")
        return value

    @validator("symbol")
    def normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return symbol


def _normalize_header_name(value: str) -> str:
    cleaned = value.strip().strip('"').lstrip("\ufeff")
    return HEADER_ALIASES.get(cleaned, cleaned)


def _find_header_row(rows: Iterable[List[str]]) -> int:
    for index, row in enumerate(rows):
        normalized = [_normalize_header_name(cell) for cell in row]
        if HEADER_REQUIRED_COLUMNS.issubset(set(normalized)):
            return index
    raise ValueError("CSV header row not found")


def _extract_as_of_date(lines: Iterable[str]) -> Optional[date]:
    for line in lines:
        match = re.search(
            r"as of .*?(\d{2}/\d{2}/\d{4}|\d{4}/\d{2}/\d{2})",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            return _parse_date(match.group(1))
    return None


def _parse_date(value: Optional[str]) -> date:
    if not value:
        raise ValueError("acquisition date is required")
    cleaned = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date format: {value}")


def _parse_effective_date(value: Optional[str]) -> date:
    if not value:
        raise ValueError("transaction date is required")
    cleaned = str(value).strip()
    match = re.search(
        r"as of\s*(\d{2}/\d{2}/\d{4}|\d{4}[-/]\d{2}[-/]\d{2})",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return _parse_date(match.group(1).replace("-", "/"))
    date_match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}[-/]\d{2}[-/]\d{2})", cleaned)
    if date_match:
        return _parse_date(date_match.group(1).replace("-", "/"))
    return _parse_date(cleaned)


def _strip_excel_format(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("="):
        cleaned = cleaned.lstrip("=")
    return cleaned.strip('"')


def _parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    cleaned = _strip_excel_format(str(value))
    if cleaned.upper() in {"N/A", "--"}:
        return None
    cleaned = cleaned.replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return Decimal(cleaned)


def _normalize_action(value: Optional[str]) -> str:
    cleaned = str(value or "").strip().lower()
    return ACTION_CANONICAL.get(cleaned, cleaned)


def _action_category(action: str) -> str:
    return ACTION_CATEGORIES.get(action, "unknown")


def _parse_currency(value: Optional[str]) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError("currency value is required")
    cleaned = _strip_excel_format(str(value))
    if cleaned.upper() in {"N/A", "--"}:
        raise ValueError("currency value is required")
    cleaned = cleaned.replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned)


def _parse_percentage(value: Optional[str]) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError("percentage value is required")
    cleaned = _strip_excel_format(str(value)).replace("%", "").strip()
    if cleaned.upper() in {"N/A", "--"}:
        raise ValueError("percentage value is required")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    return round(float(cleaned) / 100, 4)


def _parse_quantity(value: Optional[str]) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    cleaned = _strip_excel_format(str(value))
    if cleaned.upper() in {"N/A", "--"}:
        return None
    cleaned = cleaned.replace(",", "").strip()
    if cleaned == "":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _read_positions_dataframe(path: str) -> tuple[pd.DataFrame, Optional[date]]:
    with open(path, "r", newline="") as handle:
        content = handle.read()

    lines = content.splitlines()
    rows = list(csv.reader(lines))
    header_index = _find_header_row(rows)
    as_of_date = _extract_as_of_date(lines)

    df = pd.read_csv(
        io.StringIO(content),
        skiprows=range(header_index),
        dtype=str,
        keep_default_na=False,
    )
    df = df.rename(columns={col: _normalize_header_name(col) for col in df.columns})
    return df, as_of_date


def parse_schwab_positions(path: str) -> List[dict]:
    df, as_of_date = _read_positions_dataframe(path)
    if df.empty:
        raise ValueError("CSV contains no position rows")

    lots: List[Lot] = []
    for _, row in df.iterrows():
        acquisition_value = row.get("Date Acquired") or row.get("Acquired")
        acquisition_date = _parse_date(acquisition_value) if acquisition_value else None
        if acquisition_date is None:
            if as_of_date is None:
                raise ValueError("acquisition date could not be determined")
            acquisition_date = as_of_date

        qty = _parse_quantity(row.get("Quantity"))
        if qty is None:
            continue
        cost_basis_per_share = row.get("Cost Basis Per Share")
        total_cost_basis = row.get("Total Cost Basis")

        parsed_total_cost_basis = _parse_currency(total_cost_basis)
        parsed_cost_basis_per_share = (
            _parse_currency(cost_basis_per_share)
            if cost_basis_per_share
            else round(parsed_total_cost_basis / qty, 2)
        )

        lot = Lot(
            symbol=row.get("Symbol"),
            qty=qty,
            acquisition_date=acquisition_date,
            cost_basis_per_share=parsed_cost_basis_per_share,
            total_cost_basis=parsed_total_cost_basis,
            current_price=_parse_currency(row.get("Price")),
            unrealized_pl_pct=_parse_percentage(row.get("Gain/Loss %")),
        )
        lots.append(lot)

    payload = []
    for lot in lots:
        data = lot.dict()
        data["acquisition_date"] = lot.acquisition_date.isoformat()
        payload.append(data)
    return payload


def _load_brokerage_transactions(path: str) -> list[dict]:
    payload = json.loads(Path(path).read_text())
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get("BrokerageTransactions") or payload.get("brokerageTransactions")
        if records is None:
            raise ValueError("JSON payload missing BrokerageTransactions array")
        return records
    raise ValueError("unsupported JSON payload shape")


def _adjustment_sort_key(adjustment: dict) -> tuple[str, int]:
    return (adjustment["effective_date"], adjustment["source_index"])


def _build_adjustment(
    *,
    event_id: Optional[str],
    effective_date: date,
    action: str,
    symbol: Optional[str],
    quantity: Optional[Decimal],
    price: Optional[Decimal],
    amount: Optional[Decimal],
    source_index: int,
) -> dict:
    category = _action_category(action)
    normalized_symbol = symbol.strip().upper() if symbol else None
    adjustment: dict = {
        "event_id": event_id,
        "effective_date": effective_date.isoformat(),
        "action": action,
        "category": category,
        "symbol": normalized_symbol,
        "quantity": quantity,
        "price": price,
        "amount": amount,
        "cash_delta": None,
        "lot_delta": None,
        "cost_basis_multiplier": None,
        "wash_sale_candidate": action == "sell",
        "source_index": source_index,
    }

    if category == "acquisition":
        normalized_qty = abs(quantity) if quantity is not None else None
        inferred_amount = amount
        if inferred_amount is None and price is not None and normalized_qty is not None:
            inferred_amount = price * normalized_qty
        adjustment["quantity"] = normalized_qty
        adjustment["amount"] = inferred_amount
        adjustment["lot_delta"] = normalized_qty
        adjustment["cash_delta"] = -abs(inferred_amount) if inferred_amount is not None else None
    elif category == "disposal":
        normalized_qty = abs(quantity) if quantity is not None else None
        inferred_amount = amount
        if inferred_amount is None and price is not None and normalized_qty is not None:
            inferred_amount = price * normalized_qty
        adjustment["quantity"] = normalized_qty
        adjustment["amount"] = inferred_amount
        adjustment["lot_delta"] = -normalized_qty if normalized_qty is not None else None
        adjustment["cash_delta"] = abs(inferred_amount) if inferred_amount is not None else None
    elif category == "cash_flow":
        adjustment["cash_delta"] = amount
    elif category == "corporate_action":
        if action in {"cash merger", "cash merger adj"}:
            normalized_qty = abs(quantity) if quantity is not None else None
            adjustment["quantity"] = normalized_qty
            adjustment["lot_delta"] = -normalized_qty if normalized_qty is not None else None
            adjustment["cash_delta"] = amount
        elif action == "reverse split":
            adjustment["lot_delta"] = quantity
    elif category == "admin":
        adjustment["cash_delta"] = amount
        adjustment["lot_delta"] = quantity

    return adjustment


def _collapse_reverse_splits(adjustments: list[dict]) -> list[dict]:
    grouped: dict[tuple[str | None, str], list[dict]] = defaultdict(list)
    remaining: list[dict] = []
    for adjustment in adjustments:
        if adjustment["action"] == "reverse split":
            grouped[(adjustment["symbol"], adjustment["effective_date"])].append(adjustment)
        else:
            remaining.append(adjustment)

    for (symbol, effective_date), items in grouped.items():
        negative_qty = sum(
            (item["quantity"] or Decimal("0"))
            for item in items
            if (item["quantity"] or Decimal("0")) < 0
        )
        positive_qty = sum(
            (item["quantity"] or Decimal("0"))
            for item in items
            if (item["quantity"] or Decimal("0")) > 0
        )
        if negative_qty and positive_qty:
            raw_ratio = (abs(negative_qty) / positive_qty).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
            combined = items[0].copy()
            combined["quantity_before"] = abs(negative_qty)
            combined["quantity_after"] = positive_qty
            combined["cost_basis_multiplier"] = raw_ratio
            combined["lot_delta"] = None
            remaining.append(combined)
        else:
            remaining.extend(items)

    return remaining


def _build_wash_sale_index(adjustments: list[dict]) -> dict[str, list[dict]]:
    registry: dict[str, list[dict]] = defaultdict(list)
    for adjustment in adjustments:
        if adjustment.get("action") == "sell":
            symbol = adjustment.get("symbol")
            if not symbol:
                continue
            registry[symbol].append(
                {
                    "effective_date": adjustment["effective_date"],
                    "quantity": adjustment.get("quantity"),
                    "amount": adjustment.get("amount"),
                }
            )
    return dict(registry)


def parse_schwab_transactions(path: str) -> List[dict]:
    global WASH_SALE_INDEX
    if Path(path).suffix.lower() == ".json":
        transactions = _load_brokerage_transactions(path)
        adjustments: list[dict] = []
        seen_ids: set[str] = set()
        for index, row in enumerate(transactions):
            event_id = str(row.get("ItemIssueId") or row.get("itemIssueId") or "").strip() or None
            if event_id and event_id in seen_ids:
                continue
            if event_id:
                seen_ids.add(event_id)

            action = _normalize_action(row.get("Action") or row.get("action"))
            effective_date = _parse_effective_date(row.get("Date") or row.get("date"))
            adjustment = _build_adjustment(
                event_id=event_id,
                effective_date=effective_date,
                action=action,
                symbol=str(row.get("Symbol") or row.get("symbol") or "").strip(),
                quantity=_parse_decimal(row.get("Quantity") or row.get("quantity")),
                price=_parse_decimal(row.get("Price") or row.get("price")),
                amount=_parse_decimal(row.get("Amount") or row.get("amount")),
                source_index=index,
            )
            adjustments.append(adjustment)

        adjustments = _collapse_reverse_splits(adjustments)
        adjustments.sort(key=_adjustment_sort_key)
        for adjustment in adjustments:
            adjustment.pop("source_index", None)
        WASH_SALE_INDEX.clear()
        WASH_SALE_INDEX.update(_build_wash_sale_index(adjustments))
        return adjustments

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        raise ValueError("CSV contains no transaction rows")

    transactions = []
    for index, row in df.iterrows():
        action = _normalize_action(row.get("Action"))
        adjustment = _build_adjustment(
            event_id=None,
            effective_date=_parse_date(row.get("Date")),
            action=action,
            symbol=str(row.get("Symbol")).strip(),
            quantity=_parse_decimal(row.get("Quantity")),
            price=_parse_decimal(row.get("Price")),
            amount=_parse_decimal(row.get("Total Amount")),
            source_index=int(index),
        )
        adjustment.pop("source_index", None)
        transactions.append(adjustment)

    WASH_SALE_INDEX.clear()
    WASH_SALE_INDEX.update(_build_wash_sale_index(transactions))
    return transactions
