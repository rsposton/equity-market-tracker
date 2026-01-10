import pytest

from engine import Lot, generate_tlh_trades


def test_excluded_sector_reinvestment():
    lots = [
        Lot(
            ticker="PM",
            quantity=10,
            cost_basis_per_share=100.0,
            current_price=90.0,
            sector="tobacco",
        )
    ]
    trades = generate_tlh_trades(
        lots,
        account_value=1000.0,
        drawdown_mode=False,
        excluded_tickers={"PM"},
        wash_sale_locked=set(),
        replacement_map={"tobacco": "SCHX"},
        default_replacement="SCHX",
    )

    assert len(trades) == 1
    assert trades[0]["sell_ticker"] == "PM"
    assert trades[0]["buy_ticker"] == "SCHX"


@pytest.mark.parametrize(
    ("drawdown_mode", "expected_count"),
    [
        (False, 2),
        (True, 4),
    ],
)
def test_drawdown_turnover_clipping(drawdown_mode: bool, expected_count: int):
    lots = [
        Lot(
            ticker=f"LOSS{i}",
            quantity=10,
            cost_basis_per_share=12.5,
            current_price=10.0,
        )
        for i in range(4)
    ]
    trades = generate_tlh_trades(
        lots,
        account_value=1000.0,
        drawdown_mode=drawdown_mode,
        excluded_tickers=set(),
        wash_sale_locked=set(),
        replacement_map={},
        default_replacement="SCHX",
    )

    assert len(trades) == expected_count
