"""v2.5 T1.1d acceptance — persona-specific band derivation.

Each persona's `band_rules` should produce distinct entry / target / stop
prices around the live mark. Soros / Druckenmiller / Rogers / Dalio /
retail_degen modulate by `macro_regime`; Buffett / Wood / Burry don't.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from persona.loader import load_dir
from persona.reasoner import _bands_from_priors

YAML_DIR = Path(__file__).resolve().parents[3] / "docs" / "prompts" / "persona"
SPECS = load_dir(YAML_DIR)


def test_every_persona_has_band_rules():
    for slug, spec in SPECS.items():
        assert spec.band_rules is not None, f"{slug} missing band_rules"


def test_buffett_long_with_25pct_target():
    spec = SPECS["buffett"]
    direction, entry, target, stop, horizon, conf = _bands_from_priors(spec, 100.0)
    assert direction == "long"
    # 25% target → ~125; stop 20% below → ~80
    assert target[0] == pytest.approx(125.0, rel=1e-3)
    assert stop == pytest.approx(80.0, rel=1e-3)
    # Buffett's entry band ±1%
    assert entry == pytest.approx((99.0, 101.0), rel=1e-3)
    assert horizon == 730


def test_burry_short_with_inverted_bands():
    spec = SPECS["burry"]
    direction, entry, target, stop, horizon, _conf = _bands_from_priors(spec, 100.0)
    assert direction == "short"
    # Short bands MUST satisfy advice.v1: target_band[1] < entry_band[0] AND stop > entry_band[1]
    assert target[1] < entry[0], f"short violates target_band[1] < entry_band[0]: {target} {entry}"
    assert stop > entry[1], f"short violates stop > entry_band[1]: stop={stop} entry={entry}"
    # 30% target below → ~70 (target_hi); stop 20% above → ~120
    assert target[1] == pytest.approx(70.0, rel=1e-3)
    assert stop == pytest.approx(120.0, rel=1e-3)


def test_soros_target_modulated_by_regime():
    """Soros has macro_regime_modulation=True; bull regime expands target."""
    spec = SPECS["soros"]
    _, _, target_neutral, _, _, _ = _bands_from_priors(spec, 100.0, macro_regime="neutral")
    _, _, target_bull, _, _, _ = _bands_from_priors(spec, 100.0, macro_regime="bull")
    _, _, target_bear, _, _, _ = _bands_from_priors(spec, 100.0, macro_regime="bear")
    # Bull regime targets > neutral targets > bear regime targets (long bias).
    assert target_bull[0] > target_neutral[0] > target_bear[0]


def test_buffett_target_unchanged_by_regime():
    """Buffett has macro_regime_modulation=False — quality holds across regimes."""
    spec = SPECS["buffett"]
    _, _, target_a, _, _, _ = _bands_from_priors(spec, 100.0, macro_regime="bull")
    _, _, target_b, _, _, _ = _bands_from_priors(spec, 100.0, macro_regime="bear")
    assert target_a == target_b


def test_no_band_rules_falls_back_to_flat():
    """Legacy spec without band_rules still emits schema-valid (flat) advice."""
    from dataclasses import replace
    spec = replace(SPECS["buffett"], band_rules=None)
    direction, entry, target, stop, _, _ = _bands_from_priors(spec, 100.0)
    assert direction == "flat"
    assert entry == (100.0, 100.0)
    assert target == (100.0, 100.0)
    assert stop == 100.0


def test_personas_produce_distinct_bands():
    """No two personas should produce identical bands at the same mark."""
    bands_by_slug: dict[str, tuple] = {}
    for slug, spec in SPECS.items():
        band = _bands_from_priors(spec, 100.0)
        bands_by_slug[slug] = band[:4]  # direction, entry, target, stop
    distinct = {tuple(map(_round_band, b)) for b in bands_by_slug.values()}
    # 8 personas should give at least 6 distinct band shapes (allow Buffett-like
    # overlap between similar profiles).
    assert len(distinct) >= 6, (
        f"only {len(distinct)} distinct bands across {len(bands_by_slug)} personas"
    )


def _round_band(b):
    if isinstance(b, tuple):
        return tuple(round(x, 4) for x in b)
    if isinstance(b, float):
        return round(b, 4)
    return b


def test_long_personas_satisfy_advice_v1_invariants():
    """For every long persona, derived bands must satisfy AdviceV1 monotonicity."""
    for slug, spec in SPECS.items():
        if spec.band_rules is None or spec.band_rules.direction_default != "long":
            continue
        _, entry, target, stop, _, _ = _bands_from_priors(spec, 100.0)
        # AdviceV1 long: entry_band[1] < target_band[0] AND stop_loss < entry_band[0]
        assert entry[1] < target[0], f"{slug}: entry_band[1]={entry[1]} >= target_band[0]={target[0]}"
        assert stop < entry[0], f"{slug}: stop_loss={stop} >= entry_band[0]={entry[0]}"


def test_short_personas_satisfy_advice_v1_invariants():
    for slug, spec in SPECS.items():
        if spec.band_rules is None or spec.band_rules.direction_default != "short":
            continue
        _, entry, target, stop, _, _ = _bands_from_priors(spec, 100.0)
        # AdviceV1 short: target_band[1] < entry_band[0] AND stop_loss > entry_band[1]
        assert target[1] < entry[0], f"{slug}: target_band[1]={target[1]} >= entry_band[0]={entry[0]}"
        assert stop > entry[1], f"{slug}: stop_loss={stop} <= entry_band[1]={entry[1]}"


def test_horizon_propagates_from_band_rules():
    """Wood has horizon_days=1825; retail_degen has 30. Both must come through."""
    _, _, _, _, h_wood, _ = _bands_from_priors(SPECS["wood"], 100.0)
    _, _, _, _, h_degen, _ = _bands_from_priors(SPECS["retail_degen"], 100.0)
    assert h_wood == 1825
    assert h_degen == 30
