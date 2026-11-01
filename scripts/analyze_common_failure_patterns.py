"""Summarize observable failure chains in the frozen transport cohort; no API calls."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "development-baseline-v5-20261101"


def settlers(state):
    return {str(k) for k, u in state["observation"].get("unit", {}).items()
            if u.get("owner") == state["player_id"] and u.get("type_rule_name") == "Settlers"}


def cities(state):
    return {str(k) for k, c in state["observation"].get("city", {}).items()
            if c.get("owner") == state["player_id"]}


def notices(step):
    return [str(m) for m in step.get("native_messages_after", [])
            if not str(m).lstrip().startswith("{")]


def action(step):
    if "native_action" not in step:
        return "NO_SUBMISSION"
    a = step["native_action"]
    return a[2] if a else "END_TURN"


def examine(row, folder):
    # Read only trajectories, not the much larger request logs or hidden savegames.
    with (folder / "steps.jsonl").open() as f:
        steps = [json.loads(line) for line in f if line.strip()]
    initial = steps[0]["before"]
    initial_cities = cities(initial)
    new_city_seen = False
    critical = None
    restored = []
    famine = []
    landing_events = []
    population = []
    for i, s in enumerate(steps):
        ns = notices(s)
        if any("Famine feared" in m and "lost" in m for m in ns):
            famine.append(s["decision_id"])
        if any("can't build Settlers yet" in m for m in ns):
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            population.append({"decision_id": s["decision_id"], "notices": ns,
                               "next_decision_id": nxt["decision_id"] if nxt else None,
                               "next_action": action(nxt) if nxt else None})
        after = s.get("after")
        if after is None:
            continue  # Missing next state is not evidence of zero units.
        before_units, after_units = settlers(s["before"]), settlers(after)
        new_city_seen |= bool(cities(after) - initial_cities)
        if before_units and not after_units and not new_city_seen and critical is None:
            critical = {"index": i, "decision_id": s["decision_id"],
                        "turn_after": after["turn"], "lost_unit_ids": sorted(before_units),
                        "action": action(s), "notices": ns}
        if critical is not None and i > critical["index"] and after_units:
            restored.append(s["decision_id"])
        a = s.get("native_action")
        if not a or "disembark" not in a[2]:
            continue
        unit_id = str(a[1])
        cargo_before = s["before"].get("own_unit_transport", {}).get(unit_id, {})
        cargo_after = after.get("own_unit_transport", {}).get(unit_id, {})
        if unit_id not in before_units or unit_id not in after_units:
            continue
        if not cargo_before.get("transported") or cargo_after.get("transported"):
            continue
        event = {"unit_id": unit_id, "landing_step": s["decision_id"],
                 "loss_step": None, "next_end_turn": None, "lost_at_next_end_turn": False}
        for later in steps[i + 1:]:
            if not later.get("after"):
                continue
            if action(later) == "END_TURN" and event["next_end_turn"] is None:
                event["next_end_turn"] = later["decision_id"]
            if cities(later["after"]) - initial_cities:
                break
            if unit_id in settlers(later["before"]) and unit_id not in settlers(later["after"]):
                event.update(loss_step=later["decision_id"], loss_action=action(later),
                             notices=notices(later))
                event["lost_at_next_end_turn"] = later["decision_id"] == event["next_end_turn"]
                break
        landing_events.append(event)
    tail = steps[critical["index"] + 1:] if critical else []
    submitted_tail = [s for s in tail if "native_action" in s]
    result = {
        "episode_id": row["episode_id"], "instance_id": int(row["instance_id"]),
        "stop_reason": row["stop_reason"], "env_steps": int(row["env_steps"]),
        "api_calls": int(row["api_calls_total"]), "famine_loss": bool(famine),
        "actual_landing": bool(landing_events),
        "landed_settler_lost_before_city": any(e["loss_step"] for e in landing_events),
        "landed_settler_lost_at_next_end_turn": any(e["lost_at_next_end_turn"] for e in landing_events),
        "all_settlers_lost_before_city": critical is not None,
        "settler_restored_after_total_loss": bool(restored),
        "population_block": bool(population),
        "population_block_with_next_decision": any(e["next_decision_id"] for e in population),
        "post_total_loss_env_steps": len(submitted_tail),
        "post_total_loss_api_calls": sum(len(s["api_calls"]) for s in tail),
        "post_total_loss_end_turns": sum(action(s) == "END_TURN" for s in tail),
        "post_total_loss_produce_settlers": sum(action(s) == "produce_Settlers" for s in tail),
        "post_total_loss_buy_production": sum(action(s) == "city_buy_production" for s in tail),
        "first_total_loss_step": critical["decision_id"] if critical else "",
        "first_total_loss_turn_after": critical["turn_after"] if critical else None,
        "visible_new_city": new_city_seen,
    }
    evidence = {**result, "first_total_loss": critical, "famine_steps": famine,
                "landing_events": landing_events, "population_events": population,
                "settler_restored_steps": restored,
                "post_total_loss_actions": [{"decision_id": s["decision_id"], "action": action(s)} for s in tail]}
    return result, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "runs" / RUN_ID)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/failure_diagnosis")
    args = parser.parse_args()
    with (ROOT / "reports/development/episode_results.csv").open() as f:
        cohort = [r for r in csv.DictReader(f) if r["task_type"] == "development_transport"]
    if len(cohort) != 100:
        raise ValueError("Expected the frozen 100-scene transport cohort")
    rows, details = [], []
    for r in cohort:
        row, detail = examine(r, args.run_dir / "episodes" / r["episode_id"] / "attempt0")
        rows.append(row)
        details.append(detail)
    flags = [k for k, v in rows[0].items() if isinstance(v, bool)]
    groups = {}
    for outcome in ("native_success", "native_failure", "output_failure"):
        subset = [r for r in rows if r["stop_reason"] == outcome]
        lost = [r for r in subset if r["all_settlers_lost_before_city"]]
        groups[outcome] = {
            "n": len(subset), **{k: sum(r[k] for r in subset) for k in flags},
            "after_total_loss": {"n": len(lost),
                **{f"{k}_median": median(r[k] for r in lost) if lost else None for k in
                   ("post_total_loss_env_steps", "post_total_loss_api_calls", "post_total_loss_end_turns")},
                "produce_settlers_episodes": sum(r["post_total_loss_produce_settlers"] > 0 for r in lost),
                "buy_production_episodes": sum(r["post_total_loss_buy_production"] > 0 for r in lost)}}
    output = {
        "run_id": RUN_ID, "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_type": "development_transport", "episodes": len(rows),
        "definitions": {
            "famine_loss": "At least one native Famine feared ... lost notification.",
            "actual_landing": "Own Settlers exists before/after a disembark action, and transported changes true to false.",
            "landed_settler_lost_before_city": "A landed Settlers disappears in a later observed transition before any visible new own city; does not count consumption in city founding.",
            "landed_settler_lost_at_next_end_turn": "Above loss occurs at the first END_TURN following its landing.",
            "all_settlers_lost_before_city": "Observed own Settlers count changes positive to zero before any visible new own city.",
            "settler_restored_after_total_loss": "After the first total loss, a subsequent observed state contains an own Settlers.",
            "population_block": "Native notification contains can't build Settlers yet.",
            "population_block_with_next_decision": "At least one such warning is followed by another recorded decision, including a possible no-submission decision.",
            "post_total_loss": "Decisions strictly after the transition first losing all Settlers; loss action is excluded; API count includes correction.",
        },
        "groups": groups, "evidence": details,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "common_failure_patterns.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    with (args.output_dir / "common_failure_patterns.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(groups, ensure_ascii=False, indent=2))
    print("Native failure loss steps:")
    for r in rows:
        if r["stop_reason"] == "native_failure":
            print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
