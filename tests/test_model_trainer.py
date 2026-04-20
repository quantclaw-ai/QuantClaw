"""Tests for training script generator."""
import pytest
from quantclaw.sandbox.model_trainer import generate_training_script


def test_generate_gradient_boosting_script():
    script = generate_training_script(
        factors=[{"name": "momentum_5d", "code": "df['close'].pct_change(5)"}],
        symbols=["AAPL"],
        model_type="gradient_boosting",
        model_params={},
        model_id="test_model",
        forward_period=5,
    )
    assert "GradientBoostingClassifier" in script
    assert "momentum_5d" in script
    assert "test_model" in script
    assert "json.dumps" in script


def test_generate_random_forest_script():
    script = generate_training_script(
        factors=[{"name": "vol", "code": "df['close'].rolling(20).std()"}],
        symbols=["AAPL"],
        model_type="random_forest",
        model_params={"n_estimators": 100},
        model_id="rf_test",
        forward_period=5,
    )
    assert "RandomForestClassifier" in script
    assert "n_estimators" in script


def test_generate_ridge_script():
    script = generate_training_script(
        factors=[{"name": "mom", "code": "df['close'].pct_change(10)"}],
        symbols=["AAPL"],
        model_type="ridge",
        model_params={},
        model_id="ridge_test",
        forward_period=5,
    )
    assert "RidgeClassifier" in script


def test_script_saves_model():
    script = generate_training_script(
        factors=[{"name": "f1", "code": "df['close'].pct_change(5)"}],
        symbols=["AAPL"],
        model_type="gradient_boosting",
        model_params={},
        model_id="persist_test",
        forward_period=5,
    )
    assert "models" in script  # Model save directory
    assert "joblib.dump" in script


def test_unknown_model_type_raises():
    from quantclaw.sandbox.model_trainer import UnknownModelType
    with pytest.raises(UnknownModelType):
        generate_training_script(
            factors=[], symbols=[], model_type="nonexistent",
            model_params={}, model_id="x", forward_period=5,
        )
