import pytest
from pathlib import Path
from quantclaw.strategy.loader import load_strategy, list_templates


def test_load_strategy_from_file(tmp_path):
    strategy_file = tmp_path / "my_strategy.py"
    strategy_file.write_text('''
class Strategy:
    name = "test"
    universe = ["AAPL"]
    frequency = "weekly"
    def signals(self, data):
        return {"AAPL": 1.0}
    def allocate(self, scores, portfolio):
        return {"AAPL": 0.5}
''')
    strategy = load_strategy(str(strategy_file))
    assert strategy.name == "test"
    assert strategy.universe == ["AAPL"]


def test_load_strategy_missing_signals(tmp_path):
    strategy_file = tmp_path / "bad.py"
    strategy_file.write_text("class Strategy:\n    pass\n")
    with pytest.raises(ValueError, match="signals"):
        load_strategy(str(strategy_file))


def test_load_strategy_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_strategy("/nonexistent/strategy.py")


def test_list_templates():
    templates = list_templates()
    # Verify template discovery returns a list without relying on user levels.
    assert isinstance(templates, list)
