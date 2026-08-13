import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) {
    throw new Error(`missing ${name}`);
  }
  return process.argv[index + 1];
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, canonical(value[key])]),
    );
  }
  return value;
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function receiptSha(value) {
  const body = {...value};
  delete body.receipt_sha256;
  return sha256(Buffer.from(JSON.stringify(canonical(body)), 'utf8'));
}

async function writeJson(file, value) {
  const encoded = Buffer.from(`${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await writeFile(file, encoded);
  return sha256(encoded);
}

const phase = argument('--phase');
const baseUrl = argument('--url').replace(/\/$/, '');
const outputDir = path.resolve(argument('--output-dir'));
if (!['candidate', 'final'].includes(phase)) {
  throw new Error('phase must be candidate or final');
}

await mkdir(outputDir, {recursive: true});
const requests = [];
const responses = new Map();
const consoleMessages = [];
const pageErrors = [];
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({
  acceptDownloads: false,
  javaScriptEnabled: true,
  serviceWorkers: 'block',
});

try {
  if ((await context.cookies()).length !== 0) {
    throw new Error('fresh browser context unexpectedly contained cookies');
  }
  const page = await context.newPage();
  page.on('request', request => {
    requests.push({
      method: request.method(),
      resource_type: request.resourceType(),
      url: request.url(),
    });
  });
  page.on('response', response => {
    responses.set(response.url(), response.status());
  });
  page.on('console', message => {
    consoleMessages.push({type: message.type(), text: message.text()});
  });
  page.on('pageerror', error => {
    pageErrors.push(String(error));
  });

  const runUrl = `${baseUrl}/verify.html?release-browser-phase=${phase}&nonce=${Date.now()}`;
  await page.goto(runUrl, {waitUntil: 'networkidle', timeout: 60_000});
  await page.locator('#run').click();
  await page.waitForFunction(
    () => !['RUNNING', undefined].includes(window.__continuumOfflineVerification?.status),
    null,
    {timeout: 60_000},
  );

  const pageResult = await page.evaluate(() => {
    const state = window.__continuumOfflineVerification;
    const script = document.querySelector('#continuum-offline-judge-script');
    return {
      state,
      rows: {
        total: document.querySelectorAll('#checks .check').length,
        pass: document.querySelectorAll('#checks .check.pass').length,
        fail: document.querySelectorAll('#checks .check.fail').length,
        waiting: document.querySelectorAll('#checks .check.waiting').length,
      },
      script: {
        src: script?.src || '',
        integrity: script?.integrity || '',
        crossorigin: script?.crossOrigin || '',
      },
      title: document.title,
    };
  });

  const expectedStatus = phase === 'candidate' ? 'CANDIDATE_PASS' : 'PASS';
  const expectedTransactionState = phase === 'candidate'
    ? 'PAGES_MATERIALIZED'
    : 'BROWSER_VERIFIED';
  const state = pageResult.state || {};
  if (state.status !== expectedStatus) {
    throw new Error(`expected ${expectedStatus}, observed ${state.status}`);
  }
  if (phase === 'candidate' && (state.candidate_ok !== true || state.ok !== false)) {
    throw new Error('candidate gate did not preserve the non-terminal boundary');
  }
  if (phase === 'final' && (state.candidate_ok !== true || state.ok !== true)) {
    throw new Error('final browser gate did not close');
  }
  if (state.release_transaction_state !== expectedTransactionState) {
    throw new Error('unexpected release transaction state');
  }
  if (
    pageResult.rows.total !== 38 ||
    pageResult.rows.pass !== 38 ||
    pageResult.rows.fail !== 0 ||
    pageResult.rows.waiting !== 0
  ) {
    throw new Error(`browser UI gate mismatch: ${JSON.stringify(pageResult.rows)}`);
  }
  if (state.github_api_requests !== 0 || state.same_origin_static_gets !== 7) {
    throw new Error('judge click violated its zero-API request contract');
  }

  const scriptUrl = new URL(pageResult.script.src);
  const assetMarker = '/continuum-memory-firewall/';
  const markerIndex = scriptUrl.pathname.indexOf(assetMarker);
  const scriptAssetName = markerIndex >= 0
    ? scriptUrl.pathname.slice(markerIndex + assetMarker.length)
    : scriptUrl.pathname.replace(/^\//, '');
  const scriptResponse = await fetch(pageResult.script.src, {cache: 'no-store'});
  if (!scriptResponse.ok) throw new Error('content-addressed script fetch failed');
  const scriptBytes = Buffer.from(await scriptResponse.arrayBuffer());
  const scriptSha = sha256(scriptBytes);
  const expectedIntegrity = `sha256-${createHash('sha256').update(scriptBytes).digest('base64')}`;
  if (
    scriptAssetName !== state.script_asset_name ||
    scriptSha !== state.script_sha256 ||
    pageResult.script.integrity !== expectedIntegrity ||
    pageResult.script.crossorigin !== 'anonymous'
  ) {
    throw new Error('content-addressed script or SRI binding failed');
  }

  const githubApiRequests = requests.filter(item => {
    try { return new URL(item.url).hostname === 'api.github.com'; }
    catch { return false; }
  });
  const consoleErrors = consoleMessages.filter(item => item.type === 'error');
  if (githubApiRequests.length !== 0 || consoleErrors.length !== 0 || pageErrors.length !== 0) {
    throw new Error('browser emitted a forbidden request or console error');
  }

  const screenshotPath = path.join(outputDir, 'browser-verification.png');
  await page.screenshot({path: screenshotPath, fullPage: true});
  const screenshotSha = sha256(await readFile(screenshotPath));
  const networkReceipt = {
    schema_version: 1,
    kind: 'continuum.browser-network-receipt',
    phase,
    requests: requests.map(item => ({...item, status: responses.get(item.url) ?? null})),
    github_api_requests: githubApiRequests.length,
  };
  const consoleReceipt = {
    schema_version: 1,
    kind: 'continuum.browser-console-receipt',
    phase,
    messages: consoleMessages,
    page_errors: pageErrors,
    error_count: consoleErrors.length + pageErrors.length,
  };
  const networkSha = await writeJson(
    path.join(outputDir, 'browser-network-receipt.json'),
    networkReceipt,
  );
  const consoleSha = await writeJson(
    path.join(outputDir, 'browser-console-receipt.json'),
    consoleReceipt,
  );
  const report = {
    schema_version: 1,
    kind: 'continuum.browser-verification-receipt',
    observed_at: new Date().toISOString(),
    phase,
    status: expectedStatus,
    public_verifier_url: `${baseUrl}/verify.html`,
    browser: {
      engine: 'chromium',
      version: browser.version(),
      headless: true,
      context_fresh: true,
      initial_cookie_count: 0,
    },
    release: {
      tag: state.release_tag,
      target: state.release_target,
      transaction_state: state.release_transaction_state,
      pages_receipt_sha256: state.transaction_receipt_sha256,
    },
    delivery: {
      script_asset_name: scriptAssetName,
      script_sha256: scriptSha,
      script_integrity: expectedIntegrity,
    },
    verification: {
      candidate_ok: state.candidate_ok,
      final_ok: state.ok,
      ui_check_count: pageResult.rows.total,
      ui_pass_count: pageResult.rows.pass,
      github_api_requests: githubApiRequests.length,
      same_origin_static_gets: state.same_origin_static_gets,
      console_error_count: consoleErrors.length + pageErrors.length,
    },
    artifacts: {
      screenshot_sha256: screenshotSha,
      network_receipt_sha256: networkSha,
      console_receipt_sha256: consoleSha,
    },
  };
  report.receipt_sha256 = receiptSha(report);
  await writeJson(path.join(outputDir, 'browser-verification-receipt.json'), report);
  process.stdout.write(`${JSON.stringify(report)}\n`);
} finally {
  await context.close();
  await browser.close();
}
