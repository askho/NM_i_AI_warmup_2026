from policies.BFS_one_bot import policy as bfs_one_bot_policy
from policies.optimized_multi_bot import OptimizedMultiBotPolicy
from policy_factory import select_policy_for_difficulty


def test_select_policy_easy_uses_single_bot_policy():
    assert select_policy_for_difficulty("easy") is bfs_one_bot_policy


def test_select_policy_non_easy_uses_optimized_multi_bot_policy():
    policy = select_policy_for_difficulty("medium")
    assert isinstance(policy, OptimizedMultiBotPolicy)
