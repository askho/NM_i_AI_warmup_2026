import asyncio
import logging

from bot_controller import BotController
from client import get_ws_url, play
from logging_utils import configure_logging
from policies.BFS_one_bot import policy as BFSOneBotPolicy
from policy_selector import ConstantPolicySelector

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()

    difficulty = "easy"
    if difficulty != "easy":
        logger.error("No policy defined for difficulty '%s'", difficulty)
        raise SystemExit(1)

    policy_instance = BFSOneBotPolicy
    selector = ConstantPolicySelector(policy_instance)
    controller = BotController(policy=policy_instance)

    logger.info("Starting game | difficulty=%s", difficulty)
    ws_url = get_ws_url(difficulty)
    asyncio.run(play(difficulty, ws_url, controller, selector))


if __name__ == "__main__":
    main()
