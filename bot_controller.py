import logging
logger = logging.getLogger(__name__)

def decide(bot, state):
    bot_id = bot["id"]
    x, y = bot["position"]
    drop_off = state["drop_off"]

    logger.debug(f"[Bot {bot_id}] Position: {(x, y)} | Inventory: {bot['inventory']}")

    # Drop off if at drop zone with items
    if bot["inventory"] and [x, y] == drop_off:
        logger.info(f"[Bot {bot_id}] Dropping off items at {drop_off}")
        return {"bot": bot_id, "action": "drop_off"}

    # If full inventory, go to drop-off
    if len(bot["inventory"]) >= 3:
        logger.debug(f"[Bot {bot_id}] Inventory full, moving to drop-off")
        return move_toward(bot_id, x, y, drop_off)

    # Find active order
    active = next((o for o in state["orders"] if o["status"] == "active"), None)
    if not active:
        logger.debug(f"[Bot {bot_id}] No active order, waiting")
        return {"bot": bot_id, "action": "wait"}

    needed = list(active["items_required"])
    for d in active["items_delivered"]:
        if d in needed:
            needed.remove(d)

    logger.debug(f"[Bot {bot_id}] Items needed: {needed}")

    # If adjacent to needed item → pick up
    for item in state["items"]:
        if item["type"] in needed:
            ix, iy = item["position"]
            if abs(ix - x) + abs(iy - y) == 1:
                logger.info(f"[Bot {bot_id}] Picking up {item['type']} ({item['id']})")
                return {
                    "bot": bot_id,
                    "action": "pick_up",
                    "item_id": item["id"],
                }

    # Move toward nearest needed item
    for item in state["items"]:
        if item["type"] in needed:
            logger.debug(f"[Bot {bot_id}] Moving toward item {item['type']} at {item['position']}")
            return move_toward(bot_id, x, y, item["position"])

    # If holding something but nothing else needed → deliver
    if bot["inventory"]:
        logger.debug(f"[Bot {bot_id}] Holding items but none needed, moving to drop-off")
        return move_toward(bot_id, x, y, drop_off)

    logger.debug(f"[Bot {bot_id}] Nothing to do, waiting")
    return {"bot": bot_id, "action": "wait"}


def move_toward(bot_id, x, y, target):
    tx, ty = target

    if abs(tx - x) > abs(ty - y):
        action = "move_right" if tx > x else "move_left"
    elif ty != y:
        action = "move_down" if ty > y else "move_up"
    else:
        action = "wait"

    logger.debug(f"[Bot {bot_id}] Moving {action} toward {target}")
    return {"bot": bot_id, "action": action}

def get_actions(state) -> dict:
    bots = state["bots"]

    action_list = []
    for bot in bots:
        decision = decide(bot, state)
        action_list.append(decision)
    
    return {"actions" : action_list}