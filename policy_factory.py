from policies.BFS_one_bot import policy as bfs_one_bot_policy
from policies.optimized_multi_bot import OptimizedMultiBotPolicy


def select_policy_for_difficulty(difficulty: str):
    if difficulty == "easy":
        return bfs_one_bot_policy
    return OptimizedMultiBotPolicy(horizon=8, replan_every=1)
