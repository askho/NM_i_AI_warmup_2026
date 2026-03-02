import asyncio
from client import get_ws_url, main, play
import logging

from bot_controller import BotController
from policy_selector import ConstantPolicySelector

from policies.greedy import policy as greedy_policy  # example function-policy
from policies.BFS_one_bot import policy as BFSOneBotPolicy  # example object-policy


class EveryFifthRoundConsoleFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "is_round_summary", False):
            return True
        round_no = getattr(record, "round_no", None)
        return isinstance(round_no, int) and round_no % 5 == 0


class RoundSummaryOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return bool(getattr(record, "is_round_summary", False))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
console_handler.addFilter(EveryFifthRoundConsoleFilter())

summary_file_handler = logging.FileHandler("log.txt", mode="w", encoding="utf-8")
summary_file_handler.setLevel(logging.INFO)
summary_file_handler.setFormatter(formatter)
summary_file_handler.addFilter(RoundSummaryOnlyFilter())

root_logger.handlers.clear()
root_logger.addHandler(console_handler)
root_logger.addHandler(summary_file_handler)

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
    
