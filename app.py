#!/usr/bin/env python3
"""
Easy Dune Admin
Panel version: 0.8.8-beta
RedBlink stack compatibility target: v1.3.16

Small launcher for the Flask/Socket.IO application. The 0.7.0+ refactor moves
configuration, helpers, and route registrations out of this file so future
admin tools can grow without turning app.py back into a monolith.
"""

import sys

from eda_core import app, socketio  # shared Flask and Socket.IO objects
import eda_routes  # noqa: F401 - importing registers routes and socket handlers


class CtrlCMessageStream:
    """
    Rewrite Werkzeug's hardcoded Ctrl+C banner wherever it is emitted.

    Werkzeug/Flask versions differ on whether that line goes through logging,
    Click, stdout, or stderr. A small stream wrapper is intentionally narrow:
    only the exact banner text is replaced, while normal startup addresses and
    request logs pass through untouched.
    """

    OLD_TEXT = "Press CTRL+C to quit"
    NEW_TEXT = "Press CTRL+C to quit (daemon continues to run detached when launched by Docker)."

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        if isinstance(text, str):
            text = text.replace(self.OLD_TEXT, self.NEW_TEXT)
        return self.stream.write(text)

    def flush(self):
        return self.stream.flush()

    def isatty(self):
        return self.stream.isatty()

    def fileno(self):
        return self.stream.fileno()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def install_ctrl_c_message_stream_patch():
    sys.stdout = CtrlCMessageStream(sys.stdout)
    sys.stderr = CtrlCMessageStream(sys.stderr)


def install_werkzeug_quit_message_patch():
    """
    Keep Werkzeug's useful startup banner, but clarify its Ctrl+C line.

    Docker rebuilds start the container detached and then optionally follow logs.
    In that workflow Ctrl+C stops log-following on the host terminal, not the
    already-detached Easy Dune Admin container.
    """
    try:
        from werkzeug import serving
    except Exception:
        return

    original_log = serving._log

    def eda_log(log_type, message, *args, **kwargs):
        rendered = message % args if args else message
        if rendered == "Press CTRL+C to quit":
            return original_log(
                log_type,
                "%s",
                "Press CTRL+C to quit (daemon continues to run detached when launched by Docker).",
                **kwargs,
            )
        return original_log(log_type, message, *args, **kwargs)

    serving._log = eda_log


if __name__ == "__main__":
    install_ctrl_c_message_stream_patch()
    install_werkzeug_quit_message_patch()
    print("Easy Dune Admin listening on http://0.0.0.0:8089")
    print("Press Ctrl+C to quit watching this process. Docker daemon/container continues when launched detached.")
    socketio.run(
        app,
        host="0.0.0.0",
        port=8089,
        allow_unsafe_werkzeug=True,
    )
