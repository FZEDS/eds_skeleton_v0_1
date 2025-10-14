from app.services.rules_engine import compute_salary_minimum


def test_salary_min_syntec_ic_100():
    # Syntec (1486), IC coef 100 → base 2240; ratio 0.95 → 2128 (> SMIC 1801.80)
    minima, rule, _ = compute_salary_minimum(
        idcc=1486,
        categorie="cadre",
        coeff=100,
        work_time_mode="standard",
        weekly_hours=35,
        as_of="2025-01-01",
    )
    assert round(minima["monthly_min_eur"], 2) == 2128.00
    assert round(minima["base_min_eur"], 2) == 2240.00
    assert "ccn_monthly_ratio_0.95" in set(minima.get("applied", []))


def test_salary_min_hcr_coeff_121():
    # HCR (1979), coeff 121 → 1862.56 (ratio 1.00), supérieur au SMIC
    minima, rule, _ = compute_salary_minimum(
        idcc=1979,
        categorie="non-cadre",
        coeff=121,
        work_time_mode="standard",
        weekly_hours=35,
        as_of="2025-01-01",
    )
    assert round(minima["monthly_min_eur"], 2) == 1862.56
    assert round(minima["base_min_eur"], 2) == 1862.56


def test_salary_min_2216_coeff_500():
    # 2216, coeff 500 → 2143.66 (ratio 1.00)
    minima, rule, _ = compute_salary_minimum(
        idcc=2216,
        categorie="non-cadre",
        coeff=500,
        work_time_mode="standard",
        weekly_hours=35,
        as_of="2025-09-01",
    )
    assert round(minima["monthly_min_eur"], 2) == 2143.66
    assert round(minima["base_min_eur"], 2) == 2143.66


def test_salary_min_0016_trm_ouvrier():
    # CCN 0016 — Ouvriers TRM/AAT, coefficient 138M (GAR 22 785,14 €)
    minima, rule, _ = compute_salary_minimum(
        idcc=16,
        categorie="non-cadre",
        coeff=None,
        work_time_mode="standard",
        weekly_hours=35,
        classification_level="Groupe 6 - 138M",
        annexe="I",
        segment="TRM_AAT",
        statut="sedentaire",
        as_of="2025-05-01",
    )
    assert round(minima["monthly_min_eur"], 2) == 1898.76
    assert round(minima["base_min_eur"], 2) == 1898.76


def test_salary_min_0016_trm_roulant_equiv_169():
    # CCN 0016 — Ouvriers TRM/AAT roulants (équivalence 169h), coefficient 138M
    minima, rule, _ = compute_salary_minimum(
        idcc=16,
        categorie="non-cadre",
        coeff=None,
        work_time_mode="standard",
        weekly_hours=39,
        classification_level="Ouvrier 138M",
        annexe="I",
        segment="TRM_AAT",
        statut="roulant",
        as_of="2025-05-01",
    )
    assert round(minima["monthly_min_eur"], 2) == 2167.35


def test_salary_min_0016_trm_roulant_longue_distance_43h():
    # CCN 0016 — Ouvriers TRM/AAT roulants (longue distance 43h), coefficient 115M
    # GAR mensuel (200h) à l'embauche = 2 683,56 €
    minima, rule, _ = compute_salary_minimum(
        idcc=16,
        categorie="non-cadre",
        coeff=None,
        work_time_mode="standard",
        weekly_hours=43,
        classification_level="Ouvrier 115M",
        annexe="I",
        segment="TRM_AAT",
        statut="roulant",
        as_of="2025-05-01",
    )
    assert round(minima["monthly_min_eur"], 2) == 2683.56
