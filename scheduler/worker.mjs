const DISPATCH_URL = 'https://api.github.com/repos/AcerMo/Team-Balance-Panel/actions/workflows/publish.yml/dispatches';

export default {
  scheduled(_event, env, context) {
    context.waitUntil(dispatch(env.GITHUB_ACTIONS_TOKEN));
  },
};

export async function dispatch(token) {
  if (!token) throw new Error('GITHUB_ACTIONS_TOKEN is missing');

  const response = await fetch(DISPATCH_URL, {
    method: 'POST',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': 'team-balance-scheduler',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify({ref: 'main'}),
  });

  if (response.status !== 204) {
    throw new Error(`GitHub workflow dispatch failed with HTTP ${response.status}`);
  }
}
