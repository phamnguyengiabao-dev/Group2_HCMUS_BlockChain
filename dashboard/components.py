"""
components.py — Reusable UI building blocks for the dashboard.

Provides stat cards, colour-coded badges, empty-state placeholders,
and the Cytoscape stylesheet used across the app.
"""

from __future__ import annotations

from dash import html
import dash_cytoscape as cyto

from dashboard.data_loader import EVENT_COLOURS, NODE_COLOURS


# ── stat card ─────────────────────────────────────────────────────────────────

def stat_card(title: str, value: str | int, accent: str = "#4A90D9") -> html.Div:
    """A small KPI card with a coloured top border."""
    return html.Div(
        className="stat-card",
        style={"borderTop": f"4px solid {accent}"},
        children=[
            html.P(title, className="stat-label"),
            html.H3(str(value), className="stat-value"),
        ],
    )


# ── event badge ───────────────────────────────────────────────────────────────

def event_badge(event_type: str) -> html.Span:
    """Inline coloured pill for an event type."""
    colour = EVENT_COLOURS.get(event_type, "#AAAAAA")
    return html.Span(
        event_type,
        style={
            "background": colour,
            "color":      "#fff",
            "borderRadius": "4px",
            "padding":    "2px 8px",
            "fontSize":   "0.75rem",
            "fontWeight": "600",
            "whiteSpace": "nowrap",
        },
    )


# ── empty state ───────────────────────────────────────────────────────────────

def empty_state(message: str = "No log loaded — select a log file above.") -> html.Div:
    return html.Div(
        message,
        style={
            "textAlign":  "center",
            "color":      "#888",
            "padding":    "60px 20px",
            "fontSize":   "1rem",
            "fontStyle":  "italic",
        },
    )


# ── Cytoscape stylesheet ───────────────────────────────────────────────────────

CYTOSCAPE_STYLESHEET: list[dict] = [
    # ── base node ──
    {
        "selector": "node",
        "style": {
            "label":           "data(label)",
            "background-color":"data(colour)",
            "color":           "#fff",
            "text-valign":     "center",
            "text-halign":     "center",
            "font-size":       "11px",
            "font-weight":     "600",
            "width":           "48px",
            "height":          "48px",
            "border-width":    "2px",
            "border-color":    "rgba(255,255,255,0.27)",
            "text-outline-color":  "data(colour)",
            "text-outline-width":  "2px",
        },
    },
    # ── system node (larger) ──
    {
        "selector": "node[type = 'system']",
        "style": {
            "shape":  "diamond",
            "width":  "56px",
            "height": "56px",
        },
    },
    # ── selected node highlight ──
    {
        "selector": "node:selected",
        "style": {
            "border-width": "4px",
            "border-color": "#FFD700",
        },
    },
    # ── base edge ──
    {
        "selector": "edge",
        "style": {
            "width":              "1.5px",
            "line-color":         "#555",
            "opacity":            "0.45",
            "curve-style":        "bezier",
            "target-arrow-shape": "none",
        },
    },
    # ── system → validator init edge ──
    {
        "selector": "edge[label = 'init']",
        "style": {
            "line-style":         "dashed",
            "line-color":         "#7ED321",
            "opacity":            "0.6",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#7ED321",
        },
    },
    # ── selected edge ──
    {
        "selector": "edge:selected",
        "style": {
            "line-color": "#FFD700",
            "width":      "3px",
            "opacity":    "1",
        },
    },
]


# ── legend ────────────────────────────────────────────────────────────────────

def node_legend() -> html.Div:
    """Colour legend for validator node states."""
    items = [
        ("Normal validator", NODE_COLOURS["normal"]),
        ("Proposer",         NODE_COLOURS["proposer"]),
        ("Byzantine",        NODE_COLOURS["byzantine"]),
        ("Crashed",          NODE_COLOURS["crashed"]),
        ("System",           NODE_COLOURS["system"]),
    ]
    return html.Div(
        className="legend",
        children=[
            html.Span("Node types: ", style={"fontWeight": "600", "marginRight": "8px"}),
            *[
                html.Span(
                    label,
                    style={
                        "background":   colour,
                        "color":        "#fff",
                        "borderRadius": "4px",
                        "padding":      "2px 10px",
                        "marginRight":  "6px",
                        "fontSize":     "0.75rem",
                        "fontWeight":   "600",
                    },
                )
                for label, colour in items
            ],
        ],
    )


def event_legend() -> html.Div:
    """Colour legend for key event types."""
    key_events = [
        "PROPOSE", "PREVOTE", "PRECOMMIT",
        "FINALIZE", "EQUIVOCATION", "CRASH",
        "TIMEOUT", "DROP",
    ]
    return html.Div(
        className="legend",
        children=[
            html.Span("Events: ", style={"fontWeight": "600", "marginRight": "8px"}),
            *[event_badge(et) for et in key_events],
        ],
        style={"flexWrap": "wrap", "display": "flex", "alignItems": "center", "gap": "4px"},
    )
