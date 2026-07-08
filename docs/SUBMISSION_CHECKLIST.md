# Devpost Submission Checklist — Slack Agent Builder Challenge

**Deadline: Monday, July 13, 2026, 5:00 PM Pacific.** (Judging: Jul 14 – Aug 6. Winners: ~Aug 11.)

**Track: New Slack Agent.** (Not "for Good" — no social-impact angle; not "for Organizations" — that requires Slack Marketplace submission from a production workspace. So: no App ID field, no impact statement, no Marketplace steps needed.)

## Required on the Devpost form

- [ ] **Devpost account + "Join Hackathon"** at slackhack.devpost.com (if not already done)
- [ ] **Track selection:** New Slack Agent
- [ ] **Text description** — features + functionality (adapt README's Problem / What It Does sections)
- [ ] **Demo video ≤ ~3 min** — footage of the working app; uploaded **public** on YouTube/Vimeo/Facebook/Youku; link on the form; no copyrighted music; English. Script: `VIDEO_SCRIPT.md`
- [ ] **Architecture diagram** — an actual visual diagram (boxes + arrows), exported as an image, uploaded via Devpost's file field. Must show: Slack surface (DM/@mention/Assistant panel) → Bolt app → Pydantic AI agent + tools → GitHub MCP + RTS + SQLite → digest flow. Explicitly NOT allowed: a text block, a bullet list, or a screenshot of AI-generated text. Tools: Excalidraw / Draw.io / Figma
- [ ] **Sandbox URL** on the form: `https://test-sandbox-slack.enterprise.slack.com/`
- [ ] **Judge access:** invite `slackhack@salesforce.com` and `testing@devpost.com` as **Members** (not guests). ⚠️ Sandboxes cap at 8 users and ship with 7 placeholder users — deactivate placeholders at the **Organization** level first (org name top-left → Tools & settings → Organization settings → People → Members → deactivate demo users), then invite. Confirm both appear in the member list before submitting.

## Before recording / before judging

- [ ] Clear seeded test rows: `DELETE FROM commitments WHERE channel_id = 'C_TEST'` in `pydantic-ai/commitments.db` (row 1 used a real message — check it too)
- [ ] Consider making `zk19604/meeting-debt-demo` **public** so the PRs judges see verified aren't in a private repo (works either way — the GITHUB_TOKEN is ours — but public looks better)
- [ ] **Keep the app process running through the entire judging period (Jul 14 – Aug 6).** Socket Mode means no public URL, but the Python process must be alive for the bot to answer judges. A laptop is not reliable for 3+ weeks — run it on an always-on box (small VPS / Railway / Fly.io worker). See README "Running It"
- [ ] Invite the bot to / verify it responds in the channels judges will use; leave a pinned "try these prompts" message in the sandbox (extract / PR check / digest)

## Eligibility sanity check (one-time)

- [ ] 18+, legal resident of an eligible country (AR, AU, BE, CA-except-QC, FR, DE, IN, IE, JP, LU, NL, NZ, ZA, ES, UK, US)
- [ ] Project is new, original, built during the submission period (May 20 – Jul 13, 2026) ✓
- [ ] Slack Developer Program joined, sandbox provisioned (event code SABC-7X2K-M9PL-4QFN) ✓ — already done

## NOT required (don't waste time)

- Slack Marketplace submission / App ID (Organizations track only)
- Impact statement (for Good track only)
- Production workspace (Organizations track only — sandbox is exactly where judging happens for our track)
- Public GitHub repo (not in the rules — but linking one on Devpost is conventional and lets judges read the code; recommended)
