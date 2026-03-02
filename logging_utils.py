from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict


class _RoundSummaryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return bool(getattr(record, "is_round_summary", False))


class _FullGameFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return bool(getattr(record, "is_game_trace", False) or getattr(record, "is_round_summary", False))


def configure_logging(log_dir: str | Path = ".") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    summary_file = logging.FileHandler(log_dir_path / "log_summary.txt", mode="w", encoding="utf-8")
    summary_file.setLevel(logging.INFO)
    summary_file.setFormatter(formatter)
    summary_file.addFilter(_RoundSummaryFilter())

    full_trace_file = logging.FileHandler(log_dir_path / "log_full.txt", mode="w", encoding="utf-8")
    full_trace_file.setLevel(logging.INFO)
    full_trace_file.setFormatter(formatter)
    full_trace_file.addFilter(_FullGameFilter())

    legacy_file = logging.FileHandler(log_dir_path / "log.txt", mode="w", encoding="utf-8")
    legacy_file.setLevel(logging.INFO)
    legacy_file.setFormatter(formatter)
    legacy_file.addFilter(_RoundSummaryFilter())

    root_logger.handlers.clear()
    root_logger.addHandler(console)
    root_logger.addHandler(summary_file)
    root_logger.addHandler(full_trace_file)
    root_logger.addHandler(legacy_file)


def log_round_snapshot(logger: logging.Logger, state: Dict[str, Any], *, action_count: int | None = None) -> None:
    bots = state.get("bots", [])
    bot_parts = []
    for b in bots if isinstance(bots, list) else []:
        if not isinstance(b, dict):
            continue
        bot_id = b.get("id")
        pos = _to_pos(b.get("position"))
        inv_count = len(b.get("inventory", []) or [])
        bot_parts.append(f"{bot_id}@{pos} inv={inv_count}")

    message = (
        "Round=%s/%s score=%s bots=%s items=%s orders=%s%s"
        % (
            state.get("round"),
            state.get("max_rounds"),
            state.get("score"),
            ", ".join(bot_parts) if bot_parts else "-",
            len(state.get("items", []) or []),
            len(state.get("orders", []) or []),
            f" actions={action_count}" if action_count is not None else "",
        )
    )
    logger.info(
        message,
        extra={
            "is_round_summary": True,
            "is_game_trace": True,
            "round_no": int(state.get("round", -1) or -1),
        },
    )


def log_game_over(logger: logging.Logger, state: Dict[str, Any]) -> None:
    logger.info(
        "GAME OVER round=%s/%s score=%s",
        state.get("round"),
        state.get("max_rounds"),
        state.get("score"),
        extra={"is_round_summary": True, "is_game_trace": True, "round_no": int(state.get("round", -1) or -1)},
    )


def _to_pos(p: Any) -> tuple[int, int]:
    if isinstance(p, dict):
        return int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return int(p[0]), int(p[1])
    return (0, 0)
