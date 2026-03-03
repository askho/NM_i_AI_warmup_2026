import asyncio
import logging
import os

from bot_controller import BotController
from logging_utils import configure_logging
from policies.BFS_one_bot import policy as single_bot_policy
from policies.optimized_multi_bot import OptimizedMultiBotPolicy
from policy_selector import ConstantPolicySelector

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    from client import get_ws_url, play

    difficulty = os.getenv("DIFFICULTY", "easy").strip().lower()

    if difficulty == "easy":
        policy_instance = single_bot_policy
    else:
        policy_instance = OptimizedMultiBotPolicy(horizon=8, replan_every=1)

    selector = ConstantPolicySelector(policy_instance)
    controller = BotController(policy=policy_instance)

    logger.info("Starting game | difficulty=%s", difficulty)
    ws_url = get_ws_url(difficulty)
    asyncio.run(play(difficulty, ws_url, controller, selector))


if __name__ == "__main__":
    main()
