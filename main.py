import asyncio
from client import get_ws_url, main, play
import logging

from bot_controller import BotController
from policy_selector import ConstantPolicySelector

from policies.greedy import policy as greedy_policy  # example function-policy



logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

def main():
    difficulty = "easy"

    selector = ConstantPolicySelector(greedy_policy)
    controller = BotController(policy=greedy_policy)

    logger.info(f"Starting game | difficulty={difficulty}")
    ws_url = get_ws_url(difficulty)  # sync
    asyncio.run(play(difficulty, ws_url, controller, selector))

if __name__ == "__main__":
    main()
    