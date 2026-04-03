"""Flask server for live monitoring of the simulation engine."""

from __future__ import annotations

from flask import Flask, jsonify, render_template

from engine import start_engine_thread

app = Flask(__name__)
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = start_engine_thread()
    return _engine


@app.route("/")
def index():
    # Ensure engine starts when UI is opened, not merely when module imports.
    get_engine()
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    engine = get_engine()
    return jsonify(engine.dispatcher.snapshot())


if __name__ == "__main__":
    get_engine()
    app.run(host="0.0.0.0", port=5000, debug=False)
