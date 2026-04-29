import base64
import os
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HTTP_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "poker")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "app")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "app_pass_123")
CLICKHOUSE_TABLE = os.getenv("CLICKHOUSE_TABLE", "raw_hands")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
POPULATION_OUT = ROOT_DIR / "population_hands.txt"
GTO_OUT = ROOT_DIR / "gto_hands.txt"

SOURCE_GTO_HINTS = ("gto", "bot", "solver", "hishands")
SOURCE_POP_HINTS = ("smarthand", "population")
HAND_START_RE = re.compile(r"^(PokerStars Hand #|Hand #)")
STREET_RE = re.compile(r"^\*\*\* (FLOP|TURN|RIVER) \*\*\*")
ACTION_RE = re.compile(r"^(.+?)(?::)? (bets|checks|calls|raises|folds)\b")
BLIND_RE = re.compile(r"^(.+?)(?::)? posts (small blind|big blind)\b")


def _http_query(query: str) -> str:
    params = urllib.parse.urlencode({"database": CLICKHOUSE_DB, "query": query})
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/?{params}"
    req = urllib.request.Request(url=url, method="POST")
    token = base64.b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASSWORD}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _target_file_for_source(source: str) -> Path:
    source_l = source.lower()
    if any(hint in source_l for hint in SOURCE_GTO_HINTS):
        return GTO_OUT
    if any(hint in source_l for hint in SOURCE_POP_HINTS):
        return POPULATION_OUT
    return POPULATION_OUT


def _action_to_code(action: str) -> str:
    return {
        "bets": "B",
        "checks": "X",
        "calls": "C",
        "raises": "R",
        "folds": "F",
    }.get(action, "X")


def _street_key(street_name: str) -> str:
    return {
        "FLOP": "flop",
        "TURN": "turn",
        "RIVER": "river",
    }[street_name]


def _emit_event(
    spot: str,
    formation: str,
    position: str,
    street: str,
    action: str,
    line: str,
    facing_action: str | None,
) -> str:
    parts = [
        f"spot={spot}",
        f"formation={formation}",
        f"position={position}",
        "role=PFR",
        f"street={street}",
        "canAct=true",
        f"action={action}",
        f"line={line}",
    ]
    if facing_action:
        parts.append(f"facingAction={facing_action}")
    return " ".join(parts)


def _extract_events_from_hand(hand_lines: list[str]) -> list[str]:
    if not hand_lines:
        return []

    sb_player = ""
    preflop_raisers: list[str] = []
    pfr_player = ""
    street = "PREFLOP"
    postflop_actions: dict[str, list[tuple[str, str]]] = defaultdict(list)
    is_bombpot = False

    for line in hand_lines:
        line = line.strip()
        if line == "BombPot":
            is_bombpot = True

        blind_m = BLIND_RE.match(line)
        if blind_m:
            player, blind_type = blind_m.groups()
            if blind_type == "small blind":
                sb_player = player
            continue

        street_m = STREET_RE.match(line)
        if street_m:
            street = street_m.group(1)
            continue

        action_m = ACTION_RE.match(line)
        if not action_m:
            continue

        player, action = action_m.groups()
        if street == "PREFLOP":
            if action == "raises":
                preflop_raisers.append(player)
                pfr_player = player
            continue

        if street in {"FLOP", "TURN", "RIVER"}:
            postflop_actions[street].append((player, action))

    if is_bombpot or not pfr_player:
        return []

    formation = "BB_SB" if pfr_player == sb_player else "BB_BTN"
    position = "OOP" if pfr_player == sb_player else "IP"
    spot = "3BP" if len(preflop_raisers) >= 2 else "SRP"

    pfr_line_codes: list[str] = []
    events: list[str] = []
    for street_name in ("FLOP", "TURN", "RIVER"):
        acts = postflop_actions.get(street_name, [])
        if not acts:
            continue

        current_street_action = None
        current_street_facing = None
        for idx, (player, action) in enumerate(acts):
            if player != pfr_player:
                continue
            current_street_action = action
            if idx > 0:
                prev_player, prev_action = acts[idx - 1]
                if prev_player != pfr_player and prev_action in {"bets", "raises"}:
                    current_street_facing = "raise" if prev_action == "raises" else "bet"
            break

        if not current_street_action:
            continue

        pfr_line_codes.append(_action_to_code(current_street_action))
        events.append(
            _emit_event(
                spot=spot,
                formation=formation,
                position=position,
                street=_street_key(street_name),
                action=current_street_action.rstrip("s"),
                line="-".join(pfr_line_codes),
                facing_action=current_street_facing,
            )
        )
    return events


def main() -> None:
    query = f"SELECT source, line FROM {CLICKHOUSE_TABLE} FORMAT TabSeparated"
    raw = _http_query(query)
    pop_lines: list[str] = []
    gto_lines: list[str] = []

    source_to_lines: dict[str, list[str]] = defaultdict(list)
    for row in raw.splitlines():
        if not row.strip():
            continue
        parts = row.split("\t", 1)
        if len(parts) != 2:
            continue
        source_to_lines[parts[0]].append(parts[1])

    for source, lines in source_to_lines.items():
        target = _target_file_for_source(source)
        hand_buffer: list[str] = []
        for line in lines:
            if HAND_START_RE.match(line):
                if hand_buffer:
                    events = _extract_events_from_hand(hand_buffer)
                    if target == GTO_OUT:
                        gto_lines.extend(events)
                    else:
                        pop_lines.extend(events)
                hand_buffer = [line]
            else:
                hand_buffer.append(line)
        if hand_buffer:
            events = _extract_events_from_hand(hand_buffer)
            if target == GTO_OUT:
                gto_lines.extend(events)
            else:
                pop_lines.extend(events)

    POPULATION_OUT.write_text(
        "# Auto-generated from ClickHouse raw_hands (PokerStars parser, best effort)\n"
        + "\n".join(pop_lines)
        + ("\n" if pop_lines else ""),
        encoding="utf-8",
    )
    GTO_OUT.write_text(
        "# Auto-generated from ClickHouse raw_hands (PokerStars parser, best effort)\n"
        + "\n".join(gto_lines)
        + ("\n" if gto_lines else ""),
        encoding="utf-8",
    )

    print(f"population lines: {len(pop_lines)} -> {POPULATION_OUT}")
    print(f"gto lines: {len(gto_lines)} -> {GTO_OUT}")


if __name__ == "__main__":
    main()
