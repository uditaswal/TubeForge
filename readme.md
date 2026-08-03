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
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m alembic upgrade head // only to be used in case  of db migration or changes
.\.venv\Scripts\python -m pytest
```

for Python 3.13
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m alembic upgrade head // only to be used in case of db migration or changes
python -m pytest

The default configuration at `config/default.yaml` contains no credentials and
uses a local SQLite database. Set `TUBEFORGE_CONFIG` to select another YAML
configuration file.
