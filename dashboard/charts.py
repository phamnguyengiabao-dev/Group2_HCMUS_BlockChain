"""
charts.py — Plotly figure builders for the dashboard.

All functions return a plotly.graph_objects.Figure.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from dashboard.data_loader import EVENT_COLOURS


# ── shared dark theme ─────────────────────────────────────────────────────────

_LAYOUT_BASE = dict(
    paper_bgcolor="#1E1E2E",
    plot_bgcolor="#1E1E2E",
    font=dict(color="#CDD6F4", size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(
        bgcolor="#313244",
        bordercolor="#45475A",
        borderwidth=1,
    ),
)


def _dark(**kwargs) -> dict:
    base = dict(_LAYOUT_BASE)
    base.update(kwargs)
    return base


# ── event timeline ────────────────────────────────────────────────────────────

def event_timeline_figure(timeline_rows: list[dict[str, Any]]) -> go.Figure:
    """
    Scatter plot: x = logical_time, y = node_id, colour = event_type.
    Each dot is one event; hover shows full details.
    """
    if not timeline_rows:
        return _empty_figure("No events to display")

    df = pd.DataFrame(timeline_rows)

    fig = go.Figure()

    for et, group in df.groupby("event_type"):
        colour = EVENT_COLOURS.get(et, "#AAAAAA")
        fig.add_trace(go.Scatter(
            x=group["logical_time"],
            y=group["node_id"],
            mode="markers",
            name=et,
            marker=dict(color=colour, size=10, symbol="circle",
                        line=dict(color="rgba(255,255,255,0.27)", width=1)),
            customdata=group[["event_no", "height", "round", "details"]].values,
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Event #%{customdata[0]}<br>"
                "Time: %{x}<br>"
                "Height: %{customdata[1]}  Round: %{customdata[2]}<br>"
                "<extra>%{customdata[3]}</extra>"
            ),
        ))

    fig.update_layout(
        **_dark(
            title="Event Timeline",
            xaxis=dict(
                title="Logical Time",
                gridcolor="#313244",
                zeroline=False,
            ),
            yaxis=dict(
                title="Node",
                gridcolor="#313244",
                categoryorder="array",
                categoryarray=sorted(df["node_id"].unique()),
            ),
            hovermode="closest",
        )
    )
    return fig


# ── event type distribution ───────────────────────────────────────────────────

def event_type_bar(timeline_rows: list[dict[str, Any]]) -> go.Figure:
    """Horizontal bar chart: count per event type."""
    if not timeline_rows:
        return _empty_figure("No events")

    df = pd.DataFrame(timeline_rows)
    counts = df["event_type"].value_counts().reset_index()
    counts.columns = ["event_type", "count"]
    counts["colour"] = counts["event_type"].map(
        lambda e: EVENT_COLOURS.get(e, "#AAAAAA")
    )
    counts = counts.sort_values("count", ascending=True)

    fig = go.Figure(go.Bar(
        x=counts["count"],
        y=counts["event_type"],
        orientation="h",
        marker=dict(color=counts["colour"]),
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))

    fig.update_layout(
        **_dark(
            title="Event Distribution",
            xaxis=dict(title="Count", gridcolor="#313244"),
            yaxis=dict(gridcolor="#313244"),
        )
    )
    return fig


# ── chain block view ─────────────────────────────────────────────────────────

def chain_figure(chain_data: list[dict[str, Any]]) -> go.Figure:
    """
    Visualise the finalised chain as a connected scatter on height axis.
    Each block node shows height, round, and (truncated) block_hash.
    """
    if not chain_data:
        return _empty_figure("No finalised blocks in this log")

    heights = [b["height"] for b in chain_data]
    rounds  = [b["round"]  for b in chain_data]
    labels  = [
        f"H{b['height']} R{b['round']}<br>{(b.get('block_hash') or '')[:12]}…"
        for b in chain_data
    ]
    hover  = [
        (
            f"Height: {b['height']}<br>"
            f"Round: {b['round']}<br>"
            f"Node: {b['node_id']}<br>"
            f"Hash: {b.get('block_hash') or 'n/a'}<br>"
            f"Txns: {b.get('tx_count', 0)}"
        )
        for b in chain_data
    ]

    fig = go.Figure()

    # Connecting line
    fig.add_trace(go.Scatter(
        x=heights, y=[0] * len(heights),
        mode="lines",
        line=dict(color="#45475A", width=2, dash="dot"),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Block nodes
    fig.add_trace(go.Scatter(
        x=heights, y=[0] * len(heights),
        mode="markers+text",
        marker=dict(
            size=32,
            color="#00AA44",
            symbol="square",
            line=dict(color="#A6E3A1", width=2),
        ),
        text=[f"H{h}" for h in heights],
        textfont=dict(color="#fff", size=11),
        textposition="middle center",
        hovertext=hover,
        hoverinfo="text",
        name="Finalised Block",
    ))

    # Genesis block (height 0 placeholder)
    fig.add_trace(go.Scatter(
        x=[0], y=[0],
        mode="markers+text",
        marker=dict(size=32, color="#6C8EBF", symbol="square",
                    line=dict(color="#89B4FA", width=2)),
        text=["Genesis"],
        textfont=dict(color="#fff", size=9),
        textposition="middle center",
        hoverinfo="skip",
        name="Genesis",
    ))

    fig.update_layout(
        **_dark(
            title="Finalised Chain",
            xaxis=dict(
                title="Block Height",
                tickvals=list(range(0, max(heights) + 2)),
                gridcolor="#313244",
                zeroline=False,
            ),
            yaxis=dict(visible=False),
            showlegend=True,
        )
    )
    return fig


# ── vote heatmap ──────────────────────────────────────────────────────────────

def vote_heatmap(vote_data: dict[str, Any]) -> go.Figure:
    """
    Heatmap grid: rows = validators, columns = [PREVOTE, PRECOMMIT].
    Cell colours: green = voted, red = NIL, grey = no data.
    """
    validators = vote_data.get("validators", [])
    if not validators:
        return _empty_figure("No validators found")

    prevotes   = vote_data.get("prevotes",   {})
    precommits = vote_data.get("precommits", {})

    def encode(v: str | None) -> tuple[int, str]:
        if v is None:
            return 0, "—"
        if v == "NIL":
            return 1, "NIL"
        return 2, v[:10] + "…"

    pv_z, pv_text   = zip(*[encode(prevotes.get(v))   for v in validators])
    pc_z, pc_text   = zip(*[encode(precommits.get(v)) for v in validators])

    z    = [list(pv_z),   list(pc_z)]
    text = [list(pv_text), list(pc_text)]
    y    = ["PREVOTE", "PRECOMMIT"]
    x    = validators

    colour_scale = [
        [0.0,  "#313244"],   # 0 = no data (grey)
        [0.33, "#313244"],
        [0.34, "#CC0000"],   # 1 = NIL (red)
        [0.66, "#CC0000"],
        [0.67, "#00AA44"],   # 2 = voted (green)
        [1.0,  "#00AA44"],
    ]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[v.replace("validator_", "V") for v in x],
        y=y,
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=9),
        colorscale=colour_scale,
        showscale=False,
        hovertemplate="Validator: %{x}<br>Phase: %{y}<br>Hash: %{text}<extra></extra>",
    ))

    fig.update_layout(
        **_dark(
            title="Vote Matrix",
            xaxis=dict(gridcolor="#313244", side="bottom"),
            yaxis=dict(gridcolor="#313244"),
        )
    )
    return fig


# ── round progression ─────────────────────────────────────────────────────────

def round_progression_figure(timeline_rows: list[dict[str, Any]]) -> go.Figure:
    """
    Line chart: rounds used per height (how many rounds did consensus take?).
    Uses FINALIZE events to get the final round per height.
    """
    if not timeline_rows:
        return _empty_figure("No events")

    df = pd.DataFrame(timeline_rows)
    fin = df[df["event_type"] == "FINALIZE"]
    if fin.empty:
        return _empty_figure("No FINALIZE events — consensus not reached in this log")

    best = fin.groupby("height")["round"].max().reset_index()

    fig = go.Figure(go.Scatter(
        x=best["height"],
        y=best["round"],
        mode="lines+markers",
        marker=dict(size=10, color="#F5A623"),
        line=dict(color="#F5A623", width=2),
        hovertemplate="Height %{x} → Round %{y}<extra></extra>",
        name="Rounds to finalise",
    ))

    fig.update_layout(
        **_dark(
            title="Rounds per Height",
            xaxis=dict(title="Block Height", gridcolor="#313244", dtick=1),
            yaxis=dict(title="Final Round",  gridcolor="#313244", dtick=1),
        )
    )
    return fig


# ── helpers ───────────────────────────────────────────────────────────────────

def _empty_figure(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=msg,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="#888"),
    )
    fig.update_layout(**_dark())
    return fig
