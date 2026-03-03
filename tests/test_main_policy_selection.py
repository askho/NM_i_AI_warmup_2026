import importlib
import sys
import types

from policies.optimized_multi_bot import OptimizedMultiBotPolicy


def _load_main_module():
    if "client" not in sys.modules:
        client_stub = types.ModuleType("client")
        client_stub.get_ws_url = lambda difficulty: "ws://example"
        client_stub.play = lambda *args, **kwargs: None
        sys.modules["client"] = client_stub
    return importlib.import_module("main")


def test_easy_difficulty_uses_easy_policy():
    main_module = _load_main_module()
    policy = main_module.select_policy_for_difficulty("easy")
    assert callable(policy)
    assert not isinstance(policy, OptimizedMultiBotPolicy)


def test_non_easy_difficulty_uses_optimized_multi_bot_policy():
    main_module = _load_main_module()
    policy = main_module.select_policy_for_difficulty("medium")
    assert isinstance(policy, OptimizedMultiBotPolicy)
