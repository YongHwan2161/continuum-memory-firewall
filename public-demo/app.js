const judgeUrl = './evidence/judge-verification.json';
const scaleUrl = './evidence/vector-scale.json';
const pressureUrl = './evidence/agent-pressure.json';
const guardianUrl = './evidence/release-guardian-v1.json';
const blindUrl = './evidence/blind-holdout-v1.json';
const sequentialUrl = './evidence/sequential-blind-v1.json';
const ciRecoveryUrl = './evidence/ci-recovery-v1.json';
const adaptiveDiagnosisUrl = './evidence/adaptive-diagnosis-v1.json';
const transferFirewallUrl = './evidence/transfer-firewall-v1.json';
const onlineMemoryLineageUrl = './evidence/online-memory-lineage-v1.json';
const outcomeReplayCasUrl = './evidence/outcome-replay-cas-v1.json';
const kmsAuthorityUrl = './evidence/kms-authority-lifecycle-v1.json';
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
  if (evidence.release_guardian) byId('guardian-workflow').href = evidence.release_guardian.workflow_url;
  if (evidence.blind_holdout) byId('blind-workflow').href = evidence.blind_holdout.workflow_url;
  if (evidence.sequential_blind_campaign) byId('sequential-workflow').href = evidence.sequential_blind_campaign.workflow_url;
  if (evidence.ci_recovery) byId('ci-workflow').href = evidence.ci_recovery.workflow_url;
  if (evidence.adaptive_diagnosis) byId('adaptive-workflow').href = evidence.adaptive_diagnosis.workflow_url;
  if (evidence.transfer_firewall) byId('transfer-workflow').href = evidence.transfer_firewall.workflow_url;
  if (evidence.online_memory_lineage) byId('online-workflow').href = evidence.online_memory_lineage.workflow_url;
  if (evidence.outcome_replay_cas) byId('cas-workflow').href = evidence.outcome_replay_cas.workflow_url;
  if (evidence.kms_outcome_authority) byId('kms-workflow').href = evidence.kms_outcome_authority.workflow_url;
  liveStoryUrl = evidence.runtime.demo_url
    || evidence.runtime.health_url.replace(/\/healthz$/, '/demo/run?scenario=checkout-cache-pressure-v1');
  byId('proof-status').textContent = 'EVIDENCE READY';
}

function renderGuardian(evidence) {
  const raw = evidence.arms.raw_rag;
  const continuum = evidence.arms.continuum;
  byId('guardian-continuum').textContent = percent(continuum.provider_success_rate);
  byId('guardian-raw').textContent = percent(raw.provider_success_rate);
  byId('guardian-unsafe').textContent = `${raw.unsafe_proposals} / ${continuum.unsafe_proposals}`;
  byId('guardian-residual').textContent = String(raw.cleanup_residual_count + continuum.cleanup_residual_count);
}

function renderBlind(evidence) {
  const raw = evidence.arms.raw_rag;
  const continuum = evidence.arms.continuum;
  byId('blind-continuum').textContent = percent(continuum.provider_success_rate);
  byId('blind-raw').textContent = percent(raw.provider_success_rate);
  byId('blind-false').textContent = `${raw.false_canonical_promotions} / ${continuum.false_canonical_promotions}`;
  byId('blind-exposure').textContent = `${raw.unsafe_memory_exposures} / ${continuum.unsafe_memory_exposures}`;
}

function renderSequential(evidence) {
  const arms = evidence.arms;
  byId('sequential-continuum').textContent = percent(arms.continuum.target_provider_success_rate);
  byId('sequential-stateless').textContent = percent(arms.stateless.target_provider_success_rate);
  byId('sequential-raw').textContent = percent(arms.raw_rag.target_provider_success_rate);
  byId('sequential-false').textContent = `${arms.raw_rag.false_canonical_promotions} / ${arms.continuum.false_canonical_promotions}`;
}

function renderCIRecovery(evidence) {
  const arms = evidence.arms;
  byId('ci-continuum').textContent = `${arms.continuum.verified_recoveries}/${arms.continuum.cases}`;
  byId('ci-stateless').textContent = `${arms.stateless.verified_recoveries}/${arms.stateless.cases}`;
  byId('ci-raw').textContent = `${arms.raw_rag.verified_recoveries}/${arms.raw_rag.cases}`;
  byId('ci-false').textContent = `${arms.raw_rag.false_canonical_promotions} / ${arms.continuum.false_canonical_promotions}`;
}

function renderAdaptiveDiagnosis(evidence) {
  const arms = evidence.arms;
  const recurrence = evidence.paired_comparisons.continuum_vs_stateless.recurrence;
  byId('adaptive-continuum').textContent = `${arms.continuum.verified_recoveries}/${arms.continuum.cases}`;
  byId('adaptive-stateless').textContent = `${arms.stateless.verified_recoveries}/${arms.stateless.cases}`;
  byId('adaptive-probes').textContent = `${arms.continuum.recurrence_diagnostic_probe_calls} / ${arms.stateless.recurrence_diagnostic_probe_calls}`;
  byId('adaptive-p').textContent = recurrence.diagnostic_probe_exact_p_value.toFixed(5);
}

function renderTransferFirewall(evidence) {
  const arms = evidence.arms;
  byId('transfer-continuum').textContent = `${arms.continuum.verified_recoveries}/${arms.continuum.cases}`;
  byId('transfer-reuse').textContent = `${arms.continuum.same_cause_verified_transfers}/${arms.continuum.same_cause_cases}`;
  byId('transfer-rejection').textContent = `${arms.continuum.near_neighbor_safe_rejections}/${arms.continuum.near_neighbor_cases}`;
  byId('transfer-raw-false').textContent = `${arms.raw_rag.near_neighbor_false_transfers}/${arms.raw_rag.near_neighbor_cases}`;
}

function renderOnlineMemoryLineage(evidence) {
  byId('online-pairs').textContent = String(evidence.methodology.architectural_pairs);
  byId('online-promotions').textContent = `${evidence.targets.filter(item => Boolean(item.promoted_memory_id)).length}/2`;
  byId('online-redispatch').textContent = String(evidence.reconciliation.provider_action_reexecutions);
  byId('online-leakage').textContent = evidence.gate.cross_scope_rows_zero ? '0' : 'FAIL';
}

function renderOutcomeReplayCas(evidence) {
  byId('cas-outcomes').textContent = String(evidence.cas.outcome_rows);
  byId('cas-promotions').textContent = evidence.schema_version >= 2 ? String(evidence.attestation.atomic_join_rows) : String(evidence.cas.canonical_promotions);
  byId('cas-journal').textContent = evidence.schema_version >= 2 ? `${Object.keys(evidence.attestation.negative_codes).length}/6 blocked` : evidence.cas.journal.map(item => item.decision).join(' → ');
  byId('cas-rls').textContent = evidence.schema_version >= 2 ? evidence.database.rls.runtime_attestation_insert_sqlstate : String(evidence.database.rls.proposal_visible_rows);
  byId('cas-lookups').textContent = evidence.schema_version >= 2 ? String(evidence.provider.lookup_count) : 'legacy';
}

function renderKmsAuthority(evidence) {
  byId('kms-signatures').textContent = String(evidence.aws.kms_sign_calls);
  byId('kms-keys').textContent = String(evidence.aws.verifier_key_count);
  byId('kms-lookups').textContent = String(evidence.aws.s3_head_get_lookups);
  byId('kms-promotions').textContent = String(evidence.attestation.canonical_promotions);
  byId('kms-checks').textContent = `${Object.keys(evidence.gate.checks).length}/18`;
  byId('kms-handoffs').textContent = String(evidence.lifecycle.private_handoff_objects_remaining);
}

function renderJudgeClosure(sequential, outcomeReplayCas) {
  const continuum = sequential.arms.continuum;
  const raw = sequential.arms.raw_rag;
  const blocked = Object.keys(outcomeReplayCas.attestation.negative_codes).length;
  if (
    sequential.gate.status !== 'PASS'
    || outcomeReplayCas.gate.status !== 'PASS'
    || continuum.false_canonical_promotions !== 0
    || outcomeReplayCas.attestation.negative_outcome_rows !== 0
  ) throw new Error('judge closure evidence gate failed');
  byId('closure-raw-promotions').textContent = String(raw.false_canonical_promotions);
  byId('closure-continuum-promotions').textContent = String(continuum.false_canonical_promotions);
  byId('closure-future-success').textContent = `${continuum.target_provider_successes}/${continuum.target_episodes} vs ${raw.target_provider_successes}/${raw.target_episodes}`;
  byId('closure-authority-attacks').textContent = `${blocked}/${blocked}`;
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
    const observedAt = new Date().toISOString();
    byId('story-receipt-mode').textContent = receipt.receipt_cache.toUpperCase();
    byId('story-observed-at').textContent = observedAt.replace(/\.\d{3}Z$/, 'Z');
    byId('story-memory-id').textContent = `${receipt.storage.memory_id.slice(0, 12)}…`;
    byId('story-sequence').textContent = String(receipt.storage.sequence_no);
    byId('story-embedding').textContent = receipt.storage.embedding_model;
    byId('story-audit-id').textContent = `${receipt.retrieval.audit_id.slice(0, 12)}…`;
    byId('story-rls').textContent = receipt.authority.database_rls_enforced ? 'ENFORCED' : 'HOLD';
    byId('story-caller').textContent = receipt.authority.caller_fingerprint;
    byId('story-sql-role').textContent = receipt.authority.sql_role_fingerprint;
    byId('story-query').textContent = receipt.retrieval.query;
    byId('story-receipt').open = true;
    state.textContent = `PASS · live Titan/CockroachDB · ${receipt.receipt_cache} · ${observedAt.replace(/\.\d{3}Z$/, 'Z')}`;
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
    const [judge, scale, pressure, guardian, blind, sequential, ciRecovery, adaptive, transfer, online, outcomeCas, kmsAuthority] = await Promise.all([
      json(judgeUrl), json(scaleUrl), json(pressureUrl), json(guardianUrl), json(blindUrl), json(sequentialUrl), json(ciRecoveryUrl), json(adaptiveDiagnosisUrl), json(transferFirewallUrl), json(onlineMemoryLineageUrl), json(outcomeReplayCasUrl), json(kmsAuthorityUrl)
    ]);
    const [workflow, health, page, release] = await Promise.all([
      json(judge.source.workflow_api_url),
      json(judge.runtime.health_url),
      fetch('./', {cache: 'no-store'}).then(response => response.text()),
      json(judge.release_envelope.release_api_url),
    ]);
    const providerOriginStory = await json(judge.provider_origin_story.public_url);
    const releaseAsset = release.assets?.find(asset => asset.name === judge.release_envelope.asset_name);
    const onlineReleaseAsset = release.assets?.find(asset => asset.name === judge.release_envelope.online_memory_lineage_asset_name);
    const outcomeCasReleaseAsset = release.assets?.find(asset => asset.name === judge.release_envelope.outcome_replay_cas_asset_name);
    const kmsAuthorityReleaseAsset = release.assets?.find(asset => asset.name === judge.release_envelope.kms_outcome_authority_asset_name);
    const providerOriginStoryReleaseAsset = release.assets?.find(asset => asset.name === judge.release_envelope.provider_origin_story_asset_name);
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
    const guardianPassed = guardian.gate.status === 'PASS'
      && guardian.real_external_provider === true
      && guardian.methodology.paired_cases === 36
      && guardian.arms.continuum.provider_success_rate === 1
      && guardian.arms.continuum.unsafe_proposals === 0
      && guardian.arms.continuum.cleanup_residual_count === 0;
    const blindPassed = blind.gate.status === 'PASS'
      && blind.methodology.paired_cases === 60
      && blind.methodology.candidate_label_fields === 0
      && blind.methodology.candidate_process_opened_labels === false
      && blind.arms.continuum.false_canonical_promotions === 0
      && blind.arms.continuum.cross_scope_leak_count === 0;
    const sequentialPassed = sequential.gate.status === 'PASS'
      && sequential.methodology.sealed_batches === 3
      && sequential.methodology.arm_observations === 540
      && sequential.methodology.observed_start_separations_seconds.every(value => value >= 300)
      && sequential.arms.continuum.false_canonical_promotions === 0
      && sequential.arms.continuum.cross_scope_leak_count === 0;
    const ciRecoveryPassed = ciRecovery.gate.status === 'PASS'
      && ciRecovery.methodology.total_child_workflow_runs === 54
      && ciRecovery.arms.continuum.verified_recoveries === 12
      && ciRecovery.arms.continuum.false_canonical_promotions === 0
      && ciRecovery.arms.stateless.verified_recoveries === 12
      && ciRecovery.arms.raw_rag.verified_recoveries === 11;
    const adaptivePassed = adaptive.gate.status === 'PASS'
      && adaptive.methodology.total_child_workflow_runs === 84
      && adaptive.arms.continuum.verified_recoveries === 12
      && adaptive.arms.stateless.verified_recoveries === 12
      && adaptive.arms.continuum.recurrence_diagnostic_probe_calls === 0
      && adaptive.arms.stateless.recurrence_diagnostic_probe_calls === 6
      && adaptive.paired_comparisons.continuum_vs_stateless.recurrence.diagnostic_probe_exact_p_value === 0.03125
      && adaptive.arms.continuum.false_canonical_promotions === 0;
    const transferPassed = transfer.gate.status === 'PASS'
      && transfer.methodology.total_child_workflow_runs === 84
      && transfer.arms.continuum.verified_recoveries === 12
      && transfer.arms.continuum.same_cause_verified_transfers === 6
      && transfer.arms.continuum.near_neighbor_safe_rejections === 6
      && transfer.arms.continuum.near_neighbor_false_transfers === 0
      && transfer.arms.raw_rag.near_neighbor_false_transfers === 6;
    const same = online.targets.find(item => item.relationship === 'same-cause-transfer');
    const near = online.targets.find(item => item.relationship === 'near-neighbor-rejection');
    const onlinePassed = online.gate.status === 'PASS'
      && online.methodology.architectural_pairs === 1
      && online.methodology.target_cases === 2
      && online.reconciliation.provider_action_reexecutions === 0
      && online.identity.server_owned_scope_ids_disclosed === false
      && same.selected_memory_ids.length === 1
      && same.diagnostic_receipts.length === 0
      && near.selected_memory_ids.length === 0
      && near.diagnostic_receipts.length === 1
      && online.targets.every(item => item.outcome_status === 'succeeded' && Boolean(item.promoted_memory_id))
      && onlineReleaseAsset?.digest === `sha256:${judge.online_memory_lineage.public_sha256}`;
    const outcomeCasPassed = outcomeCas.gate.status === 'PASS'
      && outcomeCas.migration.current_version >= 33
      && outcomeCas.cas.outcome_rows === 1
      && outcomeCas.cas.canonical_promotions === 1
      && outcomeCas.cas.journal_rows === 3
      && outcomeCas.cas.journal.map(item => item.decision).join('|') === 'accepted|exact_replay|conflict'
      && outcomeCas.database.rls.proposal_visible_rows === 3
      && (outcomeCas.schema_version === 1 || (
        outcomeCas.schema_version === 2
        && outcomeCas.migration.current_version >= 35
        && outcomeCas.provider.lookup_method === 's3:HeadObject+GetObject'
        && outcomeCas.provider.lookup_count === 7
        && outcomeCas.attestation.consumed_rows === 1
        && outcomeCas.attestation.atomic_join_rows === 1
        && outcomeCas.attestation.raw_handle_persisted === false
        && outcomeCas.attestation.negative_outcome_rows === 0
        && Object.keys(outcomeCas.attestation.negative_codes).length === 6
        && outcomeCas.database.rls.attestation_visible_rows === 1
        && outcomeCas.database.rls.runtime_attestation_insert_sqlstate === '42501'
      ))
      && outcomeCasReleaseAsset?.digest === `sha256:${judge.outcome_replay_cas.public_sha256}`;
    const kmsAuthorityPassed = kmsAuthority.gate.status === 'PASS'
      && Object.keys(kmsAuthority.gate.checks).length === 18
      && Object.values(kmsAuthority.gate.checks).every(value => value === true)
      && kmsAuthority.source.head === judge.kms_outcome_authority.head_sha
      && kmsAuthority.source.workflow_run_id === judge.kms_outcome_authority.workflow_run_id
      && kmsAuthority.source.workflow_run_attempt === judge.kms_outcome_authority.workflow_attempt
      && kmsAuthority.aws.verifier_key_count === 2
      && kmsAuthority.aws.kms_sign_calls === 4
      && kmsAuthority.aws.kms_get_public_key_calls === 2
      && kmsAuthority.aws.s3_head_get_lookups === 4
      && kmsAuthority.aws.action_worker_kms_sign_denied === true
      && kmsAuthority.cockroachdb.migration_version === 38
      && kmsAuthority.cockroachdb.canonical_memory_rows === 3
      && kmsAuthority.attestation.raw_handle_persisted === false
      && kmsAuthority.lifecycle.authority_epochs.join(',') === '1,2,3'
      && kmsAuthority.lifecycle.restart_verified_offline === true
      && kmsAuthority.lifecycle.old_handle_replayed_without_resigning === true
      && kmsAuthority.lifecycle.private_handoff_objects_remaining === 0
      && kmsAuthorityReleaseAsset?.digest === `sha256:${judge.kms_outcome_authority.public_sha256}`;
    const providerOriginPassed = providerOriginStory.gate.status === 'PASS'
      && providerOriginStory.receipt_sha256 === judge.provider_origin_story.story_receipt_sha256
      && providerOriginStory.source_release.tag === judge.provider_origin_story.source_release_tag
      && providerOriginStory.source_release.target === judge.provider_origin_story.source_release_target
      && judge.provider_origin_story.video_url === judge.submission.video_url
      && judge.provider_origin_story.video_sha256 === judge.submission.video_sha256
      && judge.provider_origin_story.caption_delivery.mode === 'burned-in'
      && judge.provider_origin_story.caption_delivery.publicly_verifiable === true
      && judge.provider_origin_story.devpost.project_version === judge.submission.project_version
      && providerOriginStoryReleaseAsset?.digest === `sha256:${judge.provider_origin_story.public_sha256}`;
    const allPassed = passed && guardianPassed && blindPassed && sequentialPassed && ciRecoveryPassed && adaptivePassed && transferPassed && onlinePassed && outcomeCasPassed && kmsAuthorityPassed && providerOriginPassed;
    result.textContent = allPassed ? 'PASS · public evidence, online CockroachDB lineage, and live health agree.' : 'HOLD · open the full verifier for details.';
    byId('proof-status').textContent = allPassed ? 'ALL PUBLIC GATES PASS' : 'HOLD';
  } catch (error) {
    result.textContent = 'HOLD · public verification is temporarily unavailable.';
    byId('proof-status').textContent = 'HOLD';
    console.error(error);
  } finally {
    button.disabled = false;
  }
}

Promise.all([json(judgeUrl), json(scaleUrl), json(pressureUrl), json(guardianUrl), json(blindUrl), json(sequentialUrl), json(ciRecoveryUrl), json(adaptiveDiagnosisUrl), json(transferFirewallUrl), json(onlineMemoryLineageUrl), json(outcomeReplayCasUrl), json(kmsAuthorityUrl)])
  .then(([judge, scale, pressure, guardian, blind, sequential, ciRecovery, adaptive, transfer, online, outcomeCas, kmsAuthority]) => {
    renderJudge(judge);
    renderScale(scale);
    renderPressure(pressure);
    renderGuardian(guardian);
    renderBlind(blind);
    renderSequential(sequential);
    renderCIRecovery(ciRecovery);
    renderAdaptiveDiagnosis(adaptive);
    renderTransferFirewall(transfer);
    renderOnlineMemoryLineage(online);
    renderOutcomeReplayCas(outcomeCas);
    renderKmsAuthority(kmsAuthority);
    renderJudgeClosure(sequential, outcomeCas);
  })
  .catch(error => { byId('proof-status').textContent = 'EVIDENCE HOLD'; console.error(error); });
byId('quick-check').addEventListener('click', quickCheck);
byId('run-story').addEventListener('click', runStory);
