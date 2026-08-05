"""
data_loader.py — Parse JSONL event logs and config files for the dashboard.

Provides:
    - load_config()        : Load default.json + all scenario configs
    - load_log(path)       : Parse a JSONL log file into a list of event dicts
    - get_available_logs() : Discover all .jsonl files under logs/
    - build_chain_data()   : Extract block chain structure from events
    - build_validator_network() : Build node/edge data for Cytoscape
    - build_event_timeline()    : Build timeline data for Plotly Gantt
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
LOGS_DIR = ROOT / "logs"


# ── colour palette (used by layouts too) ──────────────────────────────────────
EVENT_COLOURS: dict[str, str] = {
    "SCENARIO_START": "#6C8EBF",
    "SCENARIO_END":   "#6C8EBF",
    "NODE_INIT":      "#82B366",
    "PROPOSE":        "#D6A520",
    "PREVOTE":        "#A8D08D",
    "PRECOMMIT":      "#F4A460",
    "LOCK":           "#FF8C00",
    "FINALIZE":       "#00AA44",
    "EQUIVOCATION":   "#CC0000",
    "CRASH":          "#8B0000",
    "RESTART":        "#9370DB",
    "TIMEOUT":        "#708090",
    "ROUND_CHANGE":   "#4682B4",
    "SEND":           "#B0C4DE",
    "DELIVER":        "#87CEEB",
    "DROP":           "#DC143C",
    "DELAY":          "#DAA520",
    "DUPLICATE":      "#FF69B4",
    "REJECT":         "#CD5C5C",
    "PEER_BLOCK":     "#696969",
    "PEER_UNBLOCK":   "#32CD32",
}

NODE_COLOURS: dict[str, str] = {
    "normal":       "#4A90D9",
    "proposer":     "#F5A623",
    "byzantine":    "#D0021B",
    "crashed":      "#9B9B9B",
    "system":       "#7ED321",
}


# ── config loaders ─────────────────────────────────────────────────────────────

def load_default_config() -> dict[str, Any]:
    """Load config/default.json."""
    path = CONFIG_DIR / "default.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_scenario_configs() -> dict[str, dict[str, Any]]:
    """
    Load all scenario JSON files from config/.
    Returns a dict keyed by scenario_id.
    """
    scenarios: dict[str, dict] = {}
    for p in CONFIG_DIR.glob("scenario_*.json"):
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        sid = data.get("scenario_id", p.stem)
        scenarios[sid] = data
    return scenarios


# ── log discovery & loading ────────────────────────────────────────────────────

def get_available_logs() -> list[dict[str, str]]:
    """
    Walk logs/ and return a list of dicts:
        { "label": "noop / test_run_noop", "value": "<absolute path>" }
    Sorted alphabetically.
    """
    results = []
    for p in sorted(LOGS_DIR.rglob("*.jsonl")):
        rel = p.relative_to(LOGS_DIR)
        label = str(rel.with_suffix("")).replace("\\", " / ").replace("/", " / ")
        results.append({"label": label, "value": str(p)})
    return results


def load_log(path: str | Path) -> list[dict[str, Any]]:
    """
    Parse a JSONL file and return a list of event dicts.
    Invalid / empty lines are skipped silently.
    """
    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ── derived data builders ──────────────────────────────────────────────────────

def build_chain_data(events: list[dict]) -> list[dict[str, Any]]:
    """
    Extract FINALIZE events and build a chain node list.

    Each item:
        {
            "height":     int,
            "round":      int,
            "node_id":    str,
            "event_no":   int,
            "logical_time": int,
            "block_hash": str | None,
            "tx_count":   int,
        }
    """
    chain = []
    for ev in events:
        if ev.get("event_type") != "FINALIZE":
            continue
        details = ev.get("details", {})
        chain.append({
            "height":       ev.get("height", 0),
            "round":        ev.get("round", 0),
            "node_id":      ev.get("node_id", ""),
            "event_no":     ev.get("event_no", 0),
            "logical_time": ev.get("logical_time", 0),
            "block_hash":   details.get("block_hash"),
            "tx_count":     details.get("tx_count", 0),
        })
    # Sort by height then round
    chain.sort(key=lambda x: (x["height"], x["round"]))
    return chain


def get_validator_ids(events: list[dict]) -> list[str]:
    """
    Return an ordered list of validator node_ids found in NODE_INIT events.
    Falls back to any node_id that starts with 'validator_'.
    """
    seen: list[str] = []
    for ev in events:
        if ev.get("event_type") == "NODE_INIT":
            nid = ev.get("node_id", "")
            if nid and nid not in seen:
                seen.append(nid)
    if not seen:
        # Fallback: collect from all events
        for ev in events:
            nid = ev.get("node_id", "")
            if nid.startswith("validator_") and nid not in seen:
                seen.append(nid)
    seen.sort(key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0)
    return seen


def build_cytoscape_elements(
    events: list[dict],
    scenario_cfg: dict | None = None,
) -> list[dict]:
    """
    Build Cytoscape node + edge elements for the validator network graph.

    Nodes  — one per validator + one 'system' node.
    Edges  — created for every SEND / DELIVER / DROP / DELAY event that has
             both 'from_node' and 'to_node' in details (future log enrichment).
             For now a full-mesh edge set is generated so the topology is visible.
    """
    validators = get_validator_ids(events)
    byzantine: list[int] = []
    crashed: set[str] = set()

    if scenario_cfg:
        byzantine = scenario_cfg.get("byzantine_nodes", [])

    # Track crash/restart states
    for ev in events:
        et = ev.get("event_type", "")
        nid = ev.get("node_id", "")
        if et == "CRASH":
            crashed.add(nid)
        elif et == "RESTART" and nid in crashed:
            crashed.discard(nid)

    elements: list[dict] = []

    # ── validator nodes ──
    for nid in validators:
        idx_str = nid.split("_")[-1]
        idx = int(idx_str) if idx_str.isdigit() else -1
        if nid in crashed:
            colour = NODE_COLOURS["crashed"]
            status = "crashed"
        elif idx in byzantine:
            colour = NODE_COLOURS["byzantine"]
            status = "byzantine"
        else:
            colour = NODE_COLOURS["normal"]
            status = "normal"

        elements.append({
            "data": {
                "id":     nid,
                "label":  nid.replace("validator_", "V"),
                "colour": colour,
                "status": status,
                "type":   "validator",
            }
        })

    # ── system node ──
    elements.append({
        "data": {
            "id":     "system",
            "label":  "System",
            "colour": NODE_COLOURS["system"],
            "status": "normal",
            "type":   "system",
        }
    })

    # ── edges: full mesh between validators (topology visualisation) ──
    topology = (scenario_cfg or {}).get("topology", "full_mesh")
    if topology == "full_mesh":
        for i, a in enumerate(validators):
            for b in validators[i + 1:]:
                elements.append({
                    "data": {
                        "id":     f"{a}__{b}",
                        "source": a,
                        "target": b,
                        "label":  "",
                    }
                })

    # ── edges: system → each validator (init) ──
    for nid in validators:
        elements.append({
            "data": {
                "id":     f"system__{nid}",
                "source": "system",
                "target": nid,
                "label":  "init",
            }
        })

    return elements


def build_event_timeline(events: list[dict]) -> list[dict[str, Any]]:
    """
    Convert raw events into timeline rows for Plotly scatter / bar chart.

    Returns list of dicts:
        { "event_no", "logical_time", "node_id", "event_type", "colour", "label" }
    """
    rows = []
    for ev in events:
        et = ev.get("event_type", "UNKNOWN")
        rows.append({
            "event_no":     ev.get("event_no", 0),
            "logical_time": ev.get("logical_time", 0),
            "node_id":      ev.get("node_id", "system"),
            "event_type":   et,
            "height":       ev.get("height", 0),
            "round":        ev.get("round", 0),
            "colour":       EVENT_COLOURS.get(et, "#AAAAAA"),
            "label":        f"[{ev.get('event_no')}] {et}",
            "details":      json.dumps(ev.get("details", {}), ensure_ascii=False),
        })
    return rows


def build_vote_matrix(
    events: list[dict],
    height: int,
    round_: int,
) -> dict[str, Any]:
    """
    Build vote matrix data for a specific (height, round).

    Returns:
        {
            "validators": [...],
            "prevotes":   { validator_id: block_hash | "NIL" | None },
            "precommits": { validator_id: block_hash | "NIL" | None },
        }
    """
    validators = get_validator_ids(events)
    prevotes: dict[str, str | None] = {v: None for v in validators}
    precommits: dict[str, str | None] = {v: None for v in validators}

    for ev in events:
        if ev.get("height") != height or ev.get("round") != round_:
            continue
        et = ev.get("event_type")
        nid = ev.get("node_id", "")
        details = ev.get("details", {})
        bh = details.get("block_hash") or "NIL"

        if et == "PREVOTE" and nid in prevotes:
            prevotes[nid] = bh
        elif et == "PRECOMMIT" and nid in precommits:
            precommits[nid] = bh

    return {
        "validators": validators,
        "prevotes":   prevotes,
        "precommits": precommits,
    }


def summarise_log(events: list[dict]) -> dict[str, Any]:
    """
    Compute high-level stats from event list.

    Returns dict with:
        total_events, num_validators, scenario_id, seed, spec_version,
        max_height, finalized_count, equivocation_count,
        crash_count, timeout_count
    """
    total = len(events)
    scenario_id = ""
    seed = 0
    spec_version = ""
    num_validators = 0
    max_height = 0
    finalized = 0
    equivocations = 0
    crashes = 0
    timeouts = 0

    for ev in events:
        et = ev.get("event_type", "")
        h = ev.get("height", 0)
        if h > max_height:
            max_height = h
        if et == "SCENARIO_START":
            d = ev.get("details", {})
            scenario_id = d.get("scenario_id", "")
            seed = d.get("seed", 0)
            spec_version = d.get("spec_version", "")
            num_validators = d.get("num_validators", 0)
        elif et == "FINALIZE":
            finalized += 1
        elif et == "EQUIVOCATION":
            equivocations += 1
        elif et == "CRASH":
            crashes += 1
        elif et == "TIMEOUT":
            timeouts += 1

    return {
        "total_events":       total,
        "num_validators":     num_validators,
        "scenario_id":        scenario_id,
        "seed":               seed,
        "spec_version":       spec_version,
        "max_height":         max_height,
        "finalized_count":    finalized,
        "equivocation_count": equivocations,
        "crash_count":        crashes,
        "timeout_count":      timeouts,
    }
