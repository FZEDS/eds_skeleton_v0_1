from app.services.rules_resolver import resolve


def test_part_time_guards_1501_exposed():
    # CCN 1501 (restauration rapide) expose des règles temps partiel (coupures/amplitude)
    ctx = {
        "idcc": 1501,
        "categorie": "non-cadre",
        "work_time_mode": "part_time",
        "as_of": "2025-01-01",
    }
    res = resolve("temps_travail", ctx)
    caps = res.get("capabilities", {})
    pt = caps.get("part_time_rules", {})
    assert isinstance(pt, dict) and pt, "part_time_rules should be present"
    # Quelques bornes clés
    assert pt.get("breaks_per_day_max") == 1
    assert pt.get("daily_amplitude_max") == 12
    assert pt.get("min_sequence_hours") == 2
    assert pt.get("forbid_breaks_if_weekly_hours_lt") == 12
    # primes coupures
    assert float(pt.get("break_premium_mg_ratio")) == 0.8
    assert float(pt.get("break_premium_min_eur")) == 3.5

