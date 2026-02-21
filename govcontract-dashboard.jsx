import { useState, useEffect, useCallback } from "react";

const API_BASE = "http://localhost:8000/api/v1";

// --- Color Tokens ---
const C = {
  bg: "#0a0f1a",
  surface: "#111827",
  surfaceHover: "#1a2332",
  border: "#1e293b",
  borderFocus: "#3b82f6",
  text: "#e2e8f0",
  textMuted: "#94a3b8",
  textDim: "#64748b",
  accent: "#3b82f6",
  accentHover: "#2563eb",
  high: "#22c55e",
  highBg: "rgba(34,197,94,0.1)",
  medium: "#f59e0b",
  mediumBg: "rgba(245,158,11,0.1)",
  low: "#64748b",
  lowBg: "rgba(100,116,139,0.1)",
  danger: "#ef4444",
  dangerBg: "rgba(239,68,68,0.08)",
};

// --- Styles ---
const s = {
  page: { minHeight: "100vh", background: C.bg, color: C.text, fontFamily: "'IBM Plex Sans', 'SF Pro Display', -apple-system, sans-serif", padding: "0" },
  header: { padding: "20px 32px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", background: "linear-gradient(180deg, #0f172a 0%, #0a0f1a 100%)" },
  headerTitle: { fontSize: "20px", fontWeight: 700, letterSpacing: "-0.02em", color: "#fff" },
  headerSub: { fontSize: "12px", color: C.textDim, marginTop: 2 },
  nav: { display: "flex", gap: 8 },
  navBtn: (active) => ({ padding: "8px 16px", fontSize: "13px", fontWeight: 500, background: active ? C.accent : "transparent", color: active ? "#fff" : C.textMuted, border: `1px solid ${active ? C.accent : C.border}`, borderRadius: 8, cursor: "pointer", transition: "all 0.15s" }),
  main: { display: "grid", gridTemplateColumns: "320px 1fr", minHeight: "calc(100vh - 73px)" },
  sidebar: { borderRight: `1px solid ${C.border}`, padding: "24px 20px", overflowY: "auto", maxHeight: "calc(100vh - 73px)", background: "#0d1321" },
  content: { padding: "24px 32px", overflowY: "auto", maxHeight: "calc(100vh - 73px)" },
  sectionTitle: { fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: C.textDim, marginBottom: 12 },
  input: { width: "100%", padding: "10px 12px", fontSize: "13px", background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, color: C.text, outline: "none", boxSizing: "border-box", marginBottom: 8, transition: "border-color 0.15s" },
  label: { fontSize: "12px", fontWeight: 500, color: C.textMuted, marginBottom: 4, display: "block" },
  btn: (variant = "primary") => ({ padding: "10px 20px", fontSize: "13px", fontWeight: 600, background: variant === "primary" ? C.accent : "transparent", color: variant === "primary" ? "#fff" : C.textMuted, border: `1px solid ${variant === "primary" ? C.accent : C.border}`, borderRadius: 8, cursor: "pointer", transition: "all 0.15s", width: "100%" }),
  card: (tier) => ({ padding: "16px 20px", background: tier === "high" ? C.highBg : tier === "medium" ? C.mediumBg : C.surface, border: `1px solid ${tier === "high" ? "rgba(34,197,94,0.2)" : tier === "medium" ? "rgba(245,158,11,0.2)" : C.border}`, borderRadius: 12, marginBottom: 10, cursor: "pointer", transition: "all 0.15s" }),
  badge: (tier) => ({ display: "inline-block", padding: "2px 10px", fontSize: "11px", fontWeight: 700, borderRadius: 20, background: tier === "high" ? C.high : tier === "medium" ? C.medium : C.low, color: tier === "high" ? "#052e16" : tier === "medium" ? "#451a03" : "#fff", letterSpacing: "0.03em" }),
  scorePill: { display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", fontSize: "11px", fontWeight: 600, borderRadius: 6, background: "rgba(59,130,246,0.15)", color: C.accent },
  stat: { padding: "16px", background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, textAlign: "center" },
  statNum: { fontSize: "28px", fontWeight: 700, letterSpacing: "-0.03em" },
  statLabel: { fontSize: "11px", color: C.textDim, marginTop: 4, textTransform: "uppercase", letterSpacing: "0.05em" },
  tag: { display: "inline-block", padding: "2px 8px", fontSize: "11px", background: "rgba(59,130,246,0.1)", color: C.accent, borderRadius: 4, marginRight: 4, marginBottom: 4 },
  detailPanel: { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "24px", marginTop: 16 },
  textarea: { width: "100%", padding: "10px 12px", fontSize: "13px", background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, color: C.text, outline: "none", boxSizing: "border-box", marginBottom: 8, minHeight: 80, resize: "vertical", fontFamily: "inherit" },
};

// --- Components ---

function Stats({ stats }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
      <div style={s.stat}>
        <div style={{ ...s.statNum, color: C.accent }}>{stats.total}</div>
        <div style={s.statLabel}>Opportunities</div>
      </div>
      <div style={s.stat}>
        <div style={{ ...s.statNum, color: C.high }}>{stats.high}</div>
        <div style={s.statLabel}>High Match</div>
      </div>
      <div style={s.stat}>
        <div style={{ ...s.statNum, color: C.medium }}>{stats.medium}</div>
        <div style={s.statLabel}>Medium Match</div>
      </div>
      <div style={s.stat}>
        <div style={{ ...s.statNum, color: C.textDim }}>{stats.low}</div>
        <div style={s.statLabel}>Low Match</div>
      </div>
    </div>
  );
}

function ScoreBar({ score, max = 100 }) {
  const pct = Math.min((score / max) * 100, 100);
  const color = score >= 70 ? C.high : score >= 50 ? C.medium : C.low;
  return (
    <div style={{ height: 4, background: C.border, borderRadius: 2, overflow: "hidden", width: "100%" }}>
      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 2, transition: "width 0.3s" }} />
    </div>
  );
}

function OpportunityCard({ item, onClick, isSelected }) {
  const opp = item.opportunity;
  const score = item.match_score;
  const tier = item.match_tier;
  return (
    <div
      style={{ ...s.card(tier), ...(isSelected ? { borderColor: C.accent, boxShadow: `0 0 0 1px ${C.accent}` } : {}) }}
      onClick={onClick}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <span style={s.badge(tier)}>{tier.toUpperCase()}</span>
        <span style={s.scorePill}>{score.overall_score.toFixed(0)}pts</span>
      </div>
      <div style={{ fontSize: "14px", fontWeight: 600, lineHeight: 1.4, marginBottom: 6, color: "#fff" }}>
        {opp.title.length > 80 ? opp.title.slice(0, 80) + "…" : opp.title}
      </div>
      <div style={{ fontSize: "12px", color: C.textMuted, marginBottom: 8 }}>
        {opp.department || "Unknown Agency"}{opp.naics_code ? ` · NAICS ${opp.naics_code}` : ""}
      </div>
      <ScoreBar score={score.overall_score} />
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: "11px", color: C.textDim }}>
        <span>{opp.set_aside || "Full & Open"}</span>
        <span>{opp.response_deadline ? `Due: ${opp.response_deadline}` : "No deadline"}</span>
      </div>
    </div>
  );
}

function DetailView({ item, analysis, onAnalyze, analyzing }) {
  const opp = item.opportunity;
  const score = item.match_score;
  
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: "18px", fontWeight: 700, margin: 0, lineHeight: 1.3, color: "#fff" }}>{opp.title}</h2>
          <div style={{ fontSize: "13px", color: C.textMuted, marginTop: 4 }}>
            {opp.solicitation_number || opp.notice_id} · {opp.opportunity_type || "Solicitation"}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <span style={s.badge(item.match_tier)}>{item.match_tier.toUpperCase()} MATCH</span>
          <div style={{ fontSize: "24px", fontWeight: 700, color: score.overall_score >= 70 ? C.high : score.overall_score >= 50 ? C.medium : C.textDim, marginTop: 4 }}>
            {score.overall_score.toFixed(0)}
          </div>
        </div>
      </div>

      {/* Score Breakdown */}
      <div style={{ ...s.detailPanel, marginTop: 0 }}>
        <div style={s.sectionTitle}>Score Breakdown</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
          {[
            { label: "NAICS", val: score.naics_score, max: 30 },
            { label: "Set-Aside", val: score.set_aside_score, max: 20 },
            { label: "Agency", val: score.agency_score, max: 10 },
            { label: "Geography", val: score.geo_score, max: 10 },
            { label: "AI Semantic", val: score.semantic_score, max: 30 },
          ].map((s2) => (
            <div key={s2.label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: "16px", fontWeight: 700, color: s2.val > 0 ? C.accent : C.textDim }}>{s2.val.toFixed(0)}/{s2.max}</div>
              <div style={{ fontSize: "10px", color: C.textDim, marginTop: 2 }}>{s2.label}</div>
              <ScoreBar score={s2.val} max={s2.max} />
            </div>
          ))}
        </div>
        {score.explanation && (
          <div style={{ fontSize: "12px", color: C.textMuted, marginTop: 12, padding: "8px 12px", background: C.bg, borderRadius: 6 }}>
            {score.explanation}
          </div>
        )}
      </div>

      {/* Details */}
      <div style={s.detailPanel}>
        <div style={s.sectionTitle}>Opportunity Details</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 24px", fontSize: "13px" }}>
          <div><span style={{ color: C.textDim }}>Department:</span> <span style={{ color: C.text }}>{opp.department || "—"}</span></div>
          <div><span style={{ color: C.textDim }}>Office:</span> <span style={{ color: C.text }}>{opp.office || "—"}</span></div>
          <div><span style={{ color: C.textDim }}>NAICS:</span> <span style={{ color: C.text }}>{opp.naics_code || "—"} {opp.naics_description ? `(${opp.naics_description})` : ""}</span></div>
          <div><span style={{ color: C.textDim }}>Set-Aside:</span> <span style={{ color: C.text }}>{opp.set_aside || "Full & Open"}</span></div>
          <div><span style={{ color: C.textDim }}>Posted:</span> <span style={{ color: C.text }}>{opp.posted_date || "—"}</span></div>
          <div><span style={{ color: C.textDim }}>Deadline:</span> <span style={{ color: opp.response_deadline ? C.danger : C.textDim, fontWeight: opp.response_deadline ? 600 : 400 }}>{opp.response_deadline || "Not specified"}</span></div>
          <div><span style={{ color: C.textDim }}>Location:</span> <span style={{ color: C.text }}>{opp.place_of_performance || "—"}</span></div>
          <div><span style={{ color: C.textDim }}>Type:</span> <span style={{ color: C.text }}>{opp.opportunity_type || "—"}</span></div>
        </div>
        {opp.link && (
          <a href={opp.link} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", marginTop: 12, fontSize: "12px", color: C.accent, textDecoration: "none" }}>
            View on SAM.gov →
          </a>
        )}
      </div>

      {/* Description */}
      {opp.description && (
        <div style={s.detailPanel}>
          <div style={s.sectionTitle}>Description</div>
          <div style={{ fontSize: "13px", lineHeight: 1.6, color: C.textMuted, maxHeight: 200, overflowY: "auto", whiteSpace: "pre-wrap" }}>
            {opp.description}
          </div>
        </div>
      )}

      {/* AI Analysis */}
      <div style={s.detailPanel}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={s.sectionTitle}>AI Analysis</div>
          <button onClick={onAnalyze} disabled={analyzing} style={{ ...s.btn("primary"), width: "auto", padding: "6px 16px", opacity: analyzing ? 0.6 : 1 }}>
            {analyzing ? "Analyzing…" : analysis ? "Re-analyze" : "Generate Analysis"}
          </button>
        </div>
        {analysis ? (
          <div>
            <div style={{ fontSize: "13px", lineHeight: 1.7, color: C.text, marginBottom: 16, whiteSpace: "pre-wrap" }}>
              {analysis.ai_analysis}
            </div>
            {analysis.key_requirements?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: "12px", fontWeight: 600, color: C.textMuted, marginBottom: 6 }}>Key Requirements</div>
                {analysis.key_requirements.map((r, i) => <div key={i} style={s.tag}>{r}</div>)}
              </div>
            )}
            {analysis.suggested_actions?.length > 0 && (
              <div>
                <div style={{ fontSize: "12px", fontWeight: 600, color: C.textMuted, marginBottom: 6 }}>Suggested Actions</div>
                {analysis.suggested_actions.map((a, i) => (
                  <div key={i} style={{ fontSize: "13px", color: C.text, padding: "6px 0", borderBottom: `1px solid ${C.border}` }}>
                    <span style={{ color: C.accent, marginRight: 8 }}>→</span>{a}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div style={{ fontSize: "13px", color: C.textDim, fontStyle: "italic" }}>
            Click "Generate Analysis" for AI-powered evaluation of this opportunity against your profile.
          </div>
        )}
      </div>
    </div>
  );
}

// --- Main App ---

export default function GovContractDashboard() {
  const [view, setView] = useState("dashboard");
  const [profile, setProfile] = useState({
    company_name: "",
    naics_codes: "",
    set_aside_types: [],
    capability_statement: "",
    past_performance_keywords: "",
    agency_preferences: "",
    geographic_preferences: "",
  });
  const [profileId, setProfileId] = useState(null);
  const [searchKeywords, setSearchKeywords] = useState("");
  const [opportunities, setOpportunities] = useState([]);
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const [useAI, setUseAI] = useState(false);
  const [isDemo, setIsDemo] = useState(true);

  // Demo data for when backend isn't running
  const demoOpportunities = [
    {
      opportunity: { notice_id: "demo-001", title: "IT Professional Services for Cybersecurity Operations Support", solicitation_number: "FA8773-26-R-0042", department: "Department of the Air Force", office: "Air Force Materiel Command", naics_code: "541512", naics_description: "Computer Systems Design Services", set_aside: "Total Small Business", opportunity_type: "Solicitation", posted_date: "02/15/2026", response_deadline: "03/15/2026", description: "The Air Force is seeking qualified small businesses to provide cybersecurity operations support including continuous monitoring, incident response, vulnerability assessment, and security architecture review for multiple installations.", place_of_performance: "Wright-Patterson AFB, OH", link: "https://sam.gov/opp/demo-001/view" },
      match_score: { overall_score: 82, naics_score: 30, set_aside_score: 20, agency_score: 10, geo_score: 0, semantic_score: 22, explanation: "Exact NAICS match (541512). Set-aside eligible. Preferred agency. AI: Strong alignment between data strategy capabilities and cybersecurity operations requirements." },
      match_tier: "high",
    },
    {
      opportunity: { notice_id: "demo-002", title: "Data Analytics and Machine Learning Platform Development", solicitation_number: "75D30126R00015", department: "Department of Health and Human Services", office: "Centers for Disease Control", naics_code: "541511", naics_description: "Custom Computer Programming Services", set_aside: "8(a)", opportunity_type: "Combined Synopsis/Solicitation", posted_date: "02/10/2026", response_deadline: "03/22/2026", description: "CDC seeks development of ML-based analytics platform for epidemiological data processing, predictive modeling, and automated reporting dashboard creation.", place_of_performance: "Atlanta, GA", link: "https://sam.gov/opp/demo-002/view" },
      match_score: { overall_score: 75, naics_score: 20, set_aside_score: 20, agency_score: 0, geo_score: 0, semantic_score: 25, explanation: "Related NAICS (same 4-digit). Set-aside eligible. AI: ML/analytics capabilities are directly relevant to this platform development requirement." },
      match_tier: "high",
    },
    {
      opportunity: { notice_id: "demo-003", title: "Cloud Migration and Infrastructure Modernization Services", solicitation_number: "70CMSD26Q00000123", department: "Department of Homeland Security", office: "US Citizenship and Immigration Services", naics_code: "541512", naics_description: "Computer Systems Design Services", set_aside: "Small Disadvantaged Business", opportunity_type: "Sources Sought", posted_date: "02/18/2026", response_deadline: "03/05/2026", description: "USCIS is conducting market research for cloud migration services to transition legacy on-premises systems to AWS GovCloud and Azure Government environments.", place_of_performance: "Washington, DC", link: "https://sam.gov/opp/demo-003/view" },
      match_score: { overall_score: 58, naics_score: 30, set_aside_score: 15, agency_score: 0, geo_score: 10, semantic_score: 3, explanation: "Exact NAICS match. Partial set-aside credit. Geographic fit (DC area). AI: Moderate fit — cloud migration is adjacent to data strategy expertise." },
      match_tier: "medium",
    },
    {
      opportunity: { notice_id: "demo-004", title: "AI-Powered Document Processing and Workflow Automation", solicitation_number: "1305M226QNAQ00001", department: "Department of the Interior", office: "Bureau of Land Management", naics_code: "511210", naics_description: "Software Publishers", set_aside: "Total Small Business", opportunity_type: "Combined Synopsis/Solicitation", posted_date: "02/12/2026", response_deadline: "03/28/2026", description: "BLM requires AI/ML-based document processing solution for automated extraction, classification, and routing of land management permits and environmental review documents.", place_of_performance: "Denver, CO", link: "https://sam.gov/opp/demo-004/view" },
      match_score: { overall_score: 52, naics_score: 10, set_aside_score: 20, agency_score: 0, geo_score: 0, semantic_score: 22, explanation: "Same NAICS sector. Set-aside eligible. AI: Document extraction and AI/ML capabilities strongly match this requirement despite different primary NAICS." },
      match_tier: "medium",
    },
    {
      opportunity: { notice_id: "demo-005", title: "Facilities Maintenance and Janitorial Services", solicitation_number: "SPE4A726R0045", department: "Defense Logistics Agency", office: "DLA Facility Operations", naics_code: "561720", naics_description: "Janitorial Services", set_aside: "Service-Disabled Veteran-Owned", opportunity_type: "Solicitation", posted_date: "02/08/2026", response_deadline: "03/01/2026", description: "Janitorial and facilities maintenance services for DLA distribution centers across the eastern United States.", place_of_performance: "Multiple Locations, US", link: "https://sam.gov/opp/demo-005/view" },
      match_score: { overall_score: 12, naics_score: 0, set_aside_score: 0, agency_score: 0, geo_score: 10, semantic_score: 2, explanation: "No NAICS match. No set-aside eligibility. AI: No meaningful connection between IT capabilities and janitorial requirements." },
      match_tier: "low",
    },
  ];

  const displayOpps = isDemo ? demoOpportunities : opportunities;
  const stats = {
    total: displayOpps.length,
    high: displayOpps.filter(o => o.match_tier === "high").length,
    medium: displayOpps.filter(o => o.match_tier === "medium").length,
    low: displayOpps.filter(o => o.match_tier === "low" || o.match_tier === "unscored").length,
  };

  const handleSaveProfile = async () => {
    if (isDemo) {
      setProfileId("demo-profile");
      setView("dashboard");
      return;
    }
    try {
      const body = {
        company_name: profile.company_name,
        naics_codes: profile.naics_codes.split(",").map(s => s.trim()).filter(Boolean),
        set_aside_types: profile.set_aside_types,
        capability_statement: profile.capability_statement,
        past_performance_keywords: profile.past_performance_keywords.split(",").map(s => s.trim()).filter(Boolean),
        agency_preferences: profile.agency_preferences.split(",").map(s => s.trim()).filter(Boolean),
        geographic_preferences: profile.geographic_preferences.split(",").map(s => s.trim()).filter(Boolean),
      };
      const res = await fetch(`${API_BASE}/profile`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      setProfileId(data.id);
      setView("dashboard");
    } catch (e) {
      setError("Failed to save profile. Is the backend running?");
    }
  };

  const handleSearch = async () => {
    if (isDemo) return;
    setLoading(true);
    setError(null);
    try {
      const body = { keywords: searchKeywords || null, limit: 50 };
      const res = await fetch(`${API_BASE}/opportunities/search?profile_id=${profileId || ""}&enrich=${useAI}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await res.json();
      setOpportunities(data);
      setIsDemo(false);
    } catch (e) {
      setError("Search failed. Check backend connection.");
    }
    setLoading(false);
  };

  const handleAnalyze = async () => {
    const item = displayOpps[selectedIdx];
    if (!item) return;
    setAnalyzing(true);
    if (isDemo) {
      await new Promise(r => setTimeout(r, 1500));
      setAnalysis({
        ai_analysis: `This ${item.opportunity.department} opportunity for "${item.opportunity.title}" represents a ${item.match_tier === "high" ? "strong" : item.match_tier === "medium" ? "moderate" : "weak"} fit for your company.\n\nThe requirement aligns with your capabilities in data strategy, AI/ML, and systems design. The ${item.opportunity.set_aside || "full and open"} designation ${item.match_score.set_aside_score > 0 ? "matches your set-aside eligibility, giving you a competitive advantage" : "may limit your ability to compete as a prime contractor"}.\n\nKey risk: ${item.opportunity.response_deadline ? `The response deadline of ${item.opportunity.response_deadline} requires immediate action` : "No deadline specified — monitor for updates"}. Consider reaching out to the contracting officer for additional details on evaluation criteria.`,
        key_requirements: ["Technical approach for system architecture", "Past performance on similar contracts", "Key personnel resumes", "Quality assurance plan", "Small business subcontracting plan"],
        suggested_actions: [`Review full solicitation on SAM.gov`, "Prepare capability brief tailored to this requirement", "Contact contracting officer for Q&A deadline", "Identify potential teaming partners", "Begin outline of technical volume"],
        deadline_urgency: item.opportunity.response_deadline ? "soon" : "normal",
      });
      setAnalyzing(false);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/opportunities/${item.opportunity.notice_id}/detail?profile_id=${profileId || ""}`);
      const data = await res.json();
      setAnalysis(data);
    } catch (e) {
      setError("Analysis failed.");
    }
    setAnalyzing(false);
  };

  const setAsideOptions = ["Total Small Business", "8(a)", "HUBZone", "Service-Disabled Veteran-Owned", "Women-Owned Small Business", "Small Disadvantaged Business"];

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.header}>
        <div>
          <div style={s.headerTitle}>GovContract AI</div>
          <div style={s.headerSub}>AI-Powered Government Contract Discovery</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {isDemo && (
            <span style={{ fontSize: "11px", padding: "4px 10px", background: C.mediumBg, color: C.medium, borderRadius: 6, fontWeight: 600 }}>
              DEMO MODE
            </span>
          )}
          <div style={s.nav}>
            <button style={s.navBtn(view === "dashboard")} onClick={() => setView("dashboard")}>Dashboard</button>
            <button style={s.navBtn(view === "profile")} onClick={() => setView("profile")}>Company Profile</button>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ padding: "12px 32px", background: C.dangerBg, borderBottom: `1px solid rgba(239,68,68,0.2)`, fontSize: "13px", color: C.danger }}>
          {error} <button onClick={() => setError(null)} style={{ background: "none", border: "none", color: C.danger, cursor: "pointer", marginLeft: 12, textDecoration: "underline" }}>Dismiss</button>
        </div>
      )}

      {view === "profile" ? (
        <div style={{ maxWidth: 640, margin: "40px auto", padding: "0 20px" }}>
          <h2 style={{ fontSize: "18px", fontWeight: 700, marginBottom: 24, color: "#fff" }}>Company Profile</h2>
          
          <label style={s.label}>Company Name</label>
          <input style={s.input} value={profile.company_name} onChange={e => setProfile({...profile, company_name: e.target.value})} placeholder="Quantum Robotics LLC" />
          
          <label style={s.label}>NAICS Codes (comma-separated)</label>
          <input style={s.input} value={profile.naics_codes} onChange={e => setProfile({...profile, naics_codes: e.target.value})} placeholder="541512, 541511, 541519, 541715" />
          
          <label style={s.label}>Set-Aside Eligibility</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {setAsideOptions.map(opt => (
              <button
                key={opt}
                onClick={() => {
                  const current = profile.set_aside_types;
                  setProfile({
                    ...profile,
                    set_aside_types: current.includes(opt) ? current.filter(x => x !== opt) : [...current, opt],
                  });
                }}
                style={{
                  padding: "6px 12px", fontSize: "12px", borderRadius: 6, cursor: "pointer",
                  background: profile.set_aside_types.includes(opt) ? C.accent : C.surface,
                  color: profile.set_aside_types.includes(opt) ? "#fff" : C.textMuted,
                  border: `1px solid ${profile.set_aside_types.includes(opt) ? C.accent : C.border}`,
                }}
              >
                {opt}
              </button>
            ))}
          </div>
          
          <label style={s.label}>Capability Statement</label>
          <textarea style={s.textarea} value={profile.capability_statement} onChange={e => setProfile({...profile, capability_statement: e.target.value})} placeholder="Describe your company's core capabilities, past experience, and technical strengths..." />
          
          <label style={s.label}>Past Performance Keywords (comma-separated)</label>
          <input style={s.input} value={profile.past_performance_keywords} onChange={e => setProfile({...profile, past_performance_keywords: e.target.value})} placeholder="cybersecurity, data analytics, cloud migration, AI/ML" />
          
          <label style={s.label}>Preferred Agencies (comma-separated)</label>
          <input style={s.input} value={profile.agency_preferences} onChange={e => setProfile({...profile, agency_preferences: e.target.value})} placeholder="Department of Defense, Department of Homeland Security" />
          
          <label style={s.label}>Geographic Preferences (state abbreviations, comma-separated)</label>
          <input style={s.input} value={profile.geographic_preferences} onChange={e => setProfile({...profile, geographic_preferences: e.target.value})} placeholder="NJ, VA, DC, MD" />
          
          <button style={{ ...s.btn("primary"), marginTop: 16 }} onClick={handleSaveProfile}>
            Save Profile & Go to Dashboard
          </button>
        </div>
      ) : (
        <div style={s.main}>
          {/* Sidebar - Search & Filters */}
          <div style={s.sidebar}>
            <div style={s.sectionTitle}>Search Opportunities</div>
            <input
              style={s.input}
              value={searchKeywords}
              onChange={e => setSearchKeywords(e.target.value)}
              placeholder="Keywords (e.g., cybersecurity, AI)"
              onKeyDown={e => e.key === "Enter" && handleSearch()}
            />
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              <label style={{ fontSize: "12px", color: C.textMuted, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={useAI} onChange={e => setUseAI(e.target.checked)} />
                AI Scoring
              </label>
            </div>
            <button style={s.btn("primary")} onClick={handleSearch} disabled={loading}>
              {loading ? "Searching…" : "Search SAM.gov"}
            </button>
            
            {!profileId && (
              <div style={{ marginTop: 16, padding: 12, background: C.mediumBg, borderRadius: 8, fontSize: "12px", color: C.medium }}>
                Set up your Company Profile for personalized matching scores.
              </div>
            )}

            {/* Results list */}
            <div style={{ marginTop: 24 }}>
              <div style={s.sectionTitle}>
                {displayOpps.length} Opportunities {isDemo ? "(Demo)" : ""}
              </div>
              {displayOpps.map((item, idx) => (
                <OpportunityCard
                  key={item.opportunity.notice_id}
                  item={item}
                  isSelected={selectedIdx === idx}
                  onClick={() => { setSelectedIdx(idx); setAnalysis(null); }}
                />
              ))}
            </div>
          </div>

          {/* Main Content */}
          <div style={s.content}>
            <Stats stats={stats} />
            
            {selectedIdx !== null && displayOpps[selectedIdx] ? (
              <DetailView
                item={displayOpps[selectedIdx]}
                analysis={analysis}
                onAnalyze={handleAnalyze}
                analyzing={analyzing}
              />
            ) : (
              <div style={{ textAlign: "center", padding: "80px 0", color: C.textDim }}>
                <div style={{ fontSize: "48px", marginBottom: 16 }}>🎯</div>
                <div style={{ fontSize: "16px", fontWeight: 600, color: C.textMuted }}>Select an opportunity</div>
                <div style={{ fontSize: "13px", marginTop: 8 }}>Click any contract in the sidebar to view details and AI analysis</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
