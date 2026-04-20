import pytest
from quantclaw.plugins.interfaces import BrokerPlugin, DataPlugin, EnginePlugin, AssetPlugin
from quantclaw.plugins.manager import PluginManager
import pandas as pd


def test_broker_interface_is_abstract():
    with pytest.raises(TypeError):
        BrokerPlugin()


def test_data_interface_is_abstract():
    with pytest.raises(TypeError):
        DataPlugin()


def test_engine_interface_is_abstract():
    with pytest.raises(TypeError):
        EnginePlugin()


def test_asset_interface_is_abstract():
    with pytest.raises(TypeError):
        AssetPlugin()


class MockDataPlugin(DataPlugin):
    name = "mock_data"

    def fetch_ohlcv(self, symbol, start, end, freq="1d"):
        return pd.DataFrame({"close": [100, 101]})

    def fetch_fundamentals(self, symbol):
        return {"pe_ratio": 25}

    def list_symbols(self):
        return ["AAPL", "MSFT"]

    def validate_key(self):
        return True


def test_register_and_get_plugin():
    pm = PluginManager()
    pm.register("data", "mock_data", MockDataPlugin)
    plugin = pm.get("data", "mock_data")
    assert plugin is not None
    assert plugin.name == "mock_data"


def test_list_plugins():
    pm = PluginManager()
    pm.register("data", "mock_data", MockDataPlugin)
    assert "mock_data" in pm.list_plugins("data")


def test_get_unknown_plugin():
    pm = PluginManager()
    assert pm.get("data", "nonexistent") is None
