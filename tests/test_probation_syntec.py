from app.services.rules_engine import compute_probation_bounds

def test_syntec_etam_245():
    b, r, _ = compute_probation_bounds(1486, "non-cadre", "2025-01-01", coeff=245)
    assert b["max_months"] == 2

def test_syntec_etam_275():
    b, r, _ = compute_probation_bounds(1486, "non-cadre", "2025-01-01", coeff=275)
    assert b["max_months"] == 3

def test_syntec_ic():
    b, r, _ = compute_probation_bounds(1486, "cadre", "2025-01-01", coeff=120)
    assert b["max_months"] == 4
