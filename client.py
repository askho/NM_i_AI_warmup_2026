import asyncio
import websockets
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from utils import save_json
import json


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
    card = page.get_by_role("button", name=re.compile(label, re.IGNORECASE))
    card.wait_for(state="visible", timeout=20_000)
    card.click()


def click_copy_button_if_present(page) -> None:
    try:
        button = page.get_by_role("button", name=re.compile("copy token", re.IGNORECASE))
        button.wait_for(state="visible", timeout=3_000)
        if button.is_enabled():
            button.click()
    except PlaywrightTimeoutError:
        pass

def _save_html(page, name: str) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"{ts}_{name}.html"
    path.write_text(page.content(), encoding="utf-8")
    return path

def _extract_ws_url_from_page(page) -> str:
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
        raise RuntimeError("Could not find a wss://...token=... URL in page text.")
    return m.group(1).strip()

def get_ws_url(difficulty: str, headless: bool = True) -> str:
    """
    Uses saved auth (state.json) to open the challenge page, select a difficulty,
    and return the WebSocket URL (wss://...token=...).

    Also saves HTML snapshots to ./debug_html/.
    """
    if not STATE_PATH.exists():
        raise FileNotFoundError(f"state.json not found at: {STATE_PATH}")

    key = difficulty.strip().lower()
    if key not in DIFFICULTY_LABEL:
        raise ValueError(f"Unknown difficulty '{difficulty}'. Valid: {sorted(DIFFICULTY_LABEL)}")

    label = DIFFICULTY_LABEL[key]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=headless)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=120_000)

        # Ensure manual tab is active (safe no-op if already active)
        try:
            page.get_by_role("tab", name="Manual").click(timeout=5_000)
        except PlaywrightTimeoutError:
            try:
                page.get_by_text("Manual", exact=True).click(timeout=5_000)
            except PlaywrightTimeoutError:
                pass

        _save_html(page, "challenge_before")

        click_difficulty_card(page, label)

        # Optional: click the UI "Copy Token" button if it exists
        click_copy_button_if_present(page)

        ws_url = _extract_ws_url_from_page(page)
        _save_html(page, f"challenge_after_{key}")

        context.close()
        browser.close()
        return ws_url


async def play(difficulty: str, WS_URL: str):
    async with websockets.connect(WS_URL) as ws:
        while True:
            state = await ws.recv()
            return state
            # ... decide actions ...
            #await ws.send('{"actions": [...]}')
#asyncio.run(play())
#       Respond within 2 seconds per round

async def fetch_raw_state(difficulty: str, WS_URL: str):
    async with websockets.connect(WS_URL) as ws:
        while True:
            state = await ws.recv()
            return state
        

def main():
    difficulty = "easy"
    WS_URL  = get_ws_url(difficulty)
    print(WS_URL)
    raw_json = asyncio.run(play("easy", WS_URL))
    state = json.loads(raw_json)
    save_json(state)
    return

if __name__ == "__main__":
    main()
