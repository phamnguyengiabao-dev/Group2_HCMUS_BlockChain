"""
layout.py — Root layout definition for the Dash app.

Structure:
    Header
    ├── Log selector + Refresh button
    ├── Summary stat cards (dynamic)
    └── Tabs
        ├── Tab 1: Overview        (stat cards + event distribution bar)
        ├── Tab 2: Chain View      (chain graph + round progression)
        ├── Tab 3: Validator Net   (Cytoscape network + node info panel)
        ├── Tab 4: Event Timeline  (scatter timeline + event table)
        └── Tab 5: Vote Matrix     (height/round selector + heatmap)
"""

from __future__ import annotations

from dash import dcc, html, dash_table
import dash_cytoscape as cyto

from dashboard.data_loader import get_available_logs
from dashboard.components  import (
    CYTOSCAPE_STYLESHEET,
    empty_state,
    node_legend,
    event_legend,
)


def build_layout() -> html.Div:
    logs = get_available_logs()
    log_options = [{"label": l["label"], "value": l["value"]} for l in logs]
    default_value = log_options[0]["value"] if log_options else None

    return html.Div(
        id="app-root",
        children=[

            # ── hidden store for parsed events ──────────────────────────────
            dcc.Store(id="store-events"),          # list of event dicts
            dcc.Store(id="store-scenario-cfg"),    # scenario config dict
            dcc.Store(id="store-summary"),         # summary stats dict

            # ── header ──────────────────────────────────────────────────────
            html.Header(
                className="app-header",
                children=[
                    html.Div(
                        className="header-left",
                        children=[
                            html.Span("⛓", className="header-icon"),
                            html.H1("Blockchain Visualizer", className="header-title"),
                            html.Span("lab01-testnet", className="header-chain-badge"),
                        ],
                    ),
                    html.Div(
                        className="header-right",
                        children=[
                            html.Label("Log file:", className="selector-label"),
                            dcc.Dropdown(
                                id="log-selector",
                                options=log_options,
                                value=default_value,
                                placeholder="Select a .jsonl log file…",
                                clearable=False,
                                className="log-dropdown",
                            ),
                            html.Button(
                                "↻ Refresh",
                                id="btn-refresh",
                                className="btn-refresh",
                                n_clicks=0,
                            ),
                        ],
                    ),
                ],
            ),

            # ── stat cards row ───────────────────────────────────────────────
            html.Div(id="stat-cards-row", className="stat-cards-row"),

            # ── main tabs ────────────────────────────────────────────────────
            dcc.Tabs(
                id="main-tabs",
                value="tab-overview",
                className="main-tabs",
                children=[

                    # ── Tab 1: Overview ─────────────────────────────────────
                    dcc.Tab(
                        label="📊 Overview",
                        value="tab-overview",
                        className="tab",
                        selected_className="tab-selected",
                        children=[
                            html.Div(
                                className="tab-content",
                                children=[
                                    html.Div(
                                        className="two-col",
                                        children=[
                                            html.Div(
                                                className="panel",
                                                children=[
                                                    html.H3("Scenario Config"),
                                                    html.Div(id="scenario-config-panel"),
                                                ],
                                            ),
                                            html.Div(
                                                className="panel",
                                                children=[
                                                    html.H3("Event Distribution"),
                                                    dcc.Graph(id="chart-event-bar",
                                                              config={"displayModeBar": False}),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # ── Tab 2: Chain View ────────────────────────────────────
                    dcc.Tab(
                        label="🔗 Chain View",
                        value="tab-chain",
                        className="tab",
                        selected_className="tab-selected",
                        children=[
                            html.Div(
                                className="tab-content",
                                children=[
                                    html.Div(
                                        className="panel",
                                        children=[
                                            html.H3("Finalised Chain"),
                                            dcc.Graph(id="chart-chain",
                                                      config={"displayModeBar": False},
                                                      style={"height": "220px"}),
                                        ],
                                    ),
                                    html.Div(
                                        className="panel",
                                        children=[
                                            html.H3("Rounds per Height"),
                                            dcc.Graph(id="chart-rounds",
                                                      config={"displayModeBar": False},
                                                      style={"height": "280px"}),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # ── Tab 3: Validator Network ─────────────────────────────
                    dcc.Tab(
                        label="🌐 Validator Network",
                        value="tab-network",
                        className="tab",
                        selected_className="tab-selected",
                        children=[
                            html.Div(
                                className="tab-content",
                                children=[
                                    node_legend(),
                                    html.Div(
                                        className="two-col",
                                        style={"gridTemplateColumns": "3fr 1fr"},
                                        children=[
                                            cyto.Cytoscape(
                                                id="cyto-network",
                                                elements=[],
                                                stylesheet=CYTOSCAPE_STYLESHEET,
                                                layout={
                                                    "name":    "cose",
                                                    "animate": True,
                                                    "padding": 30,
                                                },
                                                style={
                                                    "height":     "520px",
                                                    "background": "#1E1E2E",
                                                    "borderRadius": "8px",
                                                    "border":     "1px solid #45475A",
                                                },
                                                userZoomingEnabled=True,
                                                userPanningEnabled=True,
                                                boxSelectionEnabled=False,
                                            ),
                                            html.Div(
                                                id="node-info-panel",
                                                className="panel",
                                                style={"minHeight": "200px"},
                                                children=[
                                                    html.H3("Node Info"),
                                                    empty_state("Click a node to inspect."),
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="layout-controls",
                                        children=[
                                            html.Span("Layout: ", style={"color": "#888"}),
                                            *[
                                                html.Button(
                                                    name,
                                                    id=f"btn-layout-{name.lower()}",
                                                    className="btn-layout",
                                                    n_clicks=0,
                                                )
                                                for name in ["Cose", "Circle", "Grid", "Breadthfirst"]
                                            ],
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # ── Tab 4: Event Timeline ────────────────────────────────
                    dcc.Tab(
                        label="📈 Event Timeline",
                        value="tab-timeline",
                        className="tab",
                        selected_className="tab-selected",
                        children=[
                            html.Div(
                                className="tab-content",
                                children=[
                                    event_legend(),
                                    html.Div(
                                        className="panel",
                                        children=[
                                            html.H3("Timeline"),
                                            html.Div(
                                                className="filter-row",
                                                children=[
                                                    html.Label("Filter nodes:"),
                                                    dcc.Dropdown(
                                                        id="timeline-node-filter",
                                                        multi=True,
                                                        placeholder="All nodes…",
                                                        className="filter-dropdown",
                                                    ),
                                                    html.Label("Filter event types:"),
                                                    dcc.Dropdown(
                                                        id="timeline-event-filter",
                                                        multi=True,
                                                        placeholder="All event types…",
                                                        className="filter-dropdown",
                                                    ),
                                                ],
                                            ),
                                            dcc.Graph(
                                                id="chart-timeline",
                                                config={"displayModeBar": True},
                                                style={"height": "400px"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="panel",
                                        children=[
                                            html.H3("Event Log Table"),
                                            dash_table.DataTable(
                                                id="event-table",
                                                columns=[
                                                    {"name": "#",           "id": "event_no"},
                                                    {"name": "Time",        "id": "logical_time"},
                                                    {"name": "Node",        "id": "node_id"},
                                                    {"name": "Event",       "id": "event_type"},
                                                    {"name": "Height",      "id": "height"},
                                                    {"name": "Round",       "id": "round"},
                                                    {"name": "Details",     "id": "details"},
                                                ],
                                                data=[],
                                                page_size=15,
                                                sort_action="native",
                                                filter_action="native",
                                                style_table={"overflowX": "auto"},
                                                style_header={
                                                    "backgroundColor": "#313244",
                                                    "color":           "#CDD6F4",
                                                    "fontWeight":      "700",
                                                    "border":          "1px solid #45475A",
                                                },
                                                style_cell={
                                                    "backgroundColor": "#1E1E2E",
                                                    "color":           "#CDD6F4",
                                                    "border":          "1px solid #313244",
                                                    "fontSize":        "12px",
                                                    "padding":         "6px 10px",
                                                    "maxWidth":        "300px",
                                                    "overflow":        "hidden",
                                                    "textOverflow":    "ellipsis",
                                                },
                                                style_data_conditional=[
                                                    {
                                                        "if": {"filter_query": '{event_type} = "FINALIZE"'},
                                                        "backgroundColor": "rgba(0,170,68,0.13)",
                                                        "color":           "#A6E3A1",
                                                    },
                                                    {
                                                        "if": {"filter_query": '{event_type} = "EQUIVOCATION"'},
                                                        "backgroundColor": "rgba(204,0,0,0.13)",
                                                        "color":           "#F38BA8",
                                                    },
                                                    {
                                                        "if": {"filter_query": '{event_type} = "CRASH"'},
                                                        "backgroundColor": "rgba(139,0,0,0.13)",
                                                        "color":           "#F38BA8",
                                                    },
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # ── Tab 5: Vote Matrix ────────────────────────────────────
                    dcc.Tab(
                        label="🗳 Vote Matrix",
                        value="tab-votes",
                        className="tab",
                        selected_className="tab-selected",
                        children=[
                            html.Div(
                                className="tab-content",
                                children=[
                                    html.Div(
                                        className="filter-row",
                                        children=[
                                            html.Label("Height:"),
                                            dcc.Input(
                                                id="vote-height-input",
                                                type="number",
                                                min=0, step=1, value=1,
                                                debounce=True,
                                                className="number-input",
                                            ),
                                            html.Label("Round:"),
                                            dcc.Input(
                                                id="vote-round-input",
                                                type="number",
                                                min=0, step=1, value=0,
                                                debounce=True,
                                                className="number-input",
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="panel",
                                        children=[
                                            html.H3(id="vote-matrix-title",
                                                    children="Vote Matrix — Height 1, Round 0"),
                                            dcc.Graph(
                                                id="chart-vote-heatmap",
                                                config={"displayModeBar": False},
                                                style={"height": "280px"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                ],
            ),

            # ── footer ───────────────────────────────────────────────────────
            html.Footer(
                className="app-footer",
                children=[
                    html.Span("Blockchain Visualizer · lab01-testnet ·"),
                    html.Span(id="footer-event-count", children=""),
                ],
            ),

        ],
    )
