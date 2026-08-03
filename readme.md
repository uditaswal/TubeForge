# TubeForge

TubeForge is a self-hosted YouTube production pipeline. This initial scaffold
provides configuration loading, database migration support, a health endpoint,
and pure provider-neutral content contracts plus a resumable pipeline state
policy. It deliberately contains no provider adapters, media processing, or
publishing integrations.

## Local development

Use Python 3.12 or 3.13 and install the development extra:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m pytest
```

The default configuration at `config/default.yaml` contains no credentials and
uses a local SQLite database. Set `TUBEFORGE_CONFIG` to select another YAML
configuration file.
