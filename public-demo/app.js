const judgeUrl = './evidence/judge-verification.json';
const scaleUrl = './evidence/vector-scale.json';
const pressureUrl = './evidence/agent-pressure.json';
const byId = id => document.getElementById(id);
const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
const latency = value => `${Number(value).toFixed(1)} ms`;
let liveStoryUrl = '';

async function json(url) {
  const response = await fetch(url, {cache: 'no-store'});
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

function renderJudge(evidence) {
  byId('recall1').textContent = percent(evidence.evaluation.recall['1']);
  byId('recall3').textContent = percent(evidence.evaluation.recall['3']);
  byId('recall3b').textContent = percent(evidence.evaluation.recall['3']);
  byId('recall5').textContent = percent(evidence.evaluation.recall['5']);
  byId('leakage').textContent = `${evidence.evaluation.cross_scope_leaked_documents} rows`;
  byId('foreign-rows').textContent = String(evidence.evaluation.cross_scope_leaked_documents);
  byId('semantic-p95').textContent = latency(evidence.evaluation.latency_ms.p95);
  byId('token-life').textContent = `${evidence.runtime.token_lifetime_seconds}s`;
  byId('submission').textContent = evidence.submission.status;
  byId('video-link').href = evidence.submission.video_url;
  liveStoryUrl = evidence.runtime.demo_url
    || evidence.runtime.health_url.replace(/\/healthz$/, '/demo/run?scenario=checkout-cache-pressure-v1');
  byId('proof-status').textContent = 'EVIDENCE READY';
}

async function runStory() {
  const button = byId('run-story');
  const state = byId('story-state');
  button.disabled = true;
  state.textContent = 'Running live Titan retrieval and binding database receipts…';
  try {
    if (!liveStoryUrl) throw new Error('live story endpoint is unavailable');
    const receipt = await json(liveStoryUrl);
    if (!receipt.live || receipt.scenario !== 'checkout-cache-pressure-v1') {
      throw new Error('live story receipt is invalid');
    }
    byId('story-store').textContent = receipt.storage.decision;
    byId('story-store-detail').textContent = `Sequence ${receipt.storage.sequence_no} · ${receipt.storage.embedding_model}`;
    byId('story-reject').textContent = receipt.poisoning.decision;
    byId('story-reject-detail').textContent = `Blocked: “${receipt.poisoning.attempted_instruction}”`;
    byId('story-retrieve').textContent = receipt.retrieval.selected.title;
    byId('story-retrieve-detail').textContent = `${receipt.retrieval.accepted_count}/${receipt.retrieval.returned_count} accepted · audit ${receipt.retrieval.audit_id.slice(0, 8)}`;
    byId('story-citation').href = receipt.retrieval.selected.url;
    byId('story-citation').textContent = `Open memory citation ${receipt.retrieval.selected.id.slice(0, 8)} ↗`;
    byId('story-action').textContent = `${receipt.action.worker_a} / ${receipt.action.worker_b}`;
    byId('story-action-detail').textContent = `Owner ${receipt.action.owner_worker_id} · ${receipt.action.durable_claim_count} durable claim`;
    state.textContent = `PASS · live AWS/CockroachDB story · ${receipt.receipt_cache}`;
  } catch (error) {
    state.textContent = 'HOLD · live story is temporarily unavailable; the evidence verifier remains read-only.';
    console.error(error);
  } finally {
    button.disabled = false;
  }
}

function renderScale(evidence) {
  const scales = evidence.scales || [];
  const largest = scales.at(-1);
  const allBeams = scales.flatMap(scale => scale.beams || []);
  byId('largest-scale').textContent = largest ? Number(largest.row_count).toLocaleString() : '—';
  byId('ann-plan').textContent = allBeams.length && allBeams.every(item => item.query_plan.reports_vector_search && !item.query_plan.reports_full_scan) ? 'SELECTED' : 'HOLD';
  byId('scale-leak').textContent = String(allBeams.reduce((sum, item) => sum + item.cross_scope_leaked_rows, 0));
  byId('scale-gate').textContent = evidence.gate?.status || 'HOLD';
  byId('scale-rows').innerHTML = scales.flatMap(scale => scale.beams.map(beam => `
    <tr>
      <td>${Number(scale.row_count).toLocaleString()}</td>
      <td>${beam.beam_size}</td>
      <td>${percent(beam.recall_by_k['1'])}</td>
      <td>${percent(beam.recall_by_k['5'])}</td>
      <td>${percent(beam.recall_by_k['10'])}</td>
      <td>${latency(beam.fresh_connection_first_pass_ms.p50)} / ${latency(beam.fresh_connection_first_pass_ms.p95)}</td>
      <td>${latency(beam.same_connection_immediate_repeat_ms.p50)} / ${latency(beam.same_connection_immediate_repeat_ms.p95)}</td>
    </tr>`)).join('');
}

function renderPressure(evidence) {
  const highest = evidence.levels.at(-1);
  const peak = evidence.levels.reduce((best, item) =>
    item.throughput_ops_per_second > best.throughput_ops_per_second ? item : best
  );
  byId('pressure-gate').textContent = evidence.gate.status;
  byId('pressure-peak').textContent = `${peak.throughput_ops_per_second.toFixed(1)}/s`;
  byId('pressure-peak-detail').textContent = `Peak at ${peak.concurrent_agents} agents`;
  byId('pressure-p99').textContent = latency(highest.latency_ms.p99);
  byId('pressure-p99-detail').textContent = '50 agents · 20 SQL connections';
  byId('pressure-recovery').textContent = latency(evidence.recoveries.at(-1).time_to_first_success_ms);
  byId('pressure-rows').innerHTML = evidence.levels.map((level, index) => `
    <tr>
      <td>${level.concurrent_agents}</td>
      <td>${level.operations}</td>
      <td>${level.throughput_ops_per_second.toFixed(1)}/s</td>
      <td>${latency(level.latency_ms.p50)}</td>
      <td>${latency(level.latency_ms.p95)}</td>
      <td>${latency(level.latency_ms.p99)}</td>
      <td>${level.durable_action_claims}</td>
      <td>${latency(evidence.recoveries[index].time_to_first_success_ms)}</td>
    </tr>`).join('');
}

async function quickCheck() {
  const button = byId('quick-check');
  const result = byId('quick-result');
  button.disabled = true;
  result.textContent = 'Checking immutable evidence, workflow, Pages, and MCP health…';
  try {
    const [judge, scale, pressure] = await Promise.all([
      json(judgeUrl), json(scaleUrl), json(pressureUrl)
    ]);
    const [workflow, health, page, release] = await Promise.all([
      json(judge.source.workflow_api_url),
      json(judge.runtime.health_url),
      fetch('./', {cache: 'no-store'}).then(response => response.text()),
      json(judge.release_envelope.release_api_url),
    ]);
    const releaseAsset = release.assets?.find(asset => asset.name === judge.release_envelope.asset_name);
    const passed = judge.submission.status === 'Submitted'
      && judge.evaluation.cross_scope_leaked_documents === 0
      && scale.gate.status === 'PASS'
      && pressure.gate.status === 'PASS'
      && pressure.levels.at(-1).concurrent_agents === 50
      && pressure.levels.every(level => level.durable_action_claims === 1)
      && workflow.conclusion === 'success'
      && health.ok === true
      && page.includes('Continuum Memory Firewall')
      && release.immutable === true
      && release.tag_name === judge.release_envelope.tag
      && releaseAsset?.state === 'uploaded';
    result.textContent = passed ? 'PASS · public evidence and live health agree.' : 'HOLD · open the full verifier for details.';
    byId('proof-status').textContent = passed ? 'ALL PUBLIC GATES PASS' : 'HOLD';
  } catch (error) {
    result.textContent = 'HOLD · public verification is temporarily unavailable.';
    byId('proof-status').textContent = 'HOLD';
    console.error(error);
  } finally {
    button.disabled = false;
  }
}

Promise.all([json(judgeUrl), json(scaleUrl), json(pressureUrl)])
  .then(([judge, scale, pressure]) => {
    renderJudge(judge);
    renderScale(scale);
    renderPressure(pressure);
  })
  .catch(error => { byId('proof-status').textContent = 'EVIDENCE HOLD'; console.error(error); });
byId('quick-check').addEventListener('click', quickCheck);
byId('run-story').addEventListener('click', runStory);
