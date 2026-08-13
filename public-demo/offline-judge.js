/* Quota-independent judge verification.  Every fetch is same-origin. */
(function () {
  'use strict';

  const button = document.querySelector('#run');
  const paths = {
    judge: './evidence/judge-verification.json',
    capsule: './evidence/judge-offline-capsule-v1.json',
    envelope: './evidence/continuum-release-envelope-v2.json',
    authorBundle: './evidence/continuum-release-envelope-v2.sigstore.jsonl',
    networkBundle: './evidence/continuum-release-envelope-v2.network-attestations.jsonl',
    transaction: './evidence/release-transaction-receipt.json',
    providerStory: './evidence/provider-origin-story-v1.json'
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
      const [judgeBytes, capsuleBytes, envelopeBytes, authorBytes, networkBytes, transactionBytes, providerStoryBytes] = await Promise.all([
        bytes(paths.judge), bytes(paths.capsule), bytes(paths.envelope), bytes(paths.authorBundle), bytes(paths.networkBundle), bytes(paths.transaction), bytes(paths.providerStory)
      ]);
      const judge = json(judgeBytes);
      const capsule = json(capsuleBytes);
      const envelope = json(envelopeBytes);
      const authorBundles = lines(authorBytes);
      const networkBundles = lines(networkBytes);
      const transaction = json(transactionBytes);
      const providerStory = json(providerStoryBytes);
      const capsuleSha = await rawSha(capsuleBytes);
      const envelopeSha = await rawSha(envelopeBytes);
      const authorSha = await rawSha(authorBytes);
      const networkSha = await rawSha(networkBytes);
      const providerStorySha = await rawSha(normalizedTextBytes(providerStoryBytes));
      const capsuleReceiptValid = capsule.receipt_sha256 === await selfHash(capsule);
      const transactionReceiptValid = transaction.receipt_sha256 === await selfHash(transaction);
      const providerStoryReceiptValid = providerStory.receipt_sha256 === await providerStoryReceiptHash(providerStory);
      const capsuleChecks = capsule.online_verification?.checks || {};
      const uiChecks = capsule.ui_checks || {};
      const allOnlineChecks = Object.keys(capsuleChecks).length === capsule.online_verification?.check_count && Object.values(capsuleChecks).every(value => value === true);
      const predecessorUiNames = Object.keys(labels).filter(name => name !== 'providerOriginStory');
      const allUiChecks = Object.keys(uiChecks).length === predecessorUiNames.length && predecessorUiNames.every(name => uiChecks[name] === true) && !Object.hasOwn(uiChecks, 'providerOriginStory');
      const offlinePolicy = capsule.request_policy?.judge_click_github_api_requests === 0 && capsule.request_policy?.judge_click_credentials_required === false && capsule.request_policy?.same_origin_static_gets_only === true;
      const capsuleReference = envelope.offline_judge_capsule || {};
      const envelopeBound = capsuleReference.asset_name === 'judge-offline-capsule-v1.json' && capsuleReference.asset_sha256 === capsuleSha && capsuleReference.receipt_sha256 === capsule.receipt_sha256 && envelope.release?.commit_sha === capsule.compiler?.source_head && envelope.release?.tag === capsule.compiler?.successor_release_tag && envelope.public_judge_evidence?.schema_version === judge.schema_version && envelope.gates?.status === 'PASS';
      const events = transaction.events || [];
      const authorEvent = events.find(event => event.state === 'AUTHOR_ATTESTED')?.evidence || {};
      const terminal = events.at(-1)?.evidence || {};
      const transactionBound = transactionReceiptValid && transaction.state === 'PAGES_MATERIALIZED' && transaction.release_tag === envelope.release?.tag && transaction.source_digest === envelope.release?.commit_sha && transaction.envelope_sha256 === envelopeSha && events.map(event => event.state).join('|') === 'PREPARED|AUTHOR_ATTESTED|ASSETS_UPLOADED|IMMUTABLE|PAGES_MATERIALIZED' && terminal.public_bundle_sha256 === networkSha && terminal.offline_judge_capsule_sha256 === capsuleSha && terminal.offline_judge_capsule_receipt_sha256 === capsule.receipt_sha256;
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
      const capsuleGate = capsule.schema_version === 1 && capsule.kind === 'continuum.offline-judge-capsule.v1' && capsuleReceiptValid && capsule.online_verification?.ok === true && allOnlineChecks && allUiChecks && offlinePolicy && capsule.gate?.status === 'PASS' && Object.values(capsule.gate?.checks || {}).every(value => value === true);
      const core = capsuleGate && envelopeBound && provenanceBound && transactionBound && providerStoryBound;
      const values = {...uiChecks};
      values.bundle = Boolean(values.bundle && capsuleGate && envelopeBound);
      values.pages = Boolean(values.pages && transactionBound);
      values.release = Boolean(values.release && envelopeBound && transactionBound);
      values.provenance = Boolean(values.provenance && provenanceBound);
      values.transaction = Boolean(values.transaction && transactionBound);
      values.providerOriginStory = providerStoryBound;
      setChecks(values);
      const passed = core && Object.values(values).every(value => value === true);
      button.textContent = passed ? 'PASS · 0 GitHub API requests' : 'Offline verification failed';
      window.__continuumOfflineVerification = {
        ok: passed,
        status: passed ? 'PASS' : 'FAIL',
        github_api_requests: 0,
        same_origin_static_gets: 7,
        capsule_sha256: capsuleSha,
        capsule_receipt_sha256: capsule.receipt_sha256,
        envelope_sha256: envelopeSha,
        release_tag: envelope.release?.tag,
        release_target: envelope.release?.commit_sha,
        predecessor_release_tag: capsule.predecessor?.release_tag,
        predecessor_online_check_count: capsule.online_verification?.check_count,
        current_delivery_check_count: capsuleChecks.provider_origin_story_delivery === true ? 0 : 1,
        effective_check_count: Number(capsule.online_verification?.check_count || 0) + (capsuleChecks.provider_origin_story_delivery === true ? 0 : 1),
        ui_check_count: Object.keys(values).length
      };
      if (!passed) console.error('one or more offline judge gates failed');
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
