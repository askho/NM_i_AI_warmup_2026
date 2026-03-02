import asyncio
from client import get_ws_url, main, play
import logging

from bot_controller import BotController
from policy_selector import ConstantPolicySelector

from policies.greedy import policy as greedy_policy  # example function-policy
from policies.BFS_one_bot import policy as BFSOneBotPolicy  # example object-policy


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

def main():
    difficulty = "easy"

    if difficulty == "easy":
        policy_instance = BFSOneBotPolicy
    else: 
        # raise NotImplementedError(f"No policy defined for difficulty '{difficulty}'")
        print(f"No policy defined for difficulty '{difficulty}', exiting.")
        raise SystemExit(0)


    selector = ConstantPolicySelector(policy_instance)
    controller = BotController(policy=policy_instance)

    logger.info(f"Starting game | difficulty={difficulty}")
    ws_url = get_ws_url(difficulty)  # sync
    asyncio.run(play(difficulty, ws_url, controller, selector))

if __name__ == "__main__":
    main()
    