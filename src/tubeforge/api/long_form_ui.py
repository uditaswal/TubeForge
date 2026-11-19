"""Long-form script review in the existing Creator Studio shell."""
from tubeforge.api.studio_shell import STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page


# Layout stays plain CSS: no Tailwind utility can override grid placement or the breakpoints.
LAYOUT_CSS = """
.lf-grid{display:grid;grid-template-columns:minmax(250px,320px) minmax(0,1fr);align-items:start;gap:20px}
.lf-sidebar{display:grid;align-items:start;gap:20px;min-width:0}
.lf-grid [hidden]{display:none !important}
@media(max-width:1050px){.lf-grid{grid-template-columns:1fr}.lf-sidebar{grid-template-columns:1fr 1fr}}
@media(max-width:650px){.lf-sidebar{grid-template-columns:1fr}}
@media(max-width:420px){main.shell{padding-inline:16px}}
"""

# Element and component styling, read through the design tokens.

MAIN = """
<main class="shell">
  <div class="studio-page-head"><div><h1>Long-form scripts</h1>
    <p>Prepare an original 10–15 minute script from a captured reference and independent sources.</p></div></div>
  <div class="lf-grid">
    <aside class="lf-sidebar" aria-label="Preparation and history">
      <section class="panel">
        <h2>New preparation</h2>
        <form id="lfForm">
          <label for="lfReference">Captured reference revision</label>
          <select id="lfReference" required disabled><option value="">Loading references…</option></select>
          <p class="lf-muted"><a href="/references">Capture or update a reference</a></p>
          <label for="lfTopic">Video topic</label><input id="lfTopic" required maxlength="500">
          <label for="lfAngle">New angle</label><textarea id="lfAngle" required maxlength="1000" placeholder="What should our video explain differently?"></textarea>
          <label for="lfAudience">Audience</label><input id="lfAudience" required maxlength="200" placeholder="Who is watching?">
          <details><summary>Use your own primary sources</summary>
            <label for="lfPrimaryUrls">Primary page URLs</label>
            <textarea id="lfPrimaryUrls" maxlength="6002" rows="3" aria-describedby="lfPrimaryHelp" placeholder="One HTTPS URL per line"></textarea>
            <p id="lfPrimaryHelp" class="lf-muted">Enter two or three primary pages. TubeForge captures them before drafting and skips the writer’s research call. Leave blank to use writer research.</p>
          </details>
          <label for="lfWriter">Writer</label><select id="lfWriter" required disabled></select>
          <p id="lfBudget" class="lf-muted"></p>
          <button id="lfCreate" type="submit" disabled>Queue preparation</button>
          <p id="lfCreateNotice" role="status"></p>
        </form>
      </section>
      <section class="panel">
        <h2>Preparation history</h2><p id="lfHistoryNotice" class="lf-muted" role="status">Loading history…</p>
        <ul id="lfHistory" class="lf-list"></ul><button id="lfReload" type="button" class="secondary">Refresh</button>
      </section>
    </aside>
    <section class="panel" id="lfDetail" aria-label="Script review">
      <p id="lfNotice" role="status"></p>
      <div id="lfEmpty"><h2>Review a preparation</h2><p class="lf-muted">Queue a new brief or open a saved preparation to inspect its evidence.</p></div>
      <div id="lfSelected" hidden>
        <span class="lf-state" id="lfState"></span><h2 id="lfTitle"></h2><p id="lfMeta" class="lf-muted"></p>
        <p id="lfMessage"></p><p><a id="lfOriginal">Open captured reference revision</a></p>
        <div class="lf-actions"><button id="lfCancel" type="button" class="secondary">Cancel preparation</button>
          <a id="lfExport" hidden>Download review bundle</a></div>
        <div id="lfScript" class="lf-section" hidden><h3>Narration by chapter</h3><div id="lfChapters"></div></div>
        <details class="lf-section" id="lfEvidence"><summary>Sources and claim checks</summary><div id="lfSources"></div></details>
        <details class="lf-section" id="lfEditorial"><summary>Original additions and editorial findings</summary><div id="lfFindings"></div></details>
        <details class="lf-section" id="lfPackaging"><summary>Hooks, titles and thumbnail brief</summary><div id="lfScores"></div></details>
        <details class="lf-section" id="lfUsagePanel"><summary>Usage and attempts</summary><p id="lfUsage" class="lf-muted"></p><div id="lfCalls"></div><p id="lfReceipt" role="status"></p></details>
        <details class="lf-section" id="lfActivityPanel"><summary>Activity</summary><ol id="lfActivity"></ol></details>
        <section id="lfDecision" class="lf-section" hidden aria-label="Script decision">
          <h3>Review decision</h3><p class="lf-muted">The decision applies to this exact script and evidence bundle. Rendering is a separate phase.</p>
          <div class="lf-check"><input type="checkbox" id="lfReviewed"><label for="lfReviewed">I reviewed this script, its source support and its original additions.</label></div>
          <div class="lf-actions"><button id="lfApprove" type="button">Approve script</button><button id="lfReject" type="button" class="danger">Reject script</button></div>
        </section>
      </div>
    </section>
  </div>
  <dialog id="lfConfirm" class="lf-dialog" aria-labelledby="lfConfirmTitle">
    <h2 id="lfConfirmTitle"></h2><p id="lfConfirmText"></p>
    <div class="lf-actions"><button id="lfKeep" type="button" class="secondary">Go back</button><button id="lfSaveDecision" type="button">Save decision</button></div>
  </dialog>
</main>
"""

SCRIPT = r"""
(() => {
  const el = id => document.getElementById(id);
  const root = '/api/long-form';
  const params = new URLSearchParams(location.search);
  const labels = {
    pending: 'Queued', working: 'Preparing script', reconciling: 'Checking host receipt',
    blocked: 'Needs attention', exhausted: 'Budget exhausted', awaiting_review: 'Ready for review',
    approved: 'Script approved', rejected: 'Script rejected', cancelled: 'Preparation cancelled'
  };
  const active = new Set(['pending', 'working', 'reconciling']);
  const final = new Set(['approved', 'rejected', 'cancelled']);
  let selected = null, current = null, detailVersion = 0, listVersion = 0, selectionVersion = 0;
  let currentSignature = '', historySignature = '', evidenceSignature = '', draftSignature = '', loading = false;
  let creating = false, mutating = false, inspecting = false, writers = [], confirmation = null;
  const number = value => value == null ? 'Unknown' : Number(value).toLocaleString();
  const createNode = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function say(id, text, error = false) {
    el(id).textContent = text;
    el(id).classList.toggle('lf-error', error);
  }
  function external(url, label) {
    const link = createNode('a', label);
    try {
      const target = new URL(url);
      if (['https:', 'http:'].includes(target.protocol)) link.href = target.href;
    } catch (_) {}
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }
  async function api(path, options = {}) {
    const csrf = decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/) || [])[1] || '');
    const response = await fetch(path, {
      ...options, headers: {'content-type': 'application/json', 'x-csrf-token': csrf}
    });
    if (response.status === 401) {
      location.assign('/login');
      throw Error('Sign in again.');
    }
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Check the request fields.');
    return data;
  }
  function controls() {
    const available = !loading && !mutating && current?.id === selected;
    const reviewable = available && current?.state === 'awaiting_review';
    el('lfCreate').disabled = creating || !writers.length || !el('lfReference').value;
    el('lfCancel').disabled = !available || final.has(current?.state);
    el('lfCancel').hidden = final.has(current?.state);
    el('lfDecision').hidden = current?.state !== 'awaiting_review';
    el('lfReviewed').disabled = !reviewable;
    el('lfApprove').disabled = el('lfReject').disabled = !reviewable || !el('lfReviewed').checked;
    el('lfExport').hidden = !available || !current?.review_identity;
    for (const button of el('lfCalls').querySelectorAll('button')) button.disabled = !available || inspecting;
  }
  function listOf(items, render) {
    const list = createNode('ul');
    for (const item of items) {
      const li = createNode('li');
      li.append(render(item));
      list.append(li);
    }
    return list;
  }
  function drawNarration(run) {
    const draft = run.draft;
    el('lfScript').hidden = !draft;
    el('lfChapters').replaceChildren();
    if (!draft) return;
    const sections = new Map(draft.package.script_sections.map(section => [section.section_id, section]));
    const claims = new Map(draft.package.claims.map(claim => [claim.claim_id, claim]));
    for (const chapter of draft.chapters) {
      const group = createNode('details', null, 'lf-item');
      group.append(createNode('summary', chapter.title));
      for (const id of chapter.section_ids) {
        const section = sections.get(id);
        group.append(createNode('p', section.narration, 'lf-script'));
        const sources = new Set(section.claim_ids.flatMap(claim => claims.get(claim)?.source_ids || []));
        if (sources.size) {
          const line = createNode('p', 'Sources: ', 'lf-muted');
          for (const sourceId of sources) {
            const source = run.source_packet?.sources.find(row => row.source_id === sourceId);
            if (source) {
              line.append(external(source.url, source.title), ' ');
            }
          }
          group.append(line);
        }
      }
      el('lfChapters').append(group);
    }
  }
  function drawEvidence(run) {
    const sources = run.source_packet?.sources || [];
    const evidence = el('lfSources');
    const openSources = new Set([...evidence.querySelectorAll('details[open]')].map(item => item.dataset.source));
    evidence.replaceChildren();
    if (!sources.length) evidence.append(createNode('p', 'Primary evidence is pending.', 'lf-muted'));
    for (const source of sources) {
      const item = createNode('details', null, 'lf-item');
      item.dataset.source = source.source_id;
      item.open = openSources.has(source.source_id);
      item.append(createNode('summary', source.title), external(source.url, 'Open primary source'),
        createNode('blockquote', source.excerpt),
        createNode('p', 'Response SHA-256: ' + (source.original_content_sha256 || 'Unavailable'), 'lf-muted'),
        createNode('p', 'Excerpt SHA-256: ' + (source.content_sha256 || 'Unavailable'), 'lf-muted'));
      evidence.append(item);
    }
    const claims = new Map((run.draft?.package.claims || []).map(claim => [claim.claim_id, claim]));
    for (const check of run.review?.claim_checks || []) {
      const claim = run.review_applies_to_current_draft ? claims.get(check.claim_id)?.text : null;
      const item = createNode('div', null, 'lf-item');
      item.append(createNode('strong', (claim || check.claim_id) + ' · ' + check.verdict),
        createNode('blockquote', check.source_quote), createNode('p', check.reason, 'lf-muted'));
      const source = sources.find(row => row.source_id === check.source_id);
      if (source) item.append(external(source.url, source.title));
      evidence.append(item);
    }
    if (run.review && !run.review_applies_to_current_draft)
      evidence.prepend(createNode('p', 'Claim checks refer to the earlier draft. Verify the current narration against the source excerpts.', 'lf-muted'));
  }
  function drawEditorial(run) {
    const findings = el('lfFindings');
    findings.replaceChildren();
    for (const addition of run.draft?.improvements || []) {
      const item = createNode('div', null, 'lf-item');
      const cue = run.reference.cues[addition.reference_cue_index];
      item.append(createNode('strong', addition.original_addition), createNode('p', addition.observation),
        createNode('blockquote', addition.reference_quote),
        createNode('p', 'Viewer hypothesis: ' + addition.viewer_problem_hypothesis, 'lf-muted'),
        createNode('p', 'Sections: ' + addition.section_ids.join(', '), 'lf-muted'));
      if (cue) item.append(external(run.reference.reference_url + '&t=' + Math.floor(cue.start_seconds),
        'Original cue ' + (addition.reference_cue_index + 1) + ' · ' + Math.floor(cue.start_seconds) + ' s'));
      findings.append(item);
    }
    if (!run.review) {
      findings.append(createNode('p', 'Independent findings are pending.', 'lf-muted'));
      return;
    }
    findings.append(createNode('h3', run.review_applies_to_current_draft ? 'Independent review' : 'Independent review of earlier draft'),
      createNode('p', run.review.originality_rationale), createNode('p', run.review.promise_payoff_rationale),
      listOf(run.review.findings, row => createNode('span', row.severity + ' · ' + row.category + ' · ' + row.detail)));
  }
  function drawScores(run) {
    const scores = el('lfScores'), report = run.score_report, brief = run.draft?.package.thumbnail_brief;
    scores.replaceChildren();
    if (!report) {
      scores.append(createNode('p', 'Candidate scores are pending.', 'lf-muted'));
      return;
    }
    scores.append(createNode('p', 'Scores guide editorial review. Audience performance remains unknown.', 'lf-muted'));
    const groups = [
      ['Top hooks', report.hooks, 2, row => row.hook + ' · ' + row.verdict + ' · ' + row.band + (row.selected ? ' · Opening used' : '')],
      ['Top titles', [...report.titles].sort((a, b) => b.score - a.score), 3, row => row.title + ' · ' + row.score + (row.issues.length ? ' · ' + row.issues.map(issue => issue[1]).join('. ') : '')]
    ];
    for (const [label, rows, limit, format] of groups) {
      const render = row => createNode('span', format(row));
      scores.append(createNode('h3', label), listOf(rows.slice(0, limit), render));
      const rest = createNode('details', null, 'lf-item');
      rest.append(createNode('summary', 'More candidates'), listOf(rows.slice(limit), render));
      scores.append(rest);
    }
    if (brief) scores.append(createNode('h3', 'Thumbnail direction'), createNode('p', brief.text_options.join(' / ')),
      createNode('p', brief.visual_direction), createNode('p', brief.accessibility_description, 'lf-muted'));
  }
  async function inspect(runId, stage) {
    if (inspecting || loading || mutating || selected !== runId) return;
    inspecting = true;
    controls();
    say('lfReceipt', 'Checking the saved host receipt…');
    try {
      const receipt = await api(root + '/' + runId + '/calls/' + stage + '/receipt', {method: 'POST'});
      if (selected === runId) say('lfReceipt', 'Host receipt: ' + receipt.state + '. ' + receipt.notice);
    } catch (error) {
      if (selected === runId) say('lfReceipt', error.message, true);
    } finally {
      inspecting = false;
      controls();
    }
  }
  function drawUsage(run) {
    const usage = run.usage;
    const observed = field => {
      const counter = usage[field];
      return counter?.total == null ? 'Unknown (known subtotal ' + number(counter?.known_subtotal) + ')' : number(counter.total);
    };
    el('lfUsage').textContent = [
      'Calls reserved ' + usage.reserved_calls + '/' + run.token_policy.maximum_calls,
      'Narration attempts ' + usage.narration_attempts + '/' + run.token_policy.maximum_narration_attempts,
      'Charged budget ' + number(run.reserved_tokens) + '/' + number(run.token_policy.total_reserved_tokens),
      'Observed input ' + observed('input_tokens'), 'Observed output ' + observed('output_tokens')
    ].join(' · ');
    const calls = el('lfCalls'), previous = new Set([...calls.querySelectorAll('details[open]')].map(row => row.dataset.call));
    calls.replaceChildren();
    for (const call of run.calls) {
      const item = createNode('details', null, 'lf-item');
      item.dataset.call = call.call_id;
      item.open = previous.has(call.call_id);
      const result = call.response?.result;
      const outcome = call.draft_outcome;
      const rejection = outcome?.disposition === 'rejected';
      const stageLabel = call.stage[0].toUpperCase() + call.stage.slice(1);
      item.append(createNode('summary', stageLabel + ' · ' + (rejection ? 'Rejected by validation' : call.state)),
        createNode('p', [call.provider, call.model, 'Host call ' + call.state, 'Reserved ' + number(call.reservation_tokens),
          'Observed input ' + number(call.usage?.input_tokens), 'Observed output ' + number(call.usage?.output_tokens)].filter(Boolean).join(' · '), 'lf-muted'));
      if (call.failure_message || rejection) item.append(createNode('p', call.failure_message || outcome?.reason || 'Draft failed validation.', 'lf-error'));
      const superseded = outcome?.disposition === 'superseded';
      if (result?.raw_output || result?.output != null) {
        const saved = createNode('details');
        saved.open = rejection || superseded || call.state === 'failed';
        saved.append(createNode('summary', result.truncated ? 'Retained output prefix' : 'Saved stage output'));
        const reveal = () => {
          if (!saved.open || saved.querySelector('pre')) return;
          const raw = createNode('pre', result.raw_output || JSON.stringify(result.output, null, 2), 'lf-raw');
          raw.tabIndex = 0;
          saved.append(raw);
        };
        saved.ontoggle = reveal;
        reveal();
        item.append(saved);
      }
      if (['reserved', 'prepared', 'dispatching', 'unknown'].includes(call.state)) {
        const check = createNode('button', 'Check host receipt', 'secondary');
        check.type = 'button';
        check.onclick = () => inspect(run.id, call.stage);
        item.append(check);
      }
      calls.append(item);
    }
  }
  function show(run) {
    const old = current;
    current = run;
    if (old?.id !== run.id || old?.review_identity !== run.review_identity) {
      el('lfReviewed').checked = false;
      if (el('lfConfirm').open) el('lfConfirm').close();
    }
    if (run.state !== 'awaiting_review' && el('lfConfirm').open) el('lfConfirm').close();
    loading = false;
    el('lfEmpty').hidden = true;
    el('lfSelected').hidden = false;
    const signature = JSON.stringify(run);
    if (signature === currentSignature) {
      controls();
      return;
    }
    currentSignature = signature;
    el('lfTitle').textContent = run.request.topic;
    el('lfState').textContent = labels[run.state] || run.state;
    el('lfState').dataset.state = run.state;
    const owner = run.request.script_owner === 'claude' ? 'Claude' : 'Codex';
    el('lfMeta').textContent = run.request.target_duration_seconds / 60 + ' min target · '
      + owner + (run.expected_model ? ' · ' + run.expected_model : '')
      + ' · Reference revision ' + run.intake_revision;
    el('lfMessage').textContent = run.message || (active.has(run.state)
      ? run.next_stage === 'capture_sources' ? 'Next: capture supplied primary pages.' : 'Next stage: ' + run.next_stage
      : '');
    el('lfOriginal').href = '/references?intake=' + encodeURIComponent(run.intake_id) + '&revision=' + run.intake_revision;
    el('lfExport').href = root + '/' + run.id + '/export?review_identity=' + run.review_identity;
    const newDraft = JSON.stringify([run.id, run.draft_sha256]);
    if (newDraft !== draftSignature) {
      draftSignature = newDraft;
      drawNarration(run);
      drawScores(run);
    }
    const newEvidence = JSON.stringify([run.id, run.review_identity, run.source_packet]);
    if (newEvidence !== evidenceSignature) {
      evidenceSignature = newEvidence;
      drawEvidence(run);
      drawEditorial(run);
    }
    drawUsage(run);
    el('lfActivity').replaceChildren(...run.activity.map(event => createNode('li',
      event.event.replaceAll('_', ' ') + ' · ' + event.actor + ' · ' + new Date(event.created_at).toLocaleString())));
    controls();
  }
  async function loadDetail() {
    if (!selected || mutating) return;
    const id = selected, version = ++detailVersion;
    try {
      const run = await api(root + '/' + id);
      if (selected !== id || version !== detailVersion || mutating) return;
      show(run);
      say('lfNotice', '');
    } catch (error) {
      if (selected !== id || version !== detailVersion) return;
      say('lfNotice', 'Could not refresh preparation. ' + error.message, true);
    }
  }
  function choose(id) {
    if (selected === id && current?.id === id) return;
    selected = id;
    selectionVersion++;
    current = null;
    loading = true;
    if (el('lfConfirm').open) el('lfConfirm').close();
    el('lfSelected').hidden = true;
    el('lfEmpty').hidden = true;
    el('lfReviewed').checked = false;
    say('lfReceipt', '');
    say('lfNotice', 'Loading selected preparation…');
    for (const button of el('lfHistory').querySelectorAll('button')) button.setAttribute('aria-current', String(button.dataset.run === id));
    controls();
    return loadDetail();
  }
  async function loadHistory() {
    const version = ++listVersion;
    try {
      const result = await api(root);
      if (version !== listVersion) return;
      const signature = JSON.stringify(result.items);
      if (signature !== historySignature) {
        historySignature = signature;
        el('lfHistory').replaceChildren(...result.items.map(run => {
          const item = createNode('li'), button = createNode('button');
          button.type = 'button';
          button.dataset.run = run.id;
          button.setAttribute('aria-current', String(run.id === selected));
          button.append(createNode('strong', run.topic), createNode('span', labels[run.state] || run.state, 'lf-muted'));
          button.onclick = () => choose(run.id);
          item.append(button);
          return item;
        }));
      }
      say('lfHistoryNotice', result.items.length ? 'Latest ' + result.items.length + ' preparations' : 'No saved preparations yet.');
      if (!selected && result.items.length) await choose(result.items[0].id);
    } catch (error) {
      if (version === listVersion) say('lfHistoryNotice', 'Could not refresh history. ' + error.message, true);
    }
  }
  async function loadOptions() {
    try {
      const [config, history] = await Promise.all([api(root + '/options'), api('/api/reference-intakes')]);
      writers = config.writers;
      el('lfWriter').replaceChildren(...writers.map((writer, index) => {
        const option = createNode('option', writer.label);
        option.value = index;
        return option;
      }));
      el('lfWriter').disabled = !writers.length;
      el('lfBudget').textContent = 'Up to ' + config.token_policy.maximum_calls + ' calls and '
        + config.token_policy.maximum_narration_attempts + ' narration attempts. Actual provider usage appears in review.';
      const refs = history.items.map(item => item.intake).filter(item => item.state === 'ready');
      const requestedId = params.get('intake'), revision = Number(params.get('revision'));
      if (/^[a-f0-9]{32}$/.test(requestedId || '') && Number.isSafeInteger(revision) && revision > 0
          && !refs.some(item => item.intake_id === requestedId && item.revision === revision)) {
        try {
          const exact = await api('/api/reference-intakes/' + requestedId + '?revision=' + revision);
          if (exact.intake.state === 'ready') refs.unshift(exact.intake);
        } catch (error) {
          say('lfCreateNotice', 'Could not open the selected reference revision. ' + error.message, true);
        }
      }
      const placeholder = createNode('option', refs.length ? 'Choose a captured revision' : 'No ready references');
      placeholder.value = '';
      el('lfReference').replaceChildren(placeholder, ...refs.map(item => {
        const option = createNode('option', item.snapshot.title + ' · r' + item.revision + ' · ' + item.request.target_duration_seconds / 60 + ' min');
        option.value = item.intake_id + ':' + item.revision;
        option.dataset.topic = item.snapshot.title;
        return option;
      }));
      el('lfReference').disabled = !refs.length;
      if (requestedId && revision) el('lfReference').value = requestedId + ':' + revision;
      suggestTopic();
    } catch (error) {
      say('lfCreateNotice', 'Could not load preparation choices. ' + error.message, true);
    }
    controls();
  }
  function suggestTopic() {
    if (!el('lfTopic').value) el('lfTopic').value = el('lfReference').selectedOptions[0]?.dataset.topic || '';
    controls();
  }
  el('lfReference').onchange = suggestTopic;
  el('lfForm').onsubmit = async event => {
    event.preventDefault();
    if (creating || el('lfCreate').disabled) return;
    const [intake_id, revision] = el('lfReference').value.split(':');
    const writer = writers[Number(el('lfWriter').value)], version = selectionVersion;
    creating = true;
    controls();
    say('lfCreateNotice', 'Saving preparation…');
    try {
      const run = await api(root, {method: 'POST', body: JSON.stringify({
        intake_id, intake_revision: Number(revision), topic: el('lfTopic').value, angle: el('lfAngle').value,
        audience: el('lfAudience').value, owner: writer.id, model: writer.model,
        primary_urls: el('lfPrimaryUrls').value.split('\n').map(url => url.trim()).filter(Boolean)
      })});
      if (version === selectionVersion) {
        choose(run.id);
        detailVersion++;
        show(run);
        say('lfNotice', '');
        if (innerWidth < 1050) el('lfDetail').scrollIntoView({block: 'start'});
      }
      say('lfCreateNotice', 'Preparation saved. Exact duplicates use the existing allowance.');
      loadHistory();
    } catch (error) {
      say('lfCreateNotice', error.message, true);
    } finally {
      creating = false;
      controls();
    }
  };
  async function mutate(action, target, body) {
    if (mutating || loading || current?.id !== target || selected !== target) return;
    mutating = true;
    detailVersion++;
    controls();
    say('lfNotice', 'Saving ' + (action === 'cancel' ? 'cancellation' : 'decision') + '…');
    try {
      const run = await api(root + '/' + target + '/' + action, {method: 'POST', body: body && JSON.stringify(body)});
      if (selected === target) {
        detailVersion++;
        show(run);
        say('lfNotice', action === 'cancel' ? 'Cancellation saved.' : 'Exact script decision saved.');
      }
      loadHistory();
    } catch (error) {
      if (selected === target) say('lfNotice', error.message, true);
    } finally {
      mutating = false;
      controls();
      if (selected !== target) loadDetail();
    }
  }
  function askDecision(decision) {
    if (!el('lfReviewed').checked || loading || mutating || current?.state !== 'awaiting_review' || current.id !== selected) return;
    confirmation = {id: current.id, review_identity: current.review_identity, decision, reviewed_evidence: true};
    el('lfConfirmTitle').textContent = decision === 'approved' ? 'Approve this script?' : 'Reject this script?';
    el('lfConfirmText').textContent = current.request.topic + ' · Bundle ' + current.review_identity.slice(0, 12);
    el('lfConfirm').showModal();
    el('lfKeep').focus();
  }
  el('lfReviewed').onchange = controls;
  el('lfApprove').onclick = () => askDecision('approved');
  el('lfReject').onclick = () => askDecision('rejected');
  el('lfKeep').onclick = () => el('lfConfirm').close();
  el('lfSaveDecision').onclick = () => {
    if (!confirmation || confirmation.id !== selected || confirmation.review_identity !== current?.review_identity) return;
    const {id, ...body} = confirmation;
    el('lfConfirm').close();
    mutate('decision', id, body);
  };
  el('lfCancel').onclick = () => mutate('cancel', selected);
  el('lfReload').onclick = () => { loadHistory(); loadDetail(); };
  loadOptions();
  loadHistory();
  setInterval(() => {
    if (!document.hidden && (!current || active.has(current.state))) {
      loadHistory();
      loadDetail();
    }
  }, 4000);
})();
"""


def render_long_form_html(username=None):
    content = wrap_studio_page('long-form', username, 'Long-form scripts', MAIN)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Long-form scripts · TubeForge</title><style>' + LAYOUT_CSS + '</style></head>'
            '<body>' + content + '<script>' + SCRIPT + STUDIO_STATIC_MENU_SCRIPT + '</script></body></html>')
