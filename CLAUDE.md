# GovContract AI - Project Intelligence Document

## What This Is
AI-powered government contract discovery and proposal assistance tool for small businesses.
Built to be dogfooded by the founder (former Booz Allen Hamilton consultant) and sold to
small businesses navigating federal/state procurement.

## Architecture

### Stack
- **Backend**: Python 3.12+ / FastAPI
- **Frontend**: React (single HTML artifact for V1, Next.js for V2)
- **Database**: Supabase (PostgreSQL) — free tier
- **AI**: Claude API (Sonnet for scoring, Haiku for classification)
- **Data Sources**: SAM.gov API (primary), FPDS (future), state portals (future)
- **Deployment**: Vercel (frontend) + Railway/Render (backend) — both free tier

### Core Data Flow
```
SAM.gov API → Opportunity Ingestion → Normalization → 
Company Profile Matching (NAICS + Claude semantic scoring) →
Ranked Dashboard with AI Analysis → Email Alerts
```

### Key Files
- `backend/app/main.py` — FastAPI app entry point
- `backend/app/services/sam_api.py` — SAM.gov API integration
- `backend/app/services/matcher.py` — Opportunity-to-company matching engine
- `backend/app/services/analyzer.py` — Claude-powered opportunity analysis
- `backend/app/models/schemas.py` — Pydantic models for all data structures
- `backend/app/api/routes.py` — API endpoints
- `frontend/src/App.jsx` — Main React dashboard (single-file artifact for V1)

### SAM.gov API Details
- Base URL: `https://api.sam.gov/opportunities/v2/search`
- Auth: API key (free registration at https://open.gsa.gov/api/get-opportunities-public-api/)
- Rate limit: 10 requests/sec
- Returns: solicitations, presolicitations, award notices, etc.
- Key fields: title, solicitationNumber, department, subtier, naicsCode, setAside, 
  responseDeadline, description, pointOfContact

### Company Profile Schema
A user creates a profile with:
- Company name, CAGE code, UEI
- NAICS codes (primary + secondary)
- Set-aside eligibility (8(a), HUBZone, SDVOSB, WOSB, SDB, etc.)
- Capability statement (free text → Claude embeds for semantic matching)
- Past performance keywords
- Geographic preferences
- Agency preferences
- Revenue range / size standard

### Matching Algorithm
1. **Hard filters**: NAICS code overlap, set-aside eligibility, active status
2. **Soft scoring** (0-100):
   - NAICS match: exact=30pts, related=15pts
   - Set-aside match: 20pts
   - Agency preference match: 10pts
   - Geographic match: 10pts
   - Claude semantic relevance (capability statement vs description): 0-30pts
3. Opportunities scoring >50 are shown, >70 are "high match"

### Codex Review Guidelines
When OpenAI Codex reviews PRs from Claude Code:
- Check for hallucinated API endpoints or fields (verify against SAM.gov docs)
- Verify error handling on all external API calls
- Ensure no API keys are hardcoded (use env vars)
- Check that Claude API calls have proper cost controls (max_tokens limits)
- Validate that matching scores are deterministic for same inputs
- Flag any N+1 query patterns in database access

## Development Commands
```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (V1 is a single React artifact file)
# For V2: cd frontend && npm install && npm run dev

# Run tests
cd backend && pytest

# Deploy
# Backend: push to Railway/Render connected to main branch
# Frontend: push to Vercel connected to main branch
```

## V1 Scope — MVP: Discovery + Matching (Weeks 1-4, <$200)
**Goal**: First paying customer. Dogfood it yourself to find real contracts for Quantum Robotics.

### V1 Completed
- [x] SAM.gov API integration (search + detail fetch)
- [x] Company profile creation/storage (in-memory for V1)
- [x] Matching engine (NAICS + set-aside + semantic scoring)
- [x] Claude-powered opportunity analysis (Haiku for scoring, Sonnet for deep analysis)
- [x] Dashboard UI with filters, score breakdowns, and AI analysis
- [x] Demo mode with sample data

### V1 Remaining Tasks (Priority Order)
- [ ] **Email alerts (daily digest)** — Use SendGrid free tier (100 emails/day). Create `backend/app/services/email_alerts.py`. APScheduler job runs at 6am ET, fetches new opportunities posted in last 24hrs, scores against all profiles, sends HTML email with top 10 matches. Template: subject line "🎯 {count} New Contract Matches — {date}", body shows title, department, score, deadline, one-click link to dashboard.
- [ ] **User authentication** — Supabase Auth (free tier, supports email/password + Google OAuth). Add `backend/app/services/auth.py` with JWT middleware. Protect all /api/v1/ routes except /health. Frontend: add login/register modal, store JWT in localStorage, pass in Authorization header.
- [ ] **Saved searches** — Supabase table: `saved_searches(id, user_id, name, filters_json, created_at)`. API endpoints: POST/GET/DELETE /api/v1/searches. Dashboard sidebar shows saved searches as clickable presets.
- [ ] **Persistent storage** — Migrate from in-memory dicts to Supabase PostgreSQL. Tables: `profiles`, `saved_searches`, `opportunity_cache` (TTL: 24hrs), `user_settings`.
- [ ] **SAM.gov full description fetch** — Current API returns truncated descriptions. Add a detail fetch that pulls full solicitation text when user clicks "View Details". Cache results in `opportunity_cache` table.
- [ ] **Error handling & rate limiting** — Add retry logic with exponential backoff on SAM.gov API (httpx retries). Add rate limiter on Claude API calls (max 50 analyses/user/day on free tier).
- [ ] **Deploy** — Backend on Railway (Dockerfile + railway.toml). Frontend: wrap React component in Next.js, deploy to Vercel. Configure custom domain.

### V1 Tech Specs
```
Backend: Python 3.12, FastAPI 0.115, httpx, anthropic SDK, apscheduler
Frontend: React (single JSX artifact → Next.js wrapper for deploy)
Database: Supabase PostgreSQL (free: 500MB, 50K rows)
Auth: Supabase Auth (free: 50K MAU)
Email: SendGrid (free: 100/day)
Hosting: Railway (free: $5 credit/month) + Vercel (free tier)
AI Costs: ~$0.001/opportunity (Haiku scoring), ~$0.01/opportunity (Sonnet analysis)
Total monthly cost at 100 users: ~$30-50 (API costs only)
```

### V1 Pricing
- **Free tier**: 10 matched opportunities/week, manual search only, no email alerts
- **Pro ($49/month)**: Unlimited search, daily email alerts, AI analysis on all matches
- **Teams ($99/month)**: Everything in Pro + saved searches + API access + priority support

---

## V2 Scope — Growth: Multi-Source + Proposal Assist (Months 2-6, <$500 additional)
**Goal**: 50 paying users. Close the gap with Sweetspot on data sources and proposal help.

### V2 Features (Priority Order)

#### 2.1 State & Local Procurement Portals
- [ ] **Data source expansion** — Add scrapers for top 10 state portals by volume:
  - NJ (BidExpress), NY (Empire State Purchasing), CA (Cal eProcure), TX (ESBD),
    VA (eVA), FL (MyFloridaMarketPlace), MD (eMaryland Marketplace), PA (eMarketplace),
    GA (Team Georgia Marketplace), IL (BidBuy)
- [ ] **Unified opportunity schema** — Normalize all sources into our existing `Opportunity` model. Add `source` field (enum: SAM_GOV, NJ_STATE, NY_STATE, etc.).
- [ ] **Scraping architecture** — Create `backend/app/services/scrapers/` directory. Each scraper is a class inheriting `BasePortalScraper` with `fetch()` and `normalize()` methods. Use httpx + BeautifulSoup. Run on APScheduler: SAM.gov every 6hrs, state portals every 12hrs.
- [ ] **FPDS integration** — Federal Procurement Data System for historical award data. API: `https://www.fpds.gov/`. Ingest award records to build competitive intelligence database.

#### 2.2 Proposal Compliance Matrix Generator
- [ ] **Solicitation document parser** — Upload PDF/DOCX solicitation. Claude extracts: Section L (instructions), Section M (evaluation criteria), Section C (statement of work), all compliance requirements. Create `backend/app/services/proposal/sol_parser.py`.
- [ ] **Compliance matrix builder** — From parsed requirements, generate a structured matrix: Requirement ID | Requirement Text | Section Reference | Compliant (Y/N) | Response Location | Notes. Output as downloadable XLSX and editable in-dashboard table.
- [ ] **Response outline generator** — Claude generates a proposal outline based on Section L instructions, with section headers, page limits, suggested content themes, and evaluation criteria weighting. This is NOT full proposal writing — it's the skeleton that a human fills in.

#### 2.3 Competitive Intelligence
- [ ] **Past award analysis** — Using FPDS data, for any opportunity show: Who won the previous iteration of this contract? At what price? How many bidders? What was the incumbent's NAICS?
- [ ] **Win probability estimator** — Based on set-aside type, number of historical bidders, contract value, and user's past performance alignment, estimate a rough win probability (Low/Medium/High). Display on dashboard cards.
- [ ] **Agency spending patterns** — Chart showing an agency's spending by NAICS code over time. Helps users identify agencies that are increasing spend in their area.

#### 2.4 Enhanced Matching
- [ ] **Embedding-based semantic matching** — Replace Claude API scoring with local sentence-transformer embeddings (all-MiniLM-L6-v2). Generate embeddings for capability statements and opportunity descriptions. Cosine similarity for scoring. Faster, cheaper, and cacheable. Fall back to Claude for edge cases.
- [ ] **Learning from user behavior** — Track which opportunities users click, save, and mark as "bidding." Use this signal to improve matching: weight NAICS codes and keywords that correlate with user engagement.

#### 2.5 Team Collaboration (needed for $99/month tier)
- [ ] **Multi-user per organization** — Supabase: `organizations` table, `org_members` table with roles (admin, member, viewer). Profile is shared within org.
- [ ] **Pursuit tracking** — Kanban board: Identified → Qualifying → Capture → Proposal → Submitted → Won/Lost. Each pursuit linked to an opportunity with notes, tasks, and deadlines.
- [ ] **Shared annotations** — Users can add notes and tags to opportunities visible to their team.

### V2 Tech Additions
```
Scrapers: httpx + BeautifulSoup + APScheduler (state portals)
Embeddings: sentence-transformers (all-MiniLM-L6-v2) — runs on CPU, ~50ms/embedding
Proposal Parsing: Claude Sonnet (PDF text extraction → structured output)
Document Generation: python-docx (compliance matrix XLSX), docx-js (proposal outlines)
FPDS API: REST + XML parsing
New tables: organizations, org_members, pursuits, pursuit_notes, 
            opportunity_embeddings, user_engagement_signals, scraped_sources
```

### V2 Pricing Update
- **Free tier**: Same as V1
- **Pro ($99/month)**: Federal + state/local, compliance matrix, competitive intel, pursuit tracking
- **Team ($199/month)**: Everything + multi-user, shared workspace, API access, priority support
- **Enterprise ($499/month)**: Custom integrations, dedicated support, SLA, volume discounts

### V2 Competitive Positioning
After V2, we match Sweetspot on: multi-source discovery, AI matching, basic proposal tooling, and pursuit management. We beat them on: price (our Pro at $99 vs their custom pricing), semantic matching quality (embeddings > keyword lookalike), and small business UX simplicity. We still trail on: proposal copilot depth, form-fill automation, and certifications (CMMC, SOC 2).

---

## V3 Scope — Scale: Full Proposal Engine + Platform (Months 6-18)
**Goal**: $100K MRR. Become the "Sweetspot for small businesses" — full lifecycle at 1/10th the enterprise price.

### V3 Features (Priority Order)

#### 3.1 Full Proposal Draft Generation
- [ ] **Section-by-section proposal writer** — User provides: compliance matrix (from V2), past performance examples, key personnel resumes, technical approach notes. Claude Sonnet generates full proposal sections matching Section L format requirements. Output as formatted DOCX with proper headers, page numbers, and section breaks.
- [ ] **Company knowledge base** — Persistent RAG system storing: past proposals (vectorized), capability statements, past performance citations, key personnel bios, corporate certifications, facility clearances. Claude draws from this when drafting. Uses Pinecone or pgvector in Supabase.
- [ ] **Iterative refinement loop** — User reviews draft, provides feedback ("make the technical approach more specific about our AWS experience"), Claude revises specific sections. Track versions.
- [ ] **Compliance checker** — After draft is complete, a separate Claude pass verifies every Section M evaluation criterion is addressed, all Section L format requirements are met (page limits, font size, margin requirements), and flags gaps.

#### 3.2 Teaming Partner Matching
- [ ] **Contractor directory** — Ingest SAM.gov entity registration data. Build profiles of all registered contractors with NAICS codes, set-aside status, past awards, location, size.
- [ ] **Teaming recommendations** — For a given opportunity, recommend potential teaming partners who: complement the user's NAICS gaps, have past performance with the target agency, hold required set-aside certifications the user lacks, are geographically proximate to the place of performance.
- [ ] **Teaming agreement templates** — Claude-generated teaming agreements and subcontracting plans based on opportunity requirements.

#### 3.3 Win/Loss Analytics
- [ ] **Bid tracking** — After submission, track outcome (win/loss/no-bid). Build longitudinal dataset.
- [ ] **Pattern analysis** — Across all users (anonymized), identify: which agencies have highest win rates for small businesses, which NAICS codes are most competitive, which set-aside types yield best outcomes, optimal contract value ranges by company size.
- [ ] **Post-mortem assistant** — On a loss, Claude analyzes the winning award data (from FPDS) and compares to user's bid characteristics. Generates: "The winner was a HUBZone firm with 3 prior contracts with this office. Consider pursuing HUBZone certification or teaming with a HUBZone partner."

#### 3.4 Subcontract Opportunity Discovery
- [ ] **Prime contract monitoring** — Track large prime contracts that require small business subcontracting plans. Alert users when primes in their NAICS are awarded contracts requiring subcontractors.
- [ ] **Prime contractor relationship mapping** — Show which primes have historically subcontracted in the user's NAICS/geography. Enable direct outreach.

#### 3.5 Platform & API
- [ ] **Public API** — RESTful API for programmatic access to matching, scoring, and search. API keys with rate limiting. Enables integrations with CRMs, ERPs, and custom workflows.
- [ ] **Webhook system** — Push notifications on new high-match opportunities, deadline reminders, award announcements for tracked contracts.
- [ ] **White-label** — Allow GovCon consultants and PTACs (Procurement Technical Assistance Centers) to offer the tool under their brand to their small business clients. Revenue share model.
- [ ] **Mobile app** — React Native app for on-the-go opportunity review and alerts.

#### 3.6 Certifications & Compliance
- [ ] **SOC 2 Type II** — Required to serve any serious contractor. Budget: $15-30K for initial audit.
- [ ] **FedRAMP assessment** — Consider FedRAMP Ready designation (not full ATO) to signal seriousness to federal buyers. Expensive ($100K+) — only pursue if revenue justifies it.

### V3 Tech Additions
```
Proposal Engine: Claude Sonnet/Opus + RAG (pgvector or Pinecone)
Document Generation: docx-js for DOCX proposals, python-pptx for capability briefs
Knowledge Base: pgvector extension in Supabase (free tier supports it)
Entity Data: SAM.gov Entity API for contractor directory
Mobile: React Native or Expo
API Layer: FastAPI with API key auth + rate limiting
Webhooks: Celery + Redis for async delivery
Analytics: PostHog (free tier) for product analytics, custom SQL for bid analytics
New tables: proposals, proposal_versions, proposal_sections, knowledge_base_chunks,
            knowledge_base_embeddings, teaming_partners, bid_outcomes, api_keys,
            webhooks, white_label_configs
```

### V3 Pricing
- **Starter ($99/month)**: Discovery + matching + alerts + basic proposal tools
- **Professional ($249/month)**: Full proposal generation + competitive intel + pursuit management
- **Team ($499/month)**: Everything + multi-user + API + teaming partner matching
- **Enterprise ($999/month)**: White-label + dedicated support + SLA + custom integrations
- **Success fee (optional)**: 0.5% of contract value on wins attributed to the platform (opt-in)

### V3 Revenue Targets
- 200 Starter users × $99 = $19,800/month
- 75 Professional users × $249 = $18,675/month
- 30 Team accounts × $499 = $14,970/month
- 10 Enterprise accounts × $999 = $9,990/month
- Success fees (conservative): $5,000/month
- **Total: ~$68,435 MRR ($821K ARR)**

### V3 Competitive Position
At V3 completion, we are a legitimate Sweetspot alternative with: comparable discovery (federal + state + local), superior AI matching (embeddings + behavioral learning), strong proposal tooling (not as deep as GovDash but good enough for 90% of small businesses), and dramatically lower pricing. We own the "SMB tier" of the market — the $99-499/month segment that GovDash and Procurement Sciences ignore.

## Environment Variables Required
```
SAM_GOV_API_KEY=         # From https://open.gsa.gov/
ANTHROPIC_API_KEY=       # From console.anthropic.com
SUPABASE_URL=            # From Supabase dashboard
SUPABASE_ANON_KEY=       # From Supabase dashboard
```

## Design Principles
1. **Franchise owner simple**: If a 7-Eleven owner can't use it, it's too complex
2. **AI explains itself**: Every match score shows WHY it matched
3. **Actionable over comprehensive**: 10 great matches > 1000 unfiltered results
4. **Cost-conscious**: Haiku for classification, Sonnet only for deep analysis
5. **Offline-capable data**: Cache opportunities locally, don't re-fetch constantly
