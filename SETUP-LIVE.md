# Running Precedent live: checklist and troubleshooting

The steps are in the [README](README.md#try-it). This page adds what we learned doing them on Windows 11, with Switch Console 0.40.1, switch-core 0.31.0 and Claude Code.

## Checklist

**Switch**
- [ ] Console is installed from the [`switch-console` releases](https://github.com/sandbox-quantum/switch/releases). The `switch-agent-controller` downloads are a different product.
- [ ] The server is really up. Console can show "Local server is running" when it isn't, so check that the agents respond too. If in doubt, quit Console fully and reopen it.
- [ ] Slack is connected, using an app made from Switch's manifest.
- [ ] Your Slack account is linked. The row shows your handle, not **No account linked**.
- [ ] **Run managed agents on this computer** is on.
- [ ] Claude Code is signed in. Check with `claude --version` and by running one prompt.

**Precedent**
- [ ] `uv run pytest -q` passes.
- [ ] State is created, and `init` printed `"imported_cases": 42`.
- [ ] The template is rendered, and you imported `precedent.local.template.yaml`, not `precedent.template.yaml`.
- [ ] `state/precedent.config.yaml` has your real `sender` as the approver, plus the room id and credentials path, and it's committed.

**In Slack**
- [ ] The three agents said hello in the channel.
- [ ] You're posting in the channel for the current room. If you recreate the room, Slack may keep the old channel and name the new one `precedent-approvals-<suffix>`.

## Troubleshooting

| What you see | Likely cause | What to do |
|---|---|---|
| Template form: every provider says **Not supported here** | A Windows bug in Console's provider picker, [sandbox-quantum/switch#1511](https://github.com/sandbox-quantum/switch/issues/1511) | Use our template, which sets `provider: claude` directly, and turn on managed agents |
| Provider panel says "CLI not installed", but also "Found v2.x" | Same area as above | Trust what the managed-agents controller reports; agents still ran for us |
| Agent says its instructions have `{uv}` or `{engine_dir}` unfilled | Console doesn't fill `{params}` in managed agents' instructions (`bugs.md`, Bug 5) | Import the rendered `precedent.local.template.yaml` |
| Linking fails with `missing_scope … needed: users:read` | The Slack app wasn't made from Switch's manifest | Paste `slack-manifest.json` into **App Manifest**, save, and reinstall |
| "Could not reach http://localhost:…" | The Switch server process has stopped | Quit Console fully and reopen it |
| Agent says it only takes instructions from its owner | Your Slack account isn't linked | Link it on the server's Home page |
| Exit `4`: "changed outside the engine" | The state was edited by hand | Check `git -C state status`, then commit or revert |
| Exit `3`: "reference does not match" | A stale or mistyped `#code` | Copy the newest line the agent posted |
| Exit `3`: "not an approver" | `approvers[0].id` isn't your real `sender` | Run `inspect` again and copy the exact value |
| Exit `2`: "No Switch credentials" | The config has no credentials path | Add `switch.credentials`, and commit |
| Exit `5` with a credentials or connection error | Recreating the agents gave them new ids, or the controller is down | Update the path in the config, and check the agents are running |
| `uv` not found in agent sessions | Sessions don't have it on PATH | Render with `--uv <full path to uv>` |

## Starting fresh

To reset for another run, keep the old state somewhere and create a new one, carrying over your config:
```bash
cp state/precedent.config.yaml fresh.config.yaml
```
```bash
mv state ../precedent-old-run
```
```bash
uv run precedent --home <absolute path>/state init --config fresh.config.yaml --seed seed/cases
```
```bash
rm fresh.config.yaml
```
Then, in the channel, send `!reset-all-agents`, and ask the Auditor to update the ledger document.
