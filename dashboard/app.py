"""
app.py — Entry point for the Blockchain Visualizer Dash application.

Run:
    python -m dashboard.app
    # or
    python dashboard/app.py
"""

from __future__ import annotations

import dash
import dash_cytoscape as cyto

from dashboard.layout    import build_layout
from dashboard.callbacks import register_callbacks


# Register Cytoscape with Dash (must be called before app instantiation)
cyto.load_extra_layouts()

app = dash.Dash(
    __name__,
    title="Blockchain Visualizer",
    # assets_folder is automatically resolved to dashboard/assets/
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ],
)

app.layout = build_layout()
register_callbacks(app)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Blockchain Visualizer")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8050,   help="Port to bind (default: 8050)")
    parser.add_argument("--debug", action="store_true",     help="Enable Dash debug mode")
    args = parser.parse_args()

    print(f"\n  ⛓  Blockchain Visualizer")
    print(f"  →  http://{args.host}:{args.port}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)
