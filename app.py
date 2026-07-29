"""Minimal Flask app standing in for 'the small provided repo' the CI/CD
pipeline builds, tests, lints, and deploys."""
from flask import Flask, jsonify

app = Flask(__name__)


def add(a: int, b: int) -> int:
    return a + b


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/")
def index():
    return jsonify(message="hello from staging" )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
