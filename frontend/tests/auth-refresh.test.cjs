// Run with: node --test tests/auth-refresh.test.cjs
// Exercise the actual API client in isolated tabs with controlled HTTP responses.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/api.ts'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const ok = (value = {}) => Response.json(value);
const failure = status => Response.json({detail: 'Test failure'}, {status});
const user = {user: {id: 'one'}, settings: {}};
function tab(fetch, locks) {
  const exports = {}, events = [];
  vm.runInNewContext(source, {exports, process: {env: {}}, fetch, AbortSignal, URLSearchParams, Event,
    navigator: {locks}, window: {dispatchEvent: event => events.push(event.type)}});
  return {api: exports, events};
}
function sharedLocks() {
  let tail = Promise.resolve();
  return {request: (_name, operation) => {
    const result = tail.then(operation);
    tail = result.catch(() => {});
    return result;
  }};
}

test('an expired access cookie renews and retries exactly the original lesson command', async () => {
  let renewed = false, refreshes = 0;
  const commands = [];
  const {api} = tab(async (url, init) => {
    assert.equal(init.credentials, 'include');
    if (url.endsWith('/auth/session')) return failure(401);
    if (url.endsWith('/auth/refresh')) {refreshes++; renewed = true; return ok(user);}
    commands.push(init.body);
    return renewed ? ok({saved: true}) : failure(401);
  });
  const command = JSON.stringify({action:'answer',step_id:'recall',revision:32,answer:'ねこ'});
  assert.equal((await api.request('/lessons/long/progress', {method:'POST',body:command})).saved, true);
  assert.deepEqual(commands, [command, command]);
  assert.equal(refreshes, 1);
});

test('simultaneous requests share one renewal, including a late 401', async () => {
  let renewed = false, refreshes = 0, releaseLate;
  const attempts = new Map();
  const {api} = tab(async url => {
    if (url.endsWith('/auth/session')) return renewed ? ok(user) : failure(401);
    if (url.endsWith('/auth/refresh')) {refreshes++; renewed = true; return ok(user);}
    const count = (attempts.get(url) || 0) + 1; attempts.set(url, count);
    if (url.endsWith('/late') && count === 1) return new Promise(resolve => {releaseLate = () => resolve(failure(401));});
    return renewed ? ok() : failure(401);
  });
  const late = api.request('/late');
  await Promise.all([api.request('/one'), api.request('/two'), api.request('/three')]);
  releaseLate(); await late;
  assert.equal(refreshes, 1);
  assert.equal([...attempts.values()].every(value => value === 2), true);
});

test('two tabs serialize renewal and probe the shared cookie under the lock', async () => {
  let renewed = false, refreshes = 0;
  const fetch = async url => {
    if (url.endsWith('/auth/refresh')) {assert.equal(renewed, false);refreshes++;renewed = true;return ok(user);}
    return renewed ? ok(user) : failure(401);
  };
  const locks = sharedLocks();
  const first = tab(fetch, locks), second = tab(fetch, locks);
  await Promise.all([first.api.request('/lessons/one'), second.api.request('/lessons/two')]);
  assert.equal(refreshes, 1);
});

test('network errors and server failures never replay a possibly accepted write', async () => {
  for (const result of [() => {throw new TypeError('offline');}, () => failure(503)]) {
    let calls = 0;
    const {api, events} = tab(async () => {calls++;return result();});
    await assert.rejects(api.request('/lessons/one/progress', {method:'POST',body:'{}'}));
    assert.equal(calls, 1);assert.deepEqual(events, []);
  }
});

test('a temporary refresh failure preserves the known session instead of signing out', async () => {
  let expired = false;
  const {api, events} = tab(async url => {
    if (url.endsWith('/auth/refresh')) return failure(503);
    return expired ? failure(401) : ok(user);
  });
  await api.session();expired = true;
  await assert.rejects(api.session(), error => error.status === 503);
  assert.deepEqual(events, []);
});

test('a truly expired session requests inline login without replacing cached session with null', async () => {
  let expired = false;
  const {api, events} = tab(async () => expired ? failure(401) : ok(user));
  await api.session();expired = true;
  await assert.rejects(api.session(), error => error.status === 401);
  assert.deepEqual(events, [api.AUTH_EXPIRED_EVENT]);
  const anonymous = tab(async () => failure(401));
  assert.equal(await anonymous.api.session(), null);
});

test('invalid credentials do not trigger refresh; a repeated protected 401 retries only once', async () => {
  const calls = [];
  const {api, events} = tab(async url => {calls.push(url);return url.endsWith('/auth/refresh') ? ok(user) : failure(401);});
  await assert.rejects(api.login('me@example.com', 'wrong'), error => error.status === 401);
  assert.equal(calls.length, 1);assert.deepEqual(events, []);
  await assert.rejects(api.request('/lessons/one'), error => error.status === 401);
  assert.equal(calls.filter(url => url.endsWith('/lessons/one')).length, 2);
  assert.equal(calls.filter(url => url.endsWith('/auth/refresh')).length, 1);
});

test('a deliberate logout prevents an old failed request from being resubmitted', async () => {
  let release, calls = 0;
  const {api} = tab(async url => {
    if (url.endsWith('/auth/logout')) return ok({ok:true});
    calls++;
    return new Promise(resolve => {release = () => resolve(failure(401));});
  });
  const pending = api.request('/lessons/one/progress', {method:'POST',body:'{}'});
  await api.logout();release();
  await assert.rejects(pending, error => error.status === 409);
  assert.equal(calls, 1);
});

test('a different account in another tab cannot receive the old pending write', async () => {
  let switched = false, writes = 0;
  const {api, events} = tab(async url => {
    if (url.endsWith('/auth/session')) return ok(switched ? {user:{id:'two'},settings:{}} : user);
    writes++;return failure(401);
  });
  await api.session();switched = true;
  await assert.rejects(api.request('/users/me/settings', {method:'PUT',body:'{}'}), error => error.status === 401);
  assert.equal(writes, 1);
  assert.deepEqual(events, [api.AUTH_EXPIRED_EVENT]);
});
