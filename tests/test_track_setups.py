"""
test_track_setups.py — enhetstester for outcome-evalueringen i track_setups.py.

Kjøring:
    python3 tests/test_track_setups.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from track_setups import evaluate_setup

# Bar-format: (epoch_ts, high, low). first_seen_ts=0 → alle barer telles.


def test_long_t1_hit():
    """LONG: pris faller til entry, deretter opp gjennom T1."""
    bars = [
        (10, 105.0, 102.0),   # ikke ved entry (100)
        (20, 101.0, 99.5),    # aktivering (entry=100)
        (30, 103.0, 100.5),
        (40, 106.5, 102.0),   # T1=106 treffes
    ]
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 0)
    assert r["status"] == "t1", f"forventet t1, fikk {r['status']}"
    assert r["activated_ts"] == 20
    assert r["closed_ts"] == 40
    print(f"PASS: long t1-hit (mfe={r['mfe']}, mae={r['mae']})")


def test_long_sl_hit():
    """LONG: aktiveres, faller så gjennom SL."""
    bars = [
        (10, 100.5, 99.8),    # aktivering
        (20, 100.2, 97.5),    # SL=98 brytes
    ]
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 0)
    assert r["status"] == "sl", f"forventet sl, fikk {r['status']}"
    print("PASS: long sl-hit")


def test_short_t1_hit():
    """SHORT: pris stiger til entry (motstand), faller så til T1."""
    bars = [
        (10, 99.0, 97.0),
        (20, 100.5, 98.0),    # aktivering (entry=100)
        (30, 99.0, 93.5),     # T1=94 treffes
    ]
    r = evaluate_setup("SELL", 100.0, 102.0, 94.0, bars, 0)
    assert r["status"] == "t1", f"forventet t1, fikk {r['status']}"
    print("PASS: short t1-hit")


def test_ambiguous_same_bar():
    """Begge nivåer i samme bar → ambiguous (konservativt = tap)."""
    bars = [
        (10, 100.5, 99.8),    # aktivering
        (20, 107.0, 97.0),    # både T1=106 og SL=98 i samme bar
    ]
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 0)
    assert r["status"] == "ambiguous", f"forventet ambiguous, fikk {r['status']}"
    print("PASS: ambiguous same-bar")


def test_pending_never_touched():
    """Entry aldri truffet → pending."""
    bars = [(10, 105.0, 102.0), (20, 106.0, 103.0)]
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 0)
    assert r["status"] == "pending", f"forventet pending, fikk {r['status']}"
    assert r["activated_ts"] is None
    print("PASS: pending")


def test_active_unresolved():
    """Aktivert men verken T1 eller SL → active."""
    bars = [(10, 100.5, 99.8), (20, 102.0, 99.0)]
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 0)
    assert r["status"] == "active", f"forventet active, fikk {r['status']}"
    assert r["mfe"] == 2.0, f"mfe={r['mfe']}"
    assert r["mae"] == 1.0, f"mae={r['mae']}"
    print("PASS: active med korrekt MFE/MAE")


def test_first_seen_filters_old_bars():
    """Barer før first_seen ignoreres — gamle touch teller ikke."""
    bars = [
        (10, 101.0, 99.0),    # ville aktivert, men før first_seen
        (20, 105.0, 102.0),   # etter first_seen: aldri ved entry
    ]
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 15)
    assert r["status"] == "pending", f"forventet pending, fikk {r['status']}"
    print("PASS: first_seen-filter")


def test_activation_bar_can_close():
    """Aktiveringsbaren selv kan treffe SL (spike gjennom nivået)."""
    bars = [(10, 100.5, 97.0)]   # entry=100 og SL=98 i samme bar
    r = evaluate_setup("BUY", 100.0, 98.0, 106.0, bars, 0)
    assert r["status"] == "sl", f"forventet sl, fikk {r['status']}"
    assert r["activated_ts"] == 10 and r["closed_ts"] == 10
    print("PASS: aktivering+SL i samme bar")


if __name__ == "__main__":
    test_long_t1_hit()
    test_long_sl_hit()
    test_short_t1_hit()
    test_ambiguous_same_bar()
    test_pending_never_touched()
    test_active_unresolved()
    test_first_seen_filters_old_bars()
    test_activation_bar_can_close()
    print("\nAlle tester PASS")
