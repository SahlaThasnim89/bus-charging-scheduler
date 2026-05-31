import heapq
from typing import List, Dict, Tuple
from scheduler.models import (
    Scenario, Bus, Route, Station,
    ChargeEvent, BusTimeline, StationEvent, StationLog, ScheduleResult
)
from scheduler.rules import priority_score


# Find valid charging station combinations for a bus
def get_valid_station_plans(
    bus: Bus,
    route: Route,
    charging_station_ids: List[str],
    battery_range_km: float
) -> List[List[str]]:

    # Get stops in this bus's travel direction
    stops = route.stops
    origin_idx = stops.index(bus.origin)
    dest_idx = stops.index(bus.destination)
 
    # Ordered stops this bus passes through (excluding origin and destination)
    if origin_idx < dest_idx:
        ordered_stations = [
            s for s in charging_station_ids
            if stops.index(s) > origin_idx and stops.index(s) < dest_idx
        ]
    else:
        ordered_stations = [
            s for s in reversed(charging_station_ids)
            if stops.index(s) < origin_idx and stops.index(s) > dest_idx
        ]
 
    valid_plans = []

    # Try all subsets of stations (from 1 station up to all stations)
    # We use bitmask to generate all subsets
    n = len(ordered_stations)
    for mask in range(1, 2 ** n):
        plan = [
            ordered_stations[i]
            for i in range(n)
            if mask & (1 << i)
        ]
 
        # Check if this plan is valid — no leg exceeds battery range
        if is_valid_plan(bus, plan, route, battery_range_km):
            valid_plans.append(plan)
 
    return valid_plans



def is_valid_plan(
    bus: Bus,
    plan: List[str],
    route: Route,
    battery_range_km: float
) -> bool:
    stops = [bus.origin] + plan + [bus.destination]
    for i in range(len(stops) - 1):
        leg_distance = route.distance_between(stops[i], stops[i + 1])
        if leg_distance > battery_range_km:
            return False
    return True


def estimate_plan_wait(
    plan: List[str],
    current_time: float,
    station_busy_until: Dict[str, float]
) -> float:
    total_wait = 0.0
    for station_id in plan:
        busy_until = station_busy_until.get(station_id, current_time)
        if busy_until > current_time:
            total_wait += busy_until - current_time
    return total_wait


# MAIN ENGINE
def run_simulation(scenario: Scenario) -> ScheduleResult:
    route = scenario.route
    physics = scenario.physics
    weights = scenario.weights
    all_buses = scenario.buses
 
    charging_station_ids = [s.id for s in scenario.stations]

    station_free_slots: Dict[str, int] = {
        s.id: s.chargers for s in scenario.stations
    }

    station_queues: Dict[str, list] = {
        s.id: [] for s in scenario.stations
    }

    station_busy_until: Dict[str, float] = {
        s.id: 0.0 for s in scenario.stations
    }

    # Total delay accumulated by each bus (for scoring)
    delays: Dict[str, float] = {b.id: 0.0 for b in all_buses}
 
    # km traveled since last charge (or departure) for each bus
    km_since_last_charge: Dict[str, float] = {b.id: 0.0 for b in all_buses}
 
    # Output objects — one per bus, one per station
    bus_timelines: Dict[str, BusTimeline] = {
        b.id: BusTimeline(
            bus_id=b.id,
            operator=b.operator,
            direction=b.direction,
            departure_min=b.departure_min
        )
        for b in all_buses
    }

    station_logs: Dict[str, StationLog] = {
        s.id: StationLog(station_id=s.id)
        for s in scenario.stations
    }

    bus_plans: Dict[str, List[str]] = {}
 
    bus_next_stop_idx: Dict[str, int] = {b.id: 0 for b in all_buses}
 
    events = []
    counter = 0  # tie-breaker so heapq never compares Bus objects
 
    def push_event(time: float, event_type: str, bus_id: str, data=None):
        nonlocal counter
        heapq.heappush(events, (time, counter, event_type, bus_id, data))
        counter += 1
 
    for bus in all_buses:
        push_event(bus.departure_min, "depart", bus.id)
 
    bus_by_id: Dict[str, Bus] = {b.id: b for b in all_buses}
 
    while events:
        time, _, event_type, bus_id, data = heapq.heappop(events)
        bus = bus_by_id[bus_id]
 

        if event_type == "depart":
 
            valid_plans = get_valid_station_plans(
                bus, route, charging_station_ids, physics.battery_range_km
            )
 
            if not valid_plans:
                continue
 
            best_plan = min(
                valid_plans,
                key=lambda p: estimate_plan_wait(p, time, station_busy_until)
            )
 
            bus_plans[bus_id] = best_plan
            bus_next_stop_idx[bus_id] = 0
 
            first_station = best_plan[0]
            travel_time = route.travel_time_min(bus.origin, first_station)
            push_event(
                time + travel_time,
                "arrive_station",
                bus_id,
                {"station_id": first_station}
            )
 
            km_since_last_charge[bus_id] = route.distance_between(
                bus.origin, first_station
            )
 

        elif event_type == "arrive_station":
            station_id = data["station_id"]
            arrive_time = time
 
            if station_free_slots[station_id] > 0:
                station_free_slots[station_id] -= 1
                wait_time = 0.0
                charge_start = arrive_time
                charge_done = charge_start + physics.charge_time_min
 
                station_busy_until[station_id] = max(
                    station_busy_until[station_id], charge_done
                )
 
                charge_event = ChargeEvent(
                    station_id=station_id,
                    arrive_min=arrive_time,
                    wait_min=wait_time,
                    charge_start_min=charge_start,
                    depart_min=charge_done
                )
                bus_timelines[bus_id].charge_events.append(charge_event)
                station_logs[station_id].events.append(
                    StationEvent(
                        bus_id=bus_id,
                        operator=bus.operator,
                        charge_event=charge_event
                    )
                )
 
                push_event(charge_done, "charging_done", bus_id,
                           {"station_id": station_id})
 
            else:
                score = priority_score(
                    bus=bus,
                    all_buses=all_buses,
                    delays=delays,
                    km_since_last_charge=km_since_last_charge[bus_id],
                    battery_range_km=physics.battery_range_km,
                    weights=weights
                )
                heapq.heappush(
                    station_queues[station_id],
                    (-score, counter, bus_id, arrive_time)
                )

                counter += 1
 

        elif event_type == "charging_done":
            station_id = data["station_id"]
            depart_time = time
 
            km_since_last_charge[bus_id] = 0.0
 
            plan = bus_plans[bus_id]
            next_idx = bus_next_stop_idx[bus_id] + 1
            bus_next_stop_idx[bus_id] = next_idx
 
            if next_idx < len(plan):
                next_station = plan[next_idx]
                travel_time = route.travel_time_min(station_id, next_station)
 
                push_event(
                    depart_time + travel_time,
                    "arrive_station",
                    bus_id,
                    {"station_id": next_station}
                )
 
                km_since_last_charge[bus_id] = route.distance_between(
                    station_id, next_station
                )
 
            else:
                travel_time = route.travel_time_min(
                    station_id, bus.destination
                )
                push_event(
                    depart_time + travel_time,
                    "arrive_dest",
                    bus_id
                )
 
            station_free_slots[station_id] += 1
 
            if station_queues[station_id]:
                neg_score, _, next_bus_id, next_arrive_time = heapq.heappop(
                    station_queues[station_id]
                )
 
                next_bus = bus_by_id[next_bus_id]
                station_free_slots[station_id] -= 1
 
                wait_time = depart_time - next_arrive_time
                charge_start = depart_time
                charge_done = charge_start + physics.charge_time_min
 
                delays[next_bus_id] += wait_time
 
                station_busy_until[station_id] = max(
                    station_busy_until[station_id], charge_done
                )
 
                charge_event = ChargeEvent(
                    station_id=station_id,
                    arrive_min=next_arrive_time,
                    wait_min=wait_time,
                    charge_start_min=charge_start,
                    depart_min=charge_done
                )
                bus_timelines[next_bus_id].charge_events.append(charge_event)
                station_logs[station_id].events.append(
                    StationEvent(
                        bus_id=next_bus_id,
                        operator=next_bus.operator,
                        charge_event=charge_event
                    )
                )
 
                push_event(charge_done, "charging_done", next_bus_id,
                           {"station_id": station_id})
 

        elif event_type == "arrive_dest":
            bus_timelines[bus_id].arrival_min = time
 
    result = ScheduleResult(scenario_id=scenario.id)
    result.bus_timelines = list(bus_timelines.values())
    result.station_logs = list(station_logs.values())
 
    return result