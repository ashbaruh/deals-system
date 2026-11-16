// dealim scheduler: Cloudflare cron -> GitHub workflow_dispatch (GitHub's own cron drops runs).
// Secret GH_TOKEN = fine-grained token, repo ashbaruh/deals-system, Actions: Read and write.
async function dispatch(env, wf, inputs = {}) {
  const r = await fetch(`https://api.github.com/repos/ashbaruh/deals-system/actions/workflows/${wf}/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json",
               "User-Agent": "dealim-scheduler", "X-GitHub-Api-Version": "2022-11-28" },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  return `${wf}: ${r.status} ${r.status === 204 ? "ok" : await r.text()}`;
}
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, "run.yml").then(console.log));
  },
  async fetch(req, env) {   // health check: open the worker URL to fire one run now
    return new Response(await dispatch(env, "run.yml"));
  },
};
