import streamlit as st
import pandas as pd
import os
from scheduler.loader import load_scenario, minutes_to_hhmm
from scheduler.engine import run_simulation

st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="🚌",
    layout="wide"
)

SCENARIO_FILES = {
    "Scenario 1 — Even Spacing":          "scenarios/scenario_01.yaml",
    "Scenario 2 — Bunched Start":         "scenarios/scenario_02.yaml",
    "Scenario 3 — Asymmetric Load":       "scenarios/scenario_03.yaml",
    "Scenario 4 — Operator Heavy":        "scenarios/scenario_04.yaml",
    "Scenario 5 — Worst Case Convergence":"scenarios/scenario_05.yaml",
}

st.title("🚌 Bus Charging Scheduler")
st.caption("Check the schedule with us.")

st.divider()

selected_name = st.selectbox(
    "Select a scenario",
    options=list(SCENARIO_FILES.keys())
)

scenario_path = SCENARIO_FILES[selected_name]

try:
    scenario = load_scenario(scenario_path)
    result = run_simulation(scenario)
except Exception as e:
    st.error(f"Failed to load or run scenario: {e}")
    st.stop()

st.divider()


st.header("📋 Scenario Input")
col1, col2, col3 = st.columns(3)
 
with col1:
    st.subheader("Weights")
    st.metric("Individual", scenario.weights.individual)
    st.metric("Operator",   scenario.weights.operator)
    st.metric("Overall",    scenario.weights.overall)
 
with col2:
    st.subheader("Physics")
    st.metric("Battery Range",  f"{scenario.physics.battery_range_km} km")
    st.metric("Charge Time",    f"{scenario.physics.charge_time_min} min")
    st.metric("Speed",          f"{scenario.route.speed_kmh} km/h")
 
with col3:
    st.subheader("Route")
    route_str = " → ".join(scenario.route.stops)
    st.write(route_str)
    st.subheader("Stations")
    for s in scenario.stations:
        st.write(f"**{s.id}** — {s.chargers} charger(s)")
 
st.subheader("Bus Departure Schedule")


# Build input table
input_rows = []
for bus in scenario.buses:
    input_rows.append({
        "Bus ID":    bus.id,
        "Operator":  bus.operator.upper(),
        "Direction": f"{bus.origin} → {bus.destination}",
        "Departure": minutes_to_hhmm(bus.departure_min),
    })
 
input_df = pd.DataFrame(input_rows)
st.dataframe(input_df, use_container_width=True, hide_index=True)
 
st.divider()

st.header("🕐 Per-Bus Timetable")
st.caption("For each bus: which stations it charged at, wait times, and final arrival.")
 
bus_rows = []
for timeline in sorted(result.bus_timelines, key=lambda t: t.departure_min):
    # Build charging stops string e.g. "A (wait 0 min) → C (wait 12 min)"
    if timeline.charge_events:
        stops_parts = []
        for ce in timeline.charge_events:
            wait_str = f"wait {int(ce.wait_min)} min" if ce.wait_min > 0 else "no wait"
            stops_parts.append(f"{ce.station_id} ({wait_str})")
        stops_str = " → ".join(stops_parts)
    else:
        stops_str = "—"
 
    # Find bus direction
    bus = next(b for b in scenario.buses if b.id == timeline.bus_id)
 
    bus_rows.append({
        "Bus ID":        timeline.bus_id,
        "Operator":      timeline.operator.upper(),
        "Direction":     f"{bus.origin} → {bus.destination}",
        "Departure":     minutes_to_hhmm(timeline.departure_min),
        "Charging Stops":stops_str,
        "Total Wait":    f"{int(timeline.total_wait_min)} min",
        "Trip Duration": f"{int(timeline.total_trip_min)} min",
        "Arrival":       minutes_to_hhmm(timeline.arrival_min),
    })
 
bus_df = pd.DataFrame(bus_rows)
st.dataframe(bus_df, use_container_width=True, hide_index=True)
 
st.divider()
 
# ---------------------------------------------------------------------------
# SECTION 3 — PER-STATION VIEW
# ---------------------------------------------------------------------------
 
st.header("⚡ Per-Station Charging Order")
st.caption("For each station: the order in which buses charged, with timestamps.")
 
# Show each station in route order (A, B, C, D)
station_cols = st.columns(len(result.station_logs))
 
for col, station_log in zip(
    station_cols,
    sorted(result.station_logs,
           key=lambda sl: [s.id for s in scenario.stations].index(sl.station_id))
):
    with col:
        st.subheader(f"Station {station_log.station_id}")
 
        if not station_log.events:
            st.write("No buses charged here.")
            continue
 
        # Sort by charge start time
        sorted_events = sorted(
            station_log.events,
            key=lambda e: e.charge_event.charge_start_min
        )
 
        station_rows = []
        for i, se in enumerate(sorted_events, 1):
            ce = se.charge_event
            station_rows.append({
                "#":        i,
                "Bus":      se.bus_id,
                "Operator": se.operator.upper(),
                "Arrived":  minutes_to_hhmm(ce.arrive_min),
                "Waited":   f"{int(ce.wait_min)} min",
                "Started":  minutes_to_hhmm(ce.charge_start_min),
                "Departed": minutes_to_hhmm(ce.depart_min),
            })
 
        station_df = pd.DataFrame(station_rows)
        st.dataframe(station_df, use_container_width=True, hide_index=True)
 
st.divider()
 
# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
 
st.caption(
    "Weights are set per scenario in the YAML files. "
    "To change a weight: edit the `weights` section in the relevant scenario file."
)