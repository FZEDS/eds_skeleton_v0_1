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

