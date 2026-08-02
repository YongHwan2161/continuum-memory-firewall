const judgeUrl = './evidence/judge-verification.json';
const scaleUrl = './evidence/vector-scale.json';
const byId = id => document.getElementById(id);
const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
const latency = value => `${Number(value).toFixed(1)} ms`;

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
  byId('proof-status').textContent = 'EVIDENCE READY';
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

async function quickCheck() {
  const button = byId('quick-check');
  const result = byId('quick-result');
  button.disabled = true;
  result.textContent = 'Checking immutable evidence, workflow, Pages, and MCP health…';
  try {
    const [judge, scale] = await Promise.all([json(judgeUrl), json(scaleUrl)]);
    const [workflow, health, page] = await Promise.all([
      json(judge.source.workflow_api_url),
      json(judge.runtime.health_url),
      fetch('./', {cache: 'no-store'}).then(response => response.text()),
    ]);
    const passed = judge.submission.status === 'Submitted'
      && judge.evaluation.cross_scope_leaked_documents === 0
      && scale.gate.status === 'PASS'
      && workflow.conclusion === 'success'
      && health.ok === true
      && page.includes('Continuum Memory Firewall');
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

Promise.all([json(judgeUrl), json(scaleUrl)])
  .then(([judge, scale]) => { renderJudge(judge); renderScale(scale); })
  .catch(error => { byId('proof-status').textContent = 'EVIDENCE HOLD'; console.error(error); });
byId('quick-check').addEventListener('click', quickCheck);
