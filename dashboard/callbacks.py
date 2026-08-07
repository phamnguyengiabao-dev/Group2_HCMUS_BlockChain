"""
callbacks.py — All Dash callbacks for the blockchain visualizer.

Callback groups:
    1. load_log_data        — Load + parse JSONL when log-selector changes
    2. update_stat_cards    — Render KPI cards from summary store
    3. update_overview      — Overview tab: scenario config + event bar
    4. update_chain_tab     — Chain tab: chain figure + rounds figure
    5. update_network_tab   — Network tab: Cytoscape elements
    6. update_node_info     — Network tab: node info panel on click
    7. update_layout_btn    — Network tab: layout switch buttons
    8. update_timeline_tab  — Timeline tab: filters, scatter, table
    9. update_vote_tab      — Vote tab: heatmap + title
    10. update_footer       — Footer event count
"""

from __future__ import annotations

import json
from typing import Any

from dash import Input, Output, State, callback, ctx, no_update
from dash import html
import dash_cytoscape as cyto

from dashboard.data_loader import (
    load_log,
    load_scenario_configs,
    build_cytoscape_elements,
    build_event_timeline,
    build_chain_data,
    build_vote_matrix,
    get_validator_ids,
    summarise_log,
)
from dashboard.charts import (
    event_timeline_figure,
    event_type_bar,
    chain_figure,
    vote_heatmap,
    round_progression_figure,
    _empty_figure,
)
from dashboard.components import stat_card, empty_state, event_badge, CYTOSCAPE_STYLESHEET


# ── 1. Load log data ──────────────────────────────────────────────────────────

def register_callbacks(app):
    """Register all callbacks on the Dash app instance."""

    @app.callback(
        Output("store-events",      "data"),
        Output("store-scenario-cfg","data"),
        Output("store-summary",     "data"),
        Input("log-selector",       "value"),
        Input("btn-refresh",        "n_clicks"),
        prevent_initial_call=False,
    )
    def load_log_data(log_path: str | None, _n: int):
        if not log_path:
            return [], {}, {}
        try:
            events = load_log(log_path)
        except Exception as e:
            return [], {}, {"error": str(e)}

        summary = summarise_log(events)

        # Find matching scenario config by scenario_id
        scenario_id = summary.get("scenario_id", "")
        all_scenarios = load_scenario_configs()
        scenario_cfg = all_scenarios.get(scenario_id, {})

        return events, scenario_cfg, summary


    # ── 2. Stat cards ─────────────────────────────────────────────────────────

    @app.callback(
        Output("stat-cards-row", "children"),
        Input("store-summary",   "data"),
    )
    def update_stat_cards(summary: dict | None):
        if not summary:
            return []
        cards = [
            stat_card("Scenario",      summary.get("scenario_id", "—"),      "#6C8EBF"),
            stat_card("Validators",    summary.get("num_validators", "—"),    "#4A90D9"),
            stat_card("Total Events",  summary.get("total_events", 0),        "#82B366"),
            stat_card("Max Height",    summary.get("max_height", 0),          "#00AA44"),
            stat_card("Finalised",     summary.get("finalized_count", 0),     "#00AA44"),
            stat_card("Equivocations", summary.get("equivocation_count", 0),  "#CC0000"),
            stat_card("Crashes",       summary.get("crash_count", 0),         "#8B0000"),
            stat_card("Timeouts",      summary.get("timeout_count", 0),       "#708090"),
        ]
        return cards


    # ── 3. Overview tab ───────────────────────────────────────────────────────

    @app.callback(
        Output("scenario-config-panel", "children"),
        Output("chart-event-bar",       "figure"),
        Input("store-events",           "data"),
        Input("store-scenario-cfg",     "data"),
    )
    def update_overview(events: list, scenario_cfg: dict):
        if not events:
            return empty_state(), _empty_figure("No log loaded")

        # Scenario config table
        if scenario_cfg:
            rows = []
            for k, v in scenario_cfg.items():
                rows.append(html.Tr([
                    html.Td(k, style={"fontWeight": "600", "paddingRight": "12px",
                                      "color": "#89B4FA"}),
                    html.Td(str(v)),
                ]))
            config_panel = html.Table(rows, style={"borderCollapse": "collapse",
                                                    "width": "100%"})
        else:
            config_panel = html.P("No matching scenario config found.",
                                  style={"color": "#888"})

        timeline = build_event_timeline(events)
        bar_fig  = event_type_bar(timeline)
        return config_panel, bar_fig


    # ── 4. Chain tab ──────────────────────────────────────────────────────────

    @app.callback(
        Output("chart-chain",  "figure"),
        Output("chart-rounds", "figure"),
        Input("store-events",  "data"),
    )
    def update_chain_tab(events: list):
        if not events:
            return _empty_figure("No log loaded"), _empty_figure("No log loaded")
        chain_data = build_chain_data(events)
        timeline   = build_event_timeline(events)
        return chain_figure(chain_data), round_progression_figure(timeline)


    # ── 5. Validator network ──────────────────────────────────────────────────

    @app.callback(
        Output("cyto-network",      "elements"),
        Input("store-events",       "data"),
        Input("store-scenario-cfg", "data"),
    )
    def update_network_tab(events: list, scenario_cfg: dict):
        if not events:
            return []
        return build_cytoscape_elements(events, scenario_cfg or {})


    # ── 6. Node info panel ────────────────────────────────────────────────────

    @app.callback(
        Output("node-info-panel", "children"),
        Input("cyto-network",     "tapNodeData"),
        State("store-events",     "data"),
        State("store-summary",    "data"),
    )
    def update_node_info(node_data: dict | None, events: list, summary: dict):
        if not node_data:
            return [html.H3("Node Info"), empty_state("Click a node to inspect.")]

        nid     = node_data.get("id", "")
        status  = node_data.get("status", "normal")
        ntype   = node_data.get("type", "")

        # Count events for this node
        node_events = [e for e in (events or []) if e.get("node_id") == nid]
        by_type: dict[str, int] = {}
        for ev in node_events:
            et = ev.get("event_type", "")
            by_type[et] = by_type.get(et, 0) + 1

        rows = [
            html.Tr([html.Td("ID"),     html.Td(nid)]),
            html.Tr([html.Td("Type"),   html.Td(ntype)]),
            html.Tr([html.Td("Status"), html.Td(status)]),
            html.Tr([html.Td("Events"), html.Td(str(len(node_events)))]),
        ]
        breakdown = [
            html.Tr([
                html.Td(event_badge(et)),
                html.Td(str(cnt), style={"paddingLeft": "8px"}),
            ])
            for et, cnt in sorted(by_type.items(), key=lambda x: -x[1])
        ]

        return [
            html.H3("Node Info"),
            html.Table(rows, style={"borderCollapse": "collapse", "marginBottom": "12px"}),
            html.H4("Event breakdown", style={"color": "#89B4FA", "marginBottom": "6px"}),
            html.Table(breakdown, style={"borderCollapse": "collapse"}),
        ]


    # ── 7. Layout switch buttons ──────────────────────────────────────────────

    @app.callback(
        Output("cyto-network", "layout"),
        Input("btn-layout-cose",        "n_clicks"),
        Input("btn-layout-circle",      "n_clicks"),
        Input("btn-layout-grid",        "n_clicks"),
        Input("btn-layout-breadthfirst","n_clicks"),
        prevent_initial_call=True,
    )
    def switch_layout(_cose, _circle, _grid, _bf):
        triggered = ctx.triggered_id or "btn-layout-cose"
        name_map = {
            "btn-layout-cose":        "cose",
            "btn-layout-circle":      "circle",
            "btn-layout-grid":        "grid",
            "btn-layout-breadthfirst":"breadthfirst",
        }
        name = name_map.get(triggered, "cose")
        return {"name": name, "animate": True, "padding": 30}


    # ── 8. Timeline tab ───────────────────────────────────────────────────────

    @app.callback(
        Output("timeline-node-filter",  "options"),
        Output("timeline-event-filter", "options"),
        Input("store-events", "data"),
    )
    def populate_timeline_filters(events: list):
        if not events:
            return [], []
        nodes = sorted({e.get("node_id", "") for e in events})
        types = sorted({e.get("event_type", "") for e in events})
        return (
            [{"label": n, "value": n} for n in nodes],
            [{"label": t, "value": t} for t in types],
        )

    @app.callback(
        Output("chart-timeline", "figure"),
        Output("event-table",    "data"),
        Input("store-events",          "data"),
        Input("timeline-node-filter",  "value"),
        Input("timeline-event-filter", "value"),
    )
    def update_timeline_tab(events: list, node_filter: list, event_filter: list):
        if not events:
            return _empty_figure("No log loaded"), []

        filtered = events
        if node_filter:
            filtered = [e for e in filtered if e.get("node_id") in node_filter]
        if event_filter:
            filtered = [e for e in filtered if e.get("event_type") in event_filter]

        timeline = build_event_timeline(filtered)
        fig      = event_timeline_figure(timeline)

        table_data = [
            {
                "event_no":     e.get("event_no"),
                "logical_time": e.get("logical_time"),
                "node_id":      e.get("node_id"),
                "event_type":   e.get("event_type"),
                "height":       e.get("height"),
                "round":        e.get("round"),
                "details":      json.dumps(e.get("details", {}), ensure_ascii=False),
            }
            for e in filtered
        ]
        return fig, table_data


    # ── 9. Vote matrix tab ────────────────────────────────────────────────────

    @app.callback(
        Output("chart-vote-heatmap", "figure"),
        Output("vote-matrix-title",  "children"),
        Input("store-events",       "data"),
        Input("vote-height-input",  "value"),
        Input("vote-round-input",   "value"),
    )
    def update_vote_tab(events: list, height: int | None, round_: int | None):
        h = height  if height  is not None else 1
        r = round_  if round_  is not None else 0
        title = f"Vote Matrix — Height {h}, Round {r}"

        if not events:
            return _empty_figure("No log loaded"), title

        vote_data = build_vote_matrix(events, h, r)
        fig = vote_heatmap(vote_data)
        return fig, title


    # ── 10. Footer ────────────────────────────────────────────────────────────

    @app.callback(
        Output("footer-event-count", "children"),
        Input("store-summary", "data"),
    )
    def update_footer(summary: dict | None):
        if not summary:
            return " No log loaded"
        return f" {summary.get('total_events', 0)} events · spec {summary.get('spec_version', '—')}"
