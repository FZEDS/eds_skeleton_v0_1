from app.services.rules_engine import compute_leave_minimum


def test_conges_syntec_bonus_10y():
    # Syntec (1486) bonus ancienneté en jours ouvrés : à 10 ans → +2
    res, rule, _ = compute_leave_minimum(
        idcc=1486,
        anciennete_months=120,
        unit="ouvrés",
        as_of="2025-01-01",
    )
    assert res["min_days"] == 25
    assert res["suggested_days"] == 27
    assert rule and (rule.get("source") in {"ccn", "code_travail"})


def test_conges_hcr_base_legal():
    # HCR (1979) — pas de bonus générique → suggestion = base légale
    res, rule, _ = compute_leave_minimum(
        idcc=1979,
        anciennete_months=0,
        unit="ouvrés",
        as_of="2025-01-01",
    )
    assert res["min_days"] == 25
    assert res["suggested_days"] == 25
    assert rule and rule.get("source") == "code_travail"


def test_conges_2216_bonus_10y():
    # 2216 — bonus ancienneté à 10 ans: +1 (ouvrés)
    res, rule, _ = compute_leave_minimum(
        idcc=2216,
        anciennete_months=120,
        unit="ouvrés",
        as_of="2025-09-01",
    )
    assert res["min_days"] == 25
    assert res["suggested_days"] == 26
    assert rule and rule.get("source") == "ccn"

