"""YOUTUBE_DIRECT_SECTIONS: the proxy-free audio-first flow."""

from types import SimpleNamespace as NS

from tubeforge.clips import youtube_proxy as yp


def cfg(proxy="", direct=False):
    return NS(youtube_proxy_url=proxy, youtube_direct_sections=direct, youtube_proxy_country="",
              youtube_pot_provider_url="", youtube_download_timeout_seconds=60)


def test_direct_mode_counts_as_audio_first_capable_only_without_a_proxy():
    assert yp.proxy_configured(cfg(direct=True)) is True
    assert yp.proxy_configured(cfg()) is False
    assert yp.direct_sections(cfg(proxy="http://p:1", direct=True)) is False  # a proxy wins
    assert yp.proxy_configured(cfg(proxy="http://p:1")) is True


def test_direct_params_have_no_proxy_key(monkeypatch):
    monkeypatch.setattr(yp, "trial_config", lambda c: c)
    direct = yp.base_proxy_params("task", "abc12345678", cfg(direct=True))
    assert "proxy" not in direct and direct["noplaylist"] is True
    proxied = yp.base_proxy_params("task", "abc12345678", cfg(proxy="http://u-{session}:p@h:1", direct=True))
    assert proxied["proxy"].startswith("http://u-")
