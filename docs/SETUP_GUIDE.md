# Setup Guide: OpenClaw + Claude Code + Codex Dev Pipeline

## Overview
Your development stack:
- **OpenClaw** → Command center (message it from WhatsApp/Telegram to trigger builds)
- **Claude Code** → Primary coding engine (writes, tests, deploys code)
- **OpenAI Codex** → Code reviewer (validates Claude's output, catches blind spots)
- **Cursor** → IDE for hands-on work when you're at a keyboard

---

## Step 1: Claude Code (Do This First — Works Without 5090)

Claude Code works on your Intel Mac right now. This is your primary build tool.

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Navigate to project
cd ~/govcontract-ai

# Start Claude Code (uses your Anthropic API key or Claude Max subscription)
claude

# Or with Max subscription:
claude --auth max
```

### First Session Commands
```
> Read CLAUDE.md and understand the project
> Install backend dependencies and verify the SAM.gov API client works
> Run the FastAPI server and test the /health endpoint
> Review all files for any bugs or missing imports
```

### Key Claude Code Tips
- It reads CLAUDE.md automatically on session start — that's your "brain" file
- Use `claude --resume` to continue where you left off
- It can run tests, fix bugs, and commit to git autonomously
- Cost: ~$0.50-2.00/hour of active coding with Sonnet

---

## Step 2: OpenAI Codex for Review

Codex can review PRs and catch issues Claude might miss.

### Option A: GitHub Copilot Coding Agent (Recommended)
```bash
# In your GitHub repo settings:
# 1. Enable Copilot → Coding Agent
# 2. Assign issues to @copilot for automated PRs
# 3. Or use it for PR review:

# When Claude Code creates a PR, Copilot reviews it automatically
# Configure in .github/copilot-review.yml:
```

Create `.github/copilot-review.yml`:
```yaml
# Copilot will review all PRs
review:
  auto_review: true
  focus_areas:
    - security
    - error_handling
    - api_validation
    - cost_controls
```

### Option B: OpenAI Codex CLI (Direct)
```bash
# Install Codex CLI
npm install -g @openai/codex

# Review a file
codex review backend/app/services/sam_api.py

# Review entire project
codex review . --focus "security,error-handling,api-costs"
```

### Option C: Manual Codex Review via API
Use the OpenAI API to review Claude's code. Add this script to your project:

```python
# scripts/codex_review.py
"""Send Claude Code's output to Codex for review."""
import openai
import sys
import subprocess

def review_recent_changes():
    # Get recent git diff
    diff = subprocess.check_output(
        ["git", "diff", "HEAD~1"], text=True
    )
    
    client = openai.OpenAI()
    response = client.responses.create(
        model="o3-mini",
        input=f"""Review this code diff for a government contract finder app.
Check for:
1. Security issues (API key exposure, injection, etc.)
2. SAM.gov API usage correctness
3. Error handling gaps
4. Claude API cost controls (are max_tokens set appropriately?)
5. Edge cases in the matching algorithm

DIFF:
{diff[:15000]}

Provide specific, actionable feedback.""",
    )
    print(response.output_text)

if __name__ == "__main__":
    review_recent_changes()
```

---

## Step 3: OpenClaw (When You Have a Persistent Machine)

### On Intel Mac (Temporary Setup)
OpenClaw runs on Mac but your laptop sleeping = agent goes offline.
Good enough for testing the workflow.

```bash
# Install OpenClaw
curl -fsSL https://get.openclaw.ai | bash

# Run the setup wizard
openclaw onboard

# During setup:
# - Model provider: Anthropic (use your Claude API key or Max sub)
# - Channel: Telegram (easiest to set up) or WhatsApp
# - Skills: Enable "claude-code-wingman" for dev automation
# - DM policy: "pairing" (secure by default)
```

### Install the Claude Code Skill
```bash
# This lets OpenClaw trigger Claude Code sessions
mkdir -p ~/.claude/skills/openclaw-skills-clawdbot-skill
curl -fsSL "https://market.lobehub.com/api/v1/skills/openclaw-skills-clawdbot-skill/download" \
  -o /tmp/openclaw-skills-clawdbot-skill.zip
unzip -o /tmp/openclaw-skills-clawdbot-skill.zip \
  -d ~/.claude/skills/openclaw-skills-clawdbot-skill
```

### On 5090 PC (Permanent Setup — Do This When You Have It)
```bash
# Install in Docker for security isolation
docker run -d \
  --name openclaw \
  --restart unless-stopped \
  -v openclaw-data:/data \
  -e ANTHROPIC_API_KEY=your_key \
  -e OPENAI_API_KEY=your_key \
  ghcr.io/openclaw/openclaw:latest

# Or install natively with WSL2:
# 1. Enable WSL2 on Windows
# 2. Install Ubuntu 24.04
# 3. Follow Mac install steps above inside WSL2

# The 5090 stays on 24/7 as your always-on AI operations center
```

### Example OpenClaw Workflows (via Telegram/WhatsApp)
Once configured, you can message your bot:

```
You: "Start a Claude Code session on govcontract-ai, 
      add email alert functionality for daily opportunity digests"

Bot: "Starting session 'govcontract-email-alerts' in ~/govcontract-ai...
      Claude Code is working. I'll update you every 5 iterations."

[10 min later]

Bot: "Session update: Created backend/app/services/email_alerts.py,
      added APScheduler job in main.py, wrote 3 tests. 
      PR #4 ready for review. Want me to run Codex review?"

You: "Yes, review and merge if it passes"

Bot: "Codex review passed with 1 minor suggestion (added timeout to SMTP).
      Applied fix. Merged to main. Deployed to staging."
```

---

## Step 4: Deploy the GovContract AI App

### Backend (Railway — Free Tier)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
cd backend
railway init
railway up

# Set environment variables
railway variables set SAM_GOV_API_KEY=your_key
railway variables set ANTHROPIC_API_KEY=your_key
```

### Frontend (Vercel — Free Tier)
The V1 frontend is a React artifact file. For deployment:
```bash
# Create a minimal Next.js wrapper (Claude Code can do this)
cd frontend
npx create-next-app@latest govcontract-web --typescript
# Move the React component into pages/index.tsx
# Deploy:
npx vercel --prod
```

### Get Your SAM.gov API Key (Free)
1. Go to https://open.gsa.gov/api/get-opportunities-public-api/
2. Click "Get an API Key"
3. Register with your email
4. Key arrives instantly
5. Add to .env file

---

## Step 5: The Full Daily Workflow

### Morning (from phone via OpenClaw/Telegram)
```
"Check for new high-match opportunities posted in the last 24 hours"
"Generate the daily digest email for my profile"
"Any PRs waiting for review?"
```

### Working Session (laptop with Cursor/Claude Code)
```bash
# Open project in Cursor
cursor ~/govcontract-ai

# Or use Claude Code CLI
cd ~/govcontract-ai && claude

# Example tasks:
> Add state procurement portal scraping for New Jersey
> Build the proposal compliance matrix feature
> Write integration tests for the matching engine
```

### Evening (from phone via OpenClaw)
```
"Run full test suite on govcontract-ai"
"Deploy latest main to production"
"Draft 5 cold outreach emails for small gov contractors in NJ"
"Schedule a LinkedIn post about our new proposal assist feature"
```

---

## Cost Summary (Monthly)

| Tool | Cost | Notes |
|------|------|-------|
| Claude Max subscription | $100-200 | Powers Claude Code + API calls |
| Cursor Pro | $20 | IDE with AI |
| OpenAI API (Codex review) | $10-30 | Only for code review |
| OpenClaw | $0 | Free + uses your Claude/OpenAI keys |
| Railway (backend) | $0-5 | Free tier covers V1 |
| Vercel (frontend) | $0 | Free tier |
| SAM.gov API | $0 | Free |
| **Total** | **$130-255/month** | |

This replaces a $15-25K/month engineering team.

---

## Quick Start Checklist

- [ ] Get SAM.gov API key (5 min)
- [ ] Get Anthropic API key or Claude Max subscription
- [ ] Clone the govcontract-ai repo to your Mac
- [ ] Install Claude Code: `npm install -g @anthropic-ai/claude-code`
- [ ] Run `claude` in the project directory, tell it to read CLAUDE.md
- [ ] Have Claude Code install deps and start the backend
- [ ] Open the React dashboard artifact to verify the UI
- [ ] Test a live SAM.gov search
- [ ] Set up GitHub repo and connect Copilot for PR review
- [ ] (Later) Install OpenClaw when you have the 5090
