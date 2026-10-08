import assert from 'node:assert/strict';
import {afterEach, test, mock} from 'node:test';
import worker, {dispatch} from './worker.mjs';

afterEach(() => mock.restoreAll());

test('scheduled event dispatches the publishing workflow', async () => {
  let pending;
  const fetchMock = mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://api.github.com/repos/AcerMo/Team-Balance-Panel/actions/workflows/publish.yml/dispatches');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    assert.deepEqual(JSON.parse(options.body), {ref: 'main'});
    return {status: 204};
  });

  worker.scheduled({}, {GITHUB_ACTIONS_TOKEN: 'test-token'}, {
    waitUntil(promise) { pending = promise; },
  });
  await pending;
  assert.equal(fetchMock.mock.callCount(), 1);
});

test('GitHub rejection fails the scheduled invocation without exposing the token', async () => {
  mock.method(globalThis, 'fetch', async () => ({status: 403}));
  await assert.rejects(dispatch('test-token'), error =>
    error.message === 'GitHub workflow dispatch failed with HTTP 403');
});

test('a missing token does not call GitHub', async () => {
  const fetchMock = mock.method(globalThis, 'fetch');
  await assert.rejects(dispatch(), /GITHUB_ACTIONS_TOKEN is missing/);
  assert.equal(fetchMock.mock.callCount(), 0);
});
