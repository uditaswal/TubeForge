from __future__ import annotations

from types import SimpleNamespace

import uvicorn

from tubeforge import tts_server


def test_server_main_uses_configured_bind_instead_of_binding_all_interfaces(monkeypatch) -> None:
    piper = SimpleNamespace(listen_host="127.0.0.1", listen_port=5015)
    settings = SimpleNamespace(pipeline=SimpleNamespace(piper=piper))
    app = object()
    calls: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(tts_server, "load_settings", lambda: settings)
    monkeypatch.setattr(tts_server, "create_tts_app", lambda selected: app)
    monkeypatch.setattr(uvicorn, "run", lambda selected_app, **kwargs: calls.append((selected_app, kwargs)))

    tts_server.main()

    assert calls == [
        (app, {"host": "127.0.0.1", "port": 5015, "access_log": False, "workers": 1})
    ]
