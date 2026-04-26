"""Phase 2 acceptance tests — calculations schema.

Run with: pytest -m phase2
"""

import pytest

pytestmark = pytest.mark.phase2


@pytest.mark.phase2
def test_calculation_lines_fk_to_calculations():
    from app.models import CalculationLine

    fks = {fk.target_fullname for fk in CalculationLine.__table__.foreign_keys}
    assert "calculations.id" in fks


@pytest.mark.phase2
def test_calculation_lines_cascade_delete():
    from app.models import CalculationLine

    fk = next(
        fk for fk in CalculationLine.__table__.foreign_keys
        if fk.target_fullname == "calculations.id"
    )
    assert fk.ondelete.upper() == "CASCADE"


@pytest.mark.phase2
def test_calculation_lines_has_numeric_columns():
    from app.models import CalculationLine

    numeric_cols = {"amount", "fee_percent", "gross_usdt", "fee_usdt", "net_usdt"}
    cols = {c.key for c in CalculationLine.__table__.columns}
    assert numeric_cols <= cols


@pytest.mark.phase2
def test_calculation_model_has_client_fields():
    """client_calculated_at, client_request_id, tab_id must be present."""
    from app.models import Calculation

    cols = {c.key for c in Calculation.__table__.columns}
    assert "client_calculated_at" in cols
    assert "client_request_id" in cols
    assert "tab_id" in cols
    assert "experiment_flags" in cols


@pytest.mark.phase2
def test_calculation_client_request_id_nullable():
    from app.models import Calculation

    col = Calculation.__table__.c.client_request_id
    assert col.nullable


@pytest.mark.phase2
def test_calculation_has_currencies_array():
    from app.models import Calculation

    col = Calculation.__table__.c.currencies
    assert col is not None


@pytest.mark.phase2
def test_calculation_above_min_threshold_boolean():
    from app.models import Calculation

    col = Calculation.__table__.c.above_min_threshold
    assert not col.nullable


@pytest.mark.phase2
def test_create_partitions_script_importable():
    """Verify the partition script is syntactically valid."""
    import importlib.util
    import os

    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "create_partitions.py"
    )
    spec = importlib.util.spec_from_file_location("create_partitions", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "create_partitions")
    assert hasattr(mod, "main")
