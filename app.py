"""Flask server for live monitoring of the simulation engine."""

from __future__ import annotations

from flask import Flask, jsonify, render_template

from engine import start_engine_thread

app = Flask(__name__)
engine = start_engine_thread()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    return jsonify(engine.dispatcher.snapshot())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
