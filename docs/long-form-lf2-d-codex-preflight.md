# LF2 restricted Codex pilot preflight

The 10-minute library book-sorting brief uses the selected 3Blue1Brown transcript. It follows two hypothetical predictions through one weight update and checks the arithmetic, evidence and distinction from the reference. TubeForge captured three supplied primary pages locally. The preparation ledger has zero writer calls.

The installed socket answered but rejected the LF2 preflight operation as an unknown request schema. The installed Python environment lacks the LF2 module and tokenizer dependency. The reviewed wheel accepted the exact draft preflight locally using the pinned runtime paths and matched all eight skill hashes. This verifies wheel preparation. The actual restricted service still needs the upgrade and a matching socket preflight. **74 focused tests passed.**

| Setting | Prepared value |
| --- | --- |
| Run | `d05a7f8e711e4da2b4857193ce04b3e0` |
| Writer | Dedicated subscription Codex CLI, fixed `gpt-5.6-sol` |
| Plan | Draft, independent review, and at most one repair |
| First reservation | 31,966 units including 15,966 local input units |
| Admission | 100,000 total units |
| Fallback | None |

The wheel is `artifacts/review/long-form-lf2-d-codex/tubeforge-0.1.0-py3-none-any.whl`, SHA-256 `94faf811f5f1c7d33b38e5e852e56110bfd27bbeb1d92476d03373f18c0d96cf`. This preparation used zero model calls. Local admission is separate from observed provider usage and cannot predict the five-hour allowance.

The operator approved the host update and this exact 100,000-unit pilot. The host requires an interactive administrator password. Run the following from the repository root once the restricted service is idle. The existing pinned runtime, dedicated account, socket and receipts are retained. The pilot uses an isolated preparation database.

```bash
pilot_wheel=artifacts/review/long-form-lf2-d-codex/tubeforge-0.1.0-py3-none-any.whl
runner_venv=/opt/tubeforge-codex-runner/venv
runner_cache=/opt/tubeforge-codex-runner/tokenizer-cache
printf '%s  %s\n' '94faf811f5f1c7d33b38e5e852e56110bfd27bbeb1d92476d03373f18c0d96cf' "$pilot_wheel" | sha256sum -c &&
sudo "$runner_venv/bin/python" -m pip install 'tiktoken>=0.12,<1' 'Pillow>=11,<13' &&
sudo "$runner_venv/bin/python" -m pip install --force-reinstall --no-deps "$pilot_wheel" &&
sudo install -d -o root -g root -m 0755 "$runner_cache" &&
sudo env TIKTOKEN_CACHE_DIR="$runner_cache" "$runner_venv/bin/python" -c "import tiktoken; tiktoken.get_encoding('o200k_base')" &&
sudo chmod -R a+rX "$runner_cache" &&
sudo install -o root -g root -m 0644 docs/deploy/tubeforge-codex-runner.service /etc/systemd/system/tubeforge-codex-runner.service &&
sudo systemctl daemon-reload &&
sudo systemctl reset-failed tubeforge-codex-runner.service tubeforge-codex-runner.socket &&
sudo systemctl start tubeforge-codex-runner.socket &&
sudo systemctl try-restart tubeforge-codex-runner.service
```

Verify that the dedicated CLI reports a ChatGPT subscription login:

```bash
runner_runtime=/opt/tubeforge-codex-runner/codex-runtime
sudo -u tubeforge-codex env CODEX_HOME=/var/lib/tubeforge-codex/.codex \
  PATH="$runner_runtime/node/bin:/usr/bin:/bin" "$runner_runtime/node/bin/node" \
  "$runner_runtime/lib/node_modules/@openai/codex/bin/codex.js" login status
```

[Host deployment and tokenizer setup](deploy/codex-runner-runtime.md#long-form-preparation)

After the update, run the no-generation socket preflight from the checkout:

```bash
.venv-benchmark/bin/python -I artifacts/review/long-form-lf2-d-codex/preflight_installed.py
```

The expected result is exact model, request, admission and resource agreement. After the matching preflight and dedicated subscription check, the approved launcher accepts `--run-approved-subscription-pilot` for this exact brief and budget. Acceptance then requires the real draft and independent review, checked arithmetic and grounding, local hook and title scores and observed usage.

The first installed preflight reset before dispatch. The host import check reproduced missing Pillow (PIL), and the service and socket reached their startup limit. The install command above now includes Pillow. The pilot ledger remains untouched.

## Revised held-out book pilot

The original pilot is terminal. The new ten-minute brief follows two books
whose predictions move in the same direction after one weight update. The
viewer predicts whether the held-out book improves before seeing its error
grow. The run reuses the three captured primary pages and starts at draft
with an empty call ledger.

| Setting | Reviewed value |
| --- | --- |
| Isolated preparation | `8a34b8a9acff49f6916b59c9c9d889f4` |
| Provider | Dedicated subscription Codex CLI, fixed `gpt-5.6-sol` |
| Dispatch | One draft and one independent review if admitted |
| First reservation | 32,026 units |
| Total admission | 100,000 units |
| Fallback and repair | None |

The installed socket answered and matched the model, request, schema and all
eight skill hashes. Its prompt was stale and reserved 32,009 units. The newly
built wheel matches the exact 32,026-unit admission and all eight skill
hashes. The staged wheel and request are under
`artifacts/review/long-form-lf2-d-codex/held-out-books-pilot/`.

Once the host service is idle, an administrator can verify and install the
staged wheel. The pinned CLI, login, tokenizer cache and existing receipts
stay in place.

```sh
pilot_dir=artifacts/review/long-form-lf2-d-codex/held-out-books-pilot
pilot_wheel="$pilot_dir/tubeforge-0.1.0-py3-none-any.whl"
printf '%s  %s\n' 'a787a04d560c50612d3ab9348cc4a46955a7e477298893010ca9d93fa9b2772d' "$pilot_wheel" | sha256sum -c &&
sudo /opt/tubeforge-codex-runner/venv/bin/python -m pip install --force-reinstall --no-deps "$pilot_wheel" &&
sudo systemctl try-restart tubeforge-codex-runner.service
```

The following sends only a zero-call preflight to the updated socket:

```sh
PYTHONPATH=src .venv-benchmark/bin/python artifacts/review/long-form-lf2-d-codex/held-out-books-pilot/preflight.py
```

A matching installed preflight and separate authorization for this pilot
gate dispatch. Acceptance requires the exact independent review, checked toy
arithmetic, grounding, originality and hook/title reports. Report observed
usage separately from local admission and any unknown subscription fraction.
