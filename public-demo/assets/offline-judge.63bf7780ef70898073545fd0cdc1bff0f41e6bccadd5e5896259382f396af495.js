/* Quota-independent judge verification.  Every fetch is same-origin. */
(function () {
  'use strict';

  const button = document.querySelector('#run');
  const runtimeScript = document.currentScript;
  const paths = {
    judge: './evidence/judge-verification.json',
    capsule: './evidence/judge-offline-capsule-v1.json',
    envelope: './evidence/continuum-release-envelope-v2.json',
    authorBundle: './evidence/continuum-release-envelope-v2.sigstore.jsonl',
    networkBundle: './evidence/continuum-release-envelope-v2.network-attestations.jsonl',
    transaction: './evidence/release-transaction-receipt.json',
    providerStory: './evidence/provider-origin-story-v1.json',
    kmsAuthority: './evidence/kms-authority-lifecycle-v1.json'
  };

  async function bytes(path) {
    const response = await fetch(path, {cache: 'no-store', credentials: 'omit'});
    if (!response.ok) throw new Error(path + ' returned HTTP ' + response.status);
    return new Uint8Array(await response.arrayBuffer());
  }

  function json(value) {
    const parsed = JSON.parse(new TextDecoder().decode(value));
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error('expected a JSON object');
    }
    return parsed;
  }

  function lines(value) {
    return new TextDecoder().decode(value).split(/\r?\n/).filter(Boolean).map(JSON.parse);
  }

  function statement(bundle) {
    const payload = bundle?.dsseEnvelope?.payload;
    if (!payload) throw new Error('Sigstore bundle omitted its DSSE payload');
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(payload), character => character.charCodeAt(0))));
  }

  function same(left, right) {
    return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
  }

  async function rawSha(value) {
    return sha256Hex(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
  }

  async function selfHash(value) {
    const body = {...value};
    delete body.receipt_sha256;
    return sha256Json(body);
  }

  async function providerStoryReceiptHash(value) {
    const body = {...value};
    delete body.receipt_sha256;
    const canonicalWithLf = JSON.stringify(canonical(body)) + '\n';
    return sha256Hex(new TextEncoder().encode(canonicalWithLf).buffer);
  }

  async function runOffline() {
    button.disabled = true;
    button.textContent = 'Verifying static capsule…';
    setChecks();
    window.__continuumOfflineVerification = {ok: false, status: 'RUNNING'};
    try {
      const [judgeBytes, capsuleBytes, envelopeBytes, authorBytes, networkBytes, transactionBytes, providerStoryBytes, kmsAuthorityBytes] = await Promise.all([
        bytes(paths.judge), bytes(paths.capsule), bytes(paths.envelope), bytes(paths.authorBundle), bytes(paths.networkBundle), bytes(paths.transaction), bytes(paths.providerStory), bytes(paths.kmsAuthority)
      ]);
      const judge = json(judgeBytes);
      const capsule = json(capsuleBytes);
      const envelope = json(envelopeBytes);
      const authorBundles = lines(authorBytes);
      const networkBundles = lines(networkBytes);
      const transaction = json(transactionBytes);
      const providerStory = json(providerStoryBytes);
      const kmsAuthority = json(kmsAuthorityBytes);
      const capsuleSha = await rawSha(capsuleBytes);
      const envelopeSha = await rawSha(envelopeBytes);
      const authorSha = await rawSha(authorBytes);
      const networkSha = await rawSha(networkBytes);
      const providerStorySha = await rawSha(normalizedTextBytes(providerStoryBytes));
      const kmsAuthoritySha = await rawSha(normalizedTextBytes(kmsAuthorityBytes));
      const capsuleReceiptValid = capsule.receipt_sha256 === await selfHash(capsule);
      const transactionReceiptValid = transaction.receipt_sha256 === await selfHash(transaction);
      const providerStoryReceiptValid = providerStory.receipt_sha256 === await providerStoryReceiptHash(providerStory);
      const kmsAuthorityReceiptValid = kmsAuthority.receipt_sha256 === await selfHash(kmsAuthority);
      const capsuleChecks = capsule.online_verification?.checks || {};
      const uiChecks = capsule.ui_checks || {};
      const allOnlineChecks = Object.keys(capsuleChecks).length === capsule.online_verification?.check_count && Object.values(capsuleChecks).every(value => value === true);
      const currentDeliveryNames = new Set(['providerOriginStory', 'kmsAuthority']);
      const predecessorUiNames = Object.keys(labels).filter(name => !currentDeliveryNames.has(name));
      const allUiChecks = Object.keys(uiChecks).length === predecessorUiNames.length && predecessorUiNames.every(name => uiChecks[name] === true) && [...currentDeliveryNames].every(name => !Object.hasOwn(uiChecks, name));
      const offlinePolicy = capsule.request_policy?.judge_click_github_api_requests === 0 && capsule.request_policy?.judge_click_credentials_required === false && capsule.request_policy?.same_origin_static_gets_only === true;
      const capsuleReference = envelope.offline_judge_capsule || {};
      const relayRef = judge.offline_judge_capsule?.relay || {};
      const relayEvidence = capsule.relay || {};
      const relayBound = relayRef.enabled !== true || (relayRef.schema_version === 1 && relayRef.reason === 'preserved_candidate_browser_failure' && relayRef.source_release_immutable === true && relayRef.failed_pages_conclusion === 'failure' && relayEvidence.schema_version === 1 && relayEvidence.reason === relayRef.reason && relayEvidence.source_release_tag === relayRef.source_release_tag && relayEvidence.source_release_target === relayRef.source_release_target && relayEvidence.source_asset_sha256 === relayRef.source_asset_sha256 && relayEvidence.source_receipt_sha256 === relayRef.source_receipt_sha256 && relayEvidence.source_compiler_workflow_run_id === relayRef.source_compiler_workflow_run_id && relayEvidence.failed_pages_workflow_run_id === relayRef.failed_pages_workflow_run_id && relayEvidence.failed_epoch_promoted_to_pass === false && capsule.predecessor?.release_tag === relayRef.source_predecessor_release_tag && same(capsuleReference.relay, relayEvidence));
      const envelopeBound = capsuleReference.asset_name === 'judge-offline-capsule-v1.json' && capsuleReference.asset_sha256 === capsuleSha && capsuleReference.receipt_sha256 === capsule.receipt_sha256 && envelope.release?.commit_sha === capsule.compiler?.source_head && envelope.release?.tag === capsule.compiler?.successor_release_tag && envelope.public_judge_evidence?.schema_version === judge.schema_version && envelope.gates?.status === 'PASS' && relayBound;
      const events = transaction.events || [];
      const authorEvent = events.find(event => event.state === 'AUTHOR_ATTESTED')?.evidence || {};
      const pagesEvent = events.find(event => event.state === 'PAGES_MATERIALIZED');
      const pagesEvidence = pagesEvent?.evidence || {};
      const browserEvent = events.find(event => event.state === 'BROWSER_VERIFIED');
      const browserEvidence = browserEvent?.evidence || {};
      const stateSequence = events.map(event => event.state).join('|');
      const pagesSequence = 'PREPARED|AUTHOR_ATTESTED|ASSETS_UPLOADED|IMMUTABLE|PAGES_MATERIALIZED';
      const browserSequence = pagesSequence + '|BROWSER_VERIFIED';
      const pagesBound = transactionReceiptValid && transaction.release_tag === envelope.release?.tag && transaction.source_digest === envelope.release?.commit_sha && transaction.envelope_sha256 === envelopeSha && pagesEvidence.public_bundle_sha256 === networkSha && pagesEvidence.offline_judge_capsule_sha256 === capsuleSha && pagesEvidence.offline_judge_capsule_receipt_sha256 === capsule.receipt_sha256;
      const browserRef = judge.browser_verification || {};
      const browserEnvelope = envelope.browser_verification || {};
      const scriptUrl = new URL(runtimeScript?.src || '', window.location.href);
      const assetMarker = '/continuum-memory-firewall/';
      const markerIndex = scriptUrl.pathname.indexOf(assetMarker);
      const runtimeAssetName = markerIndex >= 0 ? scriptUrl.pathname.slice(markerIndex + assetMarker.length) : scriptUrl.pathname.replace(/^\//, '');
      const scriptDeliveryBound = judge.schema_version < 18 || (browserRef.schema_version === 1 && same(browserEnvelope, browserRef) && runtimeAssetName === browserRef.script_asset_name && runtimeScript?.integrity === browserRef.script_integrity && runtimeScript?.crossOrigin === 'anonymous' && browserRef.script_asset_name === 'assets/offline-judge.' + browserRef.script_sha256 + '.js' && browserRef.required_terminal_state === 'BROWSER_VERIFIED' && browserRef.required_ui_check_count === 39 && browserRef.required_github_api_requests === 0 && browserRef.required_console_errors === 0 && browserRef.fresh_context_required === true);
      const browserBound = judge.schema_version < 18 || (browserEvidence.status === 'success' && browserEvidence.browser_workflow_run_id === pagesEvidence.pages_workflow_run_id && browserEvidence.browser_workflow_url === pagesEvidence.pages_workflow_url && browserEvidence.browser_source_digest === envelope.release?.commit_sha && browserEvidence.browser_artifact_name === 'browser-verification-candidate-' + browserEvidence.browser_workflow_run_id && /^sha256:[0-9a-f]{64}$/.test(browserEvidence.browser_artifact_digest || '') && /^[0-9a-f]{64}$/.test(browserEvidence.browser_receipt_sha256 || '') && browserEvidence.browser_context_fresh === true && browserEvidence.browser_engine === 'chromium' && browserEvidence.headless === true && browserEvidence.candidate_status === 'CANDIDATE_PASS' && browserEvidence.candidate_transaction_state === 'PAGES_MATERIALIZED' && browserEvidence.ui_check_count === 39 && browserEvidence.github_api_requests === 0 && browserEvidence.console_error_count === 0 && browserEvidence.script_asset_name === browserRef.script_asset_name && browserEvidence.script_sha256 === browserRef.script_sha256 && browserEvidence.script_integrity === browserRef.script_integrity && browserEvidence.pages_receipt_sha256 === transaction.previous_receipt_sha256 && browserEvidence.release_tag === envelope.release?.tag && browserEvidence.release_target === envelope.release?.commit_sha);
      const candidateTransactionBound = transaction.state === 'PAGES_MATERIALIZED' && stateSequence === pagesSequence && pagesBound;
      const finalTransactionBound = transaction.state === 'BROWSER_VERIFIED' && stateSequence === browserSequence && pagesBound && browserBound;
      const transactionBound = judge.schema_version < 18 ? candidateTransactionBound : (candidateTransactionBound || finalTransactionBound);
      const terminalReady = judge.schema_version < 18 ? candidateTransactionBound : finalTransactionBound;
      const authorBundle = authorBundles.length === 1 ? authorBundles[0] : null;
      const authorStatement = authorBundle ? statement(authorBundle) : {};
      const networkStatements = networkBundles.map(statement);
      const authorIndexes = networkStatements.map((value, index) => ({value, index})).filter(item => item.value?.predicateType === judge.network_sign_once?.author_predicate_type && item.value?.subject?.some(subject => subject.name === judge.network_sign_once?.subject_name && subject.digest?.sha256 === envelopeSha));
      const releaseUri = 'pkg:github/' + judge.source.repository + '@' + envelope.release?.tag;
      const platformIndexes = networkStatements.map((value, index) => ({value, index})).filter(item => item.value?.predicateType === judge.network_sign_once?.platform_predicate_type && item.value?.subject?.some(subject => subject.name === judge.network_sign_once?.subject_name && subject.digest?.sha256 === envelopeSha) && item.value?.subject?.some(subject => subject.uri === releaseUri && subject.digest?.sha1 === envelope.release?.commit_sha));
      const authorMaterial = Boolean(authorBundle?.verificationMaterial?.certificate?.rawBytes) && authorBundle?.verificationMaterial?.tlogEntries?.length === 1;
      const platformBundle = networkBundles[platformIndexes[0]?.index];
      const platformMaterial = Boolean(platformBundle?.verificationMaterial?.certificate?.rawBytes) && (platformBundle?.verificationMaterial?.timestampVerificationData?.rfc3161Timestamps?.length || 0) >= 1;
      const provenanceBound = authorBundles.length === 1 && networkBundles.length === 2 && authorIndexes.length === 1 && platformIndexes.length === 1 && same(authorBundle, networkBundles[authorIndexes[0].index]) && authorStatement?.subject?.some(subject => subject.name === judge.network_sign_once?.subject_name && subject.digest?.sha256 === envelopeSha) && authorEvent.author_bundle_sha256 === authorSha && authorMaterial && platformMaterial;
      const providerRef = judge.provider_origin_story || {};
      const providerEnvelope = envelope.provider_origin_story || {};
      const caption = providerRef.caption_delivery || {};
      const devpost = providerRef.devpost || {};
      const providerStoryBound = judge.schema_version >= 17 && providerStoryReceiptValid && providerStorySha === providerRef.public_sha256 && providerStory.receipt_sha256 === providerRef.story_receipt_sha256 && providerStory.schema_version === 1 && providerStory.kind === 'continuum.provider-origin-video-story' && providerStory.gate?.status === 'PASS' && Object.values(providerStory.gate?.checks || {}).every(value => value === true) && providerStory.story?.scenes?.length === 9 && providerStory.source_release?.tag === providerRef.source_release_tag && providerStory.source_release?.target === providerRef.source_release_target && providerStory.source_release?.envelope_sha256 === providerRef.source_release_envelope_sha256 && providerRef.video_url === judge.submission?.video_url && providerRef.video_sha256 === judge.submission?.video_sha256 && providerRef.video_duration_seconds === judge.submission?.video_duration_seconds && providerRef.subtitles_sha256 === judge.submission?.video_subtitles_sha256 && ['youtube-cc', 'burned-in'].includes(caption.mode) && caption.language === 'en-US' && caption.publicly_verifiable === true && devpost.project_version === judge.submission?.project_version && devpost.project_updated_at === judge.submission?.project_updated_at && devpost.submission_id === judge.submission?.id && devpost.submitted_at === judge.submission?.submitted_at && providerEnvelope.public_sha256 === providerRef.public_sha256 && providerEnvelope.receipt_sha256 === providerRef.story_receipt_sha256 && providerEnvelope.immutable_release_asset_url === judge.release_envelope?.provider_origin_story_asset_url && same(providerEnvelope.source_release, providerStory.source_release) && providerEnvelope.video?.url === providerRef.video_url && providerEnvelope.video?.sha256 === providerRef.video_sha256 && providerEnvelope.video?.subtitles_sha256 === providerRef.subtitles_sha256 && same(providerEnvelope.video?.caption_delivery, caption) && same(providerEnvelope.devpost, devpost) && providerEnvelope.gate?.status === 'PASS';
      const kmsRef = judge.kms_outcome_authority || {};
      const kmsEnvelope = envelope.kms_outcome_authority || {};
      const kmsChecks = Object.values(kmsAuthority.gate?.checks || {});
      const kmsAuthorityBound = judge.schema_version >= 19 && kmsAuthorityReceiptValid && kmsAuthoritySha === kmsRef.public_sha256 && kmsAuthority.receipt_sha256 === kmsRef.receipt_sha256 && kmsAuthority.schema_version === 1 && kmsAuthority.kind === 'continuum.kms-outcome-authority-lifecycle' && kmsAuthority.source?.head === kmsRef.head_sha && kmsAuthority.source?.workflow_run_id === kmsRef.workflow_run_id && kmsAuthority.source?.workflow_run_attempt === kmsRef.workflow_attempt && kmsAuthority.source?.deployment_artifact_sha256 === kmsRef.deployment_artifact_sha256 && kmsAuthority.aws?.region === 'ap-southeast-1' && kmsAuthority.aws?.key_spec === 'ECC_NIST_P256' && kmsAuthority.aws?.signing_algorithm === 'ECDSA_SHA_256' && kmsAuthority.aws?.verifier_key_count === 2 && kmsAuthority.aws?.kms_sign_calls === 4 && kmsAuthority.aws?.kms_get_public_key_calls === 2 && kmsAuthority.aws?.s3_head_get_lookups === 4 && kmsAuthority.aws?.action_worker_kms_sign_denied === true && kmsAuthority.cockroachdb?.migration_version === 38 && kmsAuthority.cockroachdb?.canonical_memory_rows === 3 && kmsAuthority.cockroachdb?.runtime_attestation_insert_sqlstate === '42501' && kmsAuthority.attestation?.raw_handle_persisted === false && kmsAuthority.lifecycle?.authority_epochs?.join(',') === '1,2,3' && kmsAuthority.lifecycle?.restart_verified_offline === true && kmsAuthority.lifecycle?.old_handle_replayed_without_resigning === true && kmsAuthority.lifecycle?.private_handoff_objects_remaining === 0 && kmsAuthority.gate?.status === 'PASS' && kmsChecks.length === 18 && kmsChecks.every(value => value === true) && kmsEnvelope.public_sha256 === kmsRef.public_sha256 && kmsEnvelope.receipt_sha256 === kmsRef.receipt_sha256 && kmsEnvelope.workflow_run_id === kmsRef.workflow_run_id && kmsEnvelope.workflow_attempt === kmsRef.workflow_attempt && kmsEnvelope.head_sha === kmsRef.head_sha && kmsEnvelope.artifact_id === kmsRef.artifact_id && kmsEnvelope.artifact_name === kmsRef.artifact_name && kmsEnvelope.artifact_archive_sha256 === kmsRef.artifact_archive_sha256 && kmsEnvelope.immutable_release_asset_url === judge.release_envelope?.kms_outcome_authority_asset_url && kmsEnvelope.gate?.status === 'PASS';
      const capsuleGate = capsule.schema_version === 1 && capsule.kind === 'continuum.offline-judge-capsule.v1' && capsuleReceiptValid && capsule.online_verification?.ok === true && allOnlineChecks && allUiChecks && offlinePolicy && relayBound && capsule.gate?.status === 'PASS' && Object.values(capsule.gate?.checks || {}).every(value => value === true);
      const core = capsuleGate && envelopeBound && provenanceBound && transactionBound && providerStoryBound && kmsAuthorityBound && scriptDeliveryBound;
      const values = {...uiChecks};
      values.bundle = Boolean(values.bundle && capsuleGate && envelopeBound);
      values.pages = Boolean(values.pages && transactionBound);
      values.release = Boolean(values.release && envelopeBound && transactionBound);
      values.provenance = Boolean(values.provenance && provenanceBound);
      values.transaction = Boolean(values.transaction && transactionBound);
      values.providerOriginStory = providerStoryBound;
      values.kmsAuthority = kmsAuthorityBound;
      setChecks(values);
      const candidatePassed = core && Object.values(values).every(value => value === true);
      const passed = candidatePassed && terminalReady;
      button.textContent = passed ? 'PASS · browser verified · 0 GitHub API requests' : candidatePassed ? 'CANDIDATE PASS · awaiting browser receipt' : 'Offline verification failed';
      window.__continuumOfflineVerification = {
        ok: passed,
        candidate_ok: candidatePassed,
        status: passed ? 'PASS' : candidatePassed ? 'CANDIDATE_PASS' : 'FAIL',
        github_api_requests: 0,
        same_origin_static_gets: 8,
        capsule_sha256: capsuleSha,
        capsule_receipt_sha256: capsule.receipt_sha256,
        envelope_sha256: envelopeSha,
        release_tag: envelope.release?.tag,
        release_target: envelope.release?.commit_sha,
        release_transaction_state: transaction.state,
        transaction_receipt_sha256: transaction.receipt_sha256,
        script_asset_name: browserRef.script_asset_name,
        script_sha256: browserRef.script_sha256,
        script_integrity: browserRef.script_integrity,
        browser_artifact_digest: browserEvidence.browser_artifact_digest || null,
        predecessor_release_tag: capsule.predecessor?.release_tag,
        predecessor_online_check_count: capsule.online_verification?.check_count,
        current_delivery_check_count: (capsuleChecks.provider_origin_story_delivery === true ? 0 : 1) + (capsuleChecks.kms_outcome_authority_closure === true ? 0 : 1),
        effective_check_count: Number(capsule.online_verification?.check_count || 0) + (capsuleChecks.provider_origin_story_delivery === true ? 0 : 1) + (capsuleChecks.kms_outcome_authority_closure === true ? 0 : 1),
        ui_check_count: Object.keys(values).length
      };
      if (!candidatePassed) console.error('one or more offline judge gates failed');
    } catch (error) {
      if (window.__continuumOfflineVerification?.status !== 'FAIL') setChecks();
      button.textContent = 'Offline capsule unavailable';
      window.__continuumOfflineVerification = {ok: false, status: 'HOLD', github_api_requests: 0, error: String(error)};
      console.error(error);
    } finally {
      button.disabled = false;
    }
  }

  window.__continuumOfflineVerificationInternals = Object.freeze({providerStoryReceiptHash});
  button.addEventListener('click', runOffline);
  window.runContinuumOfflineVerification = runOffline;
})();
