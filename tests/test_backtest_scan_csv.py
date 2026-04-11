"""扫描 CSV 纯函数。"""

from src.backtest.scan import ma_cross_scan_csv_bytes, parse_scan_codes


def test_parse_scan_codes_dedup_and_cap():
    assert parse_scan_codes("sh.A, sh.B,sh.A", 10) == ["sh.a", "sh.b"]
    assert parse_scan_codes("a,b,c", 2) == ["a", "b"]


def test_ma_cross_scan_csv_bom_and_header():
    items = [
        {
            "code": "sh.x",
            "error": None,
            "bars_used": 100,
            "total_return_pct": 1.5,
            "buy_hold_return_pct": 2.0,
            "excess_return_pct": -0.5,
            "max_drawdown_pct": -3.0,
            "sharpe_ratio": 0.5,
            "signal_changes": 4,
        }
    ]
    b = ma_cross_scan_csv_bytes(
        items,
        fast=5,
        slow=20,
        limit=500,
        commission_rate=0.0,
        slippage_rate=0.0,
        sort_by="total_return",
    )
    assert b[:3] == b"\xef\xbb\xbf"
    s = b.decode("utf-8")
    assert "code" in s
    assert "sh.x" in s
    assert "1.5" in s
    assert "excess_return_pct" in s
    assert "-0.5" in s
