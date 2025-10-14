from app.services.rules_resolver import resolve


def test_hcr_modalite2_disabled():
    ctx = {
        "idcc": 1979,  # HCR
        "categorie": "non-cadre",
        "work_time_mode": "standard",
        "as_of": "2025-01-01",
    }
    res = resolve("temps_travail", ctx)
    wm = res.get("capabilities", {}).get("work_time_modes", {})
    assert wm.get("forfait_hours_mod2") is False


def test_syntec_modalite2_enabled():
    ctx = {
        "idcc": 1486,  # Syntec
        "categorie": "cadre",
        "work_time_mode": "standard",
        "as_of": "2025-01-01",
    }
    res = resolve("temps_travail", ctx)
    wm = res.get("capabilities", {}).get("work_time_modes", {})
    assert wm.get("forfait_hours_mod2") is True


def test_trv_modulation_capability_and_bounds():
    # CCN 0016 — TRV : modulation exposée avec cadre annuel 1600 h
    ctx = {
        "idcc": 16,
        "categorie": "non-cadre",
        "work_time_mode": "modulation",
        "segment": "TRV",
        "as_of": "2025-05-01",
    }
    res = resolve("temps_travail", ctx)
    wm = res.get("capabilities", {}).get("work_time_modes", {})
    assert wm.get("modulation") is True
    b = res.get("bounds") or {}
    assert int(b.get("annual_hours_max")) == 1600


def test_sanitaire_modulation_bounds_weekly_cap():
    # CCN 0016 — Sanitaire : modulation ≤1600 h; plafond hebdo 42 h
    ctx = {
        "idcc": 16,
        "categorie": "non-cadre",
        "work_time_mode": "modulation",
        "segment": "SANITAIRE",
        "as_of": "2025-05-01",
    }
    res = resolve("temps_travail", ctx)
    b = res.get("bounds") or {}
    assert int(b.get("annual_hours_max")) == 1600
    assert float(b.get("weekly_hours_max")) == 42.0
