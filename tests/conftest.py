"""Keep test runs from writing into the real data/logs directory."""

import os
import tempfile

os.environ.setdefault("TUBEFORGE_LOG_DIR", tempfile.mkdtemp(prefix="tubeforge-test-logs-"))
os.environ.setdefault("TUBEFORGE_LOG_HEARTBEAT_SECONDS", "0")
