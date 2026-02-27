def decide(bot, state):
    x, y = bot["position"]
    drop_off = state["drop_off"]
 
    if bot["inventory"] and [x, y] == drop_off:
        return {"bot": bot["id"], "action": "drop_off"}
 
    if len(bot["inventory"]) >= 3:
        return move_toward(bot["id"], x, y, drop_off)
 
    active = next((o for o in state["orders"] if o["status"] == "active"), None)
    if not active:
        return {"bot": bot["id"], "action": "wait"}
 
    needed = list(active["items_required"])
    for d in active["items_delivered"]:
        if d in needed:
            needed.remove(d)
 
    for item in state["items"]:
        if item["type"] in needed:
            ix, iy = item["position"]
            if abs(ix - x) + abs(iy - y) == 1:
                return {"bot": bot["id"], "action": "pick_up", "item_id": item["id"]}
 
    for item in state["items"]:
        if item["type"] in needed:
            return move_toward(bot["id"], x, y, item["position"])
 
    if bot["inventory"]:
        return move_toward(bot["id"], x, y, drop_off)
 
    return {"bot": bot["id"], "action": "wait"}

def move_toward(bot_id, x, y, target):
    tx, ty = target
    if abs(tx - x) > abs(ty - y):
        return {"bot": bot_id, "action": "move_right" if tx > x else "move_left"}
    elif ty != y:
        return {"bot": bot_id, "action": "move_down" if ty > y else "move_up"}
    return {"bot": bot_id, "action": "wait"}