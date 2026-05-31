from typing import List
from scheduler.models import Bus


# RULE 1 — INDIVIDUAL
def individual_score(delay_so_far: float) -> float:
    return delay_so_far


# RULE 2 — OPERATOR
def operator_score(bus: Bus, all_buses: List[Bus], delays: dict) -> float:
    # Get all buses from the same operator
    fleet = [b for b in all_buses if b.operator == bus.operator]
 
    if not fleet:
        return 0.0
    # Average delay across the entire operator fleet
    total_delay = sum(delays.get(b.id, 0.0) for b in fleet)
    return total_delay / len(fleet)


# RULE 3 — OVERALL
def overall_score(km_since_last_charge: float,
                  battery_range_km: float) -> float:
    # How many km of range does this bus have left?
    range_remaining = battery_range_km - km_since_last_charge
    return battery_range_km - range_remaining


# COMBINED PRIORITY SCORE
def priority_score(bus: Bus,
                   all_buses: List[Bus],
                   delays: dict,
                   km_since_last_charge: float,
                   battery_range_km: float,
                   weights) -> float:
    score = (
        weights.individual * individual_score(
            delay_so_far=delays.get(bus.id, 0.0)
        )
        +
        weights.operator * operator_score(
            bus=bus,
            all_buses=all_buses,
            delays=delays
        )
        +
        weights.overall * overall_score(
            km_since_last_charge=km_since_last_charge,
            battery_range_km=battery_range_km
        )
    )
    return score
                  