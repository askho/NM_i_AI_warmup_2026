import asyncio
import websockets
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import json

from bot_controller import BotController
from policy_selector import PolicySelector

import logging





logger = logging.getLogger(__name__)

GAME_URL = "https://app.ainm.no/challenge"
STATE_PATH = Path(__file__).resolve().parent / "state.json"
DUMP_DIR = Path(__file__).resolve().parent / "debug_html"
DUMP_DIR.mkdir(exist_ok=True)

# Map from your internal difficulty string to the UI label text
DIFFICULTY_LABEL = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
    "expert": "Expert",
}

def click_difficulty_card(page, label: str) -> None:
    logger.debug(f"Clicking difficulty card: {label}")
    card = page.get_by_role("button", name=re.compile(label, re.IGNORECASE))
    card.wait_for(state="visible", timeout=20_000)
    card.click()

def click_copy_button_if_present(page) -> None:
    try:
        logger.debug("Looking for 'Copy Token' button")
        button = page.get_by_role("button", name=re.compile("copy token", re.IGNORECASE))
        button.wait_for(state="visible", timeout=3_000)
        if button.is_enabled():
            logger.debug("'Copy Token' button found & enabled -> clicking")
            button.click()
        else:
            logger.debug("'Copy Token' button found but disabled")
    except PlaywrightTimeoutError:
        logger.debug("'Copy Token' button not found (timeout)")

def _save_html(page, name: str) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"{ts}_{name}.html"
    path.write_text(page.content(), encoding="utf-8")
    logger.debug(f"Saved HTML snapshot: {path}")
    return path

def _extract_ws_url_from_page(page) -> str:
    logger.debug("Waiting for page text to contain wss://...token=...")

    # Wait until the page text contains the ws url with token
    page.wait_for_function(
        """() => {
            const t = document.body.innerText || "";
            return t.includes("wss://") && t.includes("token=");
        }""",
        timeout=120_000,
    )

    text = page.evaluate("() => document.body.innerText || ''")
    m = re.search(r"(wss://[^\s]+token=[^\s]+)", text)
    if not m:
        logger.error("Failed to extract ws url: regex found no match")
        raise RuntimeError("Could not find a wss://...token=... URL in page text.")

    ws_url = m.group(1).strip()
    logger.info("Extracted WebSocket URL successfully")
    logger.debug(f"WS_URL: {ws_url}")
    return ws_url

def get_ws_url(difficulty: str, headless: bool = True) -> str:
    """
    Uses saved auth (state.json) to open the challenge page, select a difficulty,
    and return the WebSocket URL (wss://...token=...).

    Also saves HTML snapshots to ./debug_html/.
    """
    logger.info(f"Getting WS URL | difficulty={difficulty} | headless={headless}")

    if not STATE_PATH.exists():
        logger.error(f"Missing state.json at: {STATE_PATH}")
        raise FileNotFoundError(f"state.json not found at: {STATE_PATH}")

    key = difficulty.strip().lower()
    if key not in DIFFICULTY_LABEL:
        logger.error(f"Unknown difficulty: {difficulty}")
        raise ValueError(f"Unknown difficulty '{difficulty}'. Valid: {sorted(DIFFICULTY_LABEL)}")

    label = DIFFICULTY_LABEL[key]

    with sync_playwright() as p:
        logger.debug("Launching Chromium (channel=chrome)")
        browser = p.chromium.launch(channel="chrome", headless=headless)

        logger.debug(f"Creating context with storage_state={STATE_PATH}")
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        logger.info(f"Navigating to {GAME_URL}")
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=120_000)

        # Ensure manual tab is active (safe no-op if already active)
        logger.debug("Ensuring 'Manual' tab is active (best-effort)")
        try:
            page.get_by_role("tab", name="Manual").click(timeout=5_000)
            logger.debug("Clicked 'Manual' tab via role=tab")
        except PlaywrightTimeoutError:
            try:
                page.get_by_text("Manual", exact=True).click(timeout=5_000)
                logger.debug("Clicked 'Manual' tab via text selector")
            except PlaywrightTimeoutError:
                logger.debug("'Manual' tab not found (continuing)")

        _save_html(page, "challenge_before")

        logger.info(f"Selecting difficulty: {label}")
        click_difficulty_card(page, label)

        # Optional: click the UI "Copy Token" button if it exists
        click_copy_button_if_present(page)

        ws_url = _extract_ws_url_from_page(page)
        _save_html(page, f"challenge_after_{key}")

        logger.debug("Closing context and browser")
        context.close()
        browser.close()

        logger.info("WS URL retrieval complete")
        return ws_url


import json
import websockets
from typing import Any, Dict, Optional

# type hints are optional, but nice
from bot_controller import BotController
from policy_selector import PolicySelector, ConstantPolicySelector


async def play(
    difficulty: str,
    WS_URL: str,
    controller: BotController,
    selector: PolicySelector,
) -> None:
    async with websockets.connect(WS_URL) as ws:
        while True:
            state: Dict[str, Any] = json.loads(await ws.recv())

            msg_type = state.get("type")
            if msg_type == "game_over":
                break

            if msg_type != "game_state":
                # ignore unexpected message types safely
                continue

            controller.set_policy(selector.select(difficulty=difficulty, state=state))
            actions_list = controller.act(state)

            await ws.send(json.dumps({"actions": actions_list}))


def start_game(
    difficulty: str,
    controller: Optional[BotController] = None,
    selector: Optional[PolicySelector] = None,
) -> None:
    WS_URL = get_ws_url(difficulty)
    # Provide sane defaults so client.py can be run standalone
    if controller is None:
        controller = BotController(policy=None)
    if selector is None:
        selector = ConstantPolicySelector(lambda state: [])

    logger.info(f"Starting game | difficulty={difficulty}")
    asyncio.run(play(difficulty, WS_URL, controller, selector))


def main():
    difficulty = "easy"
    # start the game when run as a script
    start_game(difficulty)

if __name__ == "__main__":
    main()
