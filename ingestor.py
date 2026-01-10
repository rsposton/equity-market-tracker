import csv
import io
import re
from datetime import datetime, date
from typing import Iterable, List, Optional

import pandas as pd
from pydantic import BaseModel, Field, validator


HEADER_REQUIRED_COLUMNS = {"Symbol", "Quantity"}
DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d"]


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


def _find_header_row(rows: Iterable[List[str]]) -> int:
    for index, row in enumerate(rows):
        normalized = [cell.strip().strip('"') for cell in row]
        if HEADER_REQUIRED_COLUMNS.issubset(set(normalized)):
            return index
    raise ValueError("CSV header row not found")


def _extract_as_of_date(lines: Iterable[str]) -> Optional[date]:
    for line in lines:
        match = re.search(r"as of (\d{2}/\d{2}/\d{4})", line, flags=re.IGNORECASE)
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


def _parse_currency(value: Optional[str]) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError("currency value is required")
    cleaned = str(value)
    cleaned = cleaned.replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned)


def _parse_percentage(value: Optional[str]) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError("percentage value is required")
    cleaned = str(value).strip().replace("%", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    return round(float(cleaned) / 100, 4)


def _read_positions_dataframe(path: str) -> tuple[pd.DataFrame, Optional[date]]:
    with open(path, "r", newline="") as handle:
        content = handle.read()

    lines = content.splitlines()
    rows = list(csv.reader(lines))
    header_index = _find_header_row(rows)
    as_of_date = _extract_as_of_date(lines[:header_index])

    df = pd.read_csv(
        io.StringIO(content),
        skiprows=range(header_index),
        dtype=str,
        keep_default_na=False,
    )
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

        qty = float(row.get("Quantity"))
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


def parse_schwab_transactions(path: str) -> List[dict]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        raise ValueError("CSV contains no transaction rows")

    transactions = []
    for _, row in df.iterrows():
        transactions.append(
            {
                "date": _parse_date(row.get("Date")).isoformat(),
                "action": str(row.get("Action")).strip().lower(),
                "symbol": str(row.get("Symbol")).strip().upper(),
                "quantity": float(row.get("Quantity")),
                "price": _parse_currency(row.get("Price")),
                "total_amount": _parse_currency(row.get("Total Amount")),
            }
        )

    return transactions
