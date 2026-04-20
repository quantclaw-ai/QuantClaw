"""Plugin manager: register, discover, and instantiate plugins."""
from __future__ import annotations
from typing import Type, Any
from importlib.metadata import entry_points


class PluginManager:
    def __init__(self):
        self._registry: dict[str, dict[str, Type]] = {
            "broker": {},
            "data": {},
            "engine": {},
            "asset": {},
        }
        self._instances: dict[str, dict[str, Any]] = {
            "broker": {},
            "data": {},
            "engine": {},
            "asset": {},
        }

    def register(self, plugin_type: str, name: str, cls: Type):
        if plugin_type not in self._registry:
            self._registry[plugin_type] = {}
        self._registry[plugin_type][name] = cls

    def get(self, plugin_type: str, name: str) -> Any | None:
        if name not in self._instances.get(plugin_type, {}):
            cls = self._registry.get(plugin_type, {}).get(name)
            if cls is None:
                return None
            instance = cls()
            if plugin_type == "data":
                from quantclaw.plugins.data_cache import CachedDataPlugin
                instance = CachedDataPlugin(instance)
            self._instances[plugin_type][name] = instance
        return self._instances[plugin_type].get(name)

    def list_plugins(self, plugin_type: str) -> list[str]:
        return list(self._registry.get(plugin_type, {}).keys())

    def discover(self):
        eps = entry_points()
        quantclaw_eps = (
            eps.get("quantclaw.plugins", [])
            if isinstance(eps, dict)
            else eps.select(group="quantclaw.plugins")
        )
        for ep in quantclaw_eps:
            try:
                cls = ep.load()
                for ptype in ("broker", "data", "engine", "asset"):
                    if ep.name.startswith(ptype + "_"):
                        self.register(ptype, ep.name, cls)
                        break
            except Exception:
                pass

    def install(self, plugin_name: str) -> bool:
        import subprocess

        result = subprocess.run(
            ["pip", "install", f"quantclaw-{plugin_name}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.discover()
            return True
        return False

    def uninstall(self, plugin_name: str) -> bool:
        import subprocess

        result = subprocess.run(
            ["pip", "uninstall", "-y", f"quantclaw-{plugin_name}"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
