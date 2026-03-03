import asyncio
import logging
import os

from bot_controller import BotController
from client import get_ws_url, play
from logging_utils import configure_logging
from policies.greedy import policy as easy_policy
from policies.optimized_multi_bot import OptimizedMultiBotPolicy
from policy_selector import ConstantPolicySelector

logger = logging.getLogger(__name__)


def select_policy_for_difficulty(difficulty: str):
    return easy_policy if difficulty == "easy" else OptimizedMultiBotPolicy(horizon=8, replan_every=1)


def main() -> None:
    configure_logging()

    difficulty = os.getenv("DIFFICULTY", "easy").strip().lower()

    policy_instance = select_policy_for_difficulty(difficulty)
    selector = ConstantPolicySelector(policy_instance)
    controller = BotController(policy=policy_instance)

    logger.info("Starting game | difficulty=%s | policy=%s", difficulty, type(policy_instance).__name__)
    ws_url = get_ws_url(difficulty)
    asyncio.run(play(difficulty, ws_url, controller, selector))


if __name__ == "__main__":
    main()
