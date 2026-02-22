import { useState, useEffect, useMemo, useCallback, useRef } from "react";

const API = "http://localhost:8000/api/v1";

// ─── Utilities ────────────────────────────────────────────────────────────────

function daysUntil(dateStr) {
  if (!dateStr) return null;
  try {
    // Handle MM/DD/YYYY and ISO formats
    const d = /^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)
      ? new Date(dateStr.replace(/(\d{2})\/(\d{2})\/(\d{4})/, "$3-$1-$2"))
      : new Date(dateStr);
    return Math.ceil((d - Date.now()) / 86_400_000);
  } catch { return null; }
}

function fmtDate(dateStr) {
  if (!dateStr) return null;
  try {
    const d = /^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)
      ? new Date(dateStr.replace(/(\d{2})\/(\d{2})\/(\d{4})/, "$3-$1-$2"))
      : new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch { return dateStr; }
}

function fmtDateTime(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleString("en-US", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
    });
  } catch { return isoStr; }
}

function fmtValue(v) {
  if (v == null) return null;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

// ─── Style Helpers ────────────────────────────────────────────────────────────

function tierBg(tier) {
  if (tier === "high") return "bg-emerald-500/10 border-emerald-500/25 hover:border-emerald-500/50";
  if (tier === "medium") return "bg-amber-500/10 border-amber-500/25 hover:border-amber-500/50";
  return "bg-slate-900 border-slate-800 hover:border-slate-700";
}
function tierBadge(tier) {
  if (tier === "high") return "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
  if (tier === "medium") return "bg-amber-500/20 text-amber-400 border border-amber-500/30";
  return "bg-slate-800 text-slate-500 border border-slate-700";
}
function tierBarColor(score) {
  if (score >= 70) return "bg-emerald-400";
  if (score >= 50) return "bg-amber-400";
  return "bg-slate-500";
}
function complexityBadge(ct) {
  if (ct === "MICRO") return "bg-slate-700/60 text-slate-400";
  if (ct === "SIMPLIFIED") return "bg-sky-500/15 text-sky-400";
  if (ct === "MAJOR") return "bg-purple-500/15 text-purple-400";
  return "bg-blue-500/15 text-blue-400";
}
function competitionBadge(cl) {
  if (cl === "OPEN") return "bg-emerald-500/15 text-emerald-400";
  if (cl === "PARTIAL") return "bg-amber-500/15 text-amber-400";
  return "bg-red-500/15 text-red-400";
}
const CLUSTER_COLORS = [
  "bg-blue-500/20 text-blue-300 border border-blue-500/30",
  "bg-violet-500/20 text-violet-300 border border-violet-500/30",
  "bg-orange-500/20 text-orange-300 border border-orange-500/30",
  "bg-teal-500/20 text-teal-300 border border-teal-500/30",
  "bg-pink-500/20 text-pink-300 border border-pink-500/30",
];
function clusterColor(idx) { return CLUSTER_COLORS[idx % CLUSTER_COLORS.length]; }

const CERT_COLORS = {
  "Small Business": "bg-slate-700 text-slate-300",
  "8(a)": "bg-violet-500/20 text-violet-300",
  HUBZone: "bg-orange-500/20 text-orange-300",
  "Service-Disabled Veteran-Owned": "bg-red-500/20 text-red-400",
  "Veteran-Owned": "bg-red-500/15 text-red-400",
  "Women-Owned Small Business": "bg-pink-500/20 text-pink-300",
  "Economically Disadvantaged WOSB": "bg-pink-500/20 text-pink-300",
  "Small Disadvantaged Business": "bg-amber-500/20 text-amber-400",
  "Minority-Owned": "bg-teal-500/20 text-teal-400",
  AbilityOne: "bg-indigo-500/20 text-indigo-300",
};
function certBadge(cert) {
  return CERT_COLORS[cert] || "bg-slate-700 text-slate-300";
}

// ─── Demo Data ────────────────────────────────────────────────────────────────

const DEMO_CLUSTERS = [
  {
    id: "demo-c1", name: "AI & Robotics",
    naics_codes: ["541512", "541511", "541715", "334111"],
    certifications: ["Small Business"],
    capability_description: "Artificial intelligence, machine learning, autonomous systems, robotics, computer vision, edge computing, IoT sensor networks, drone systems, autonomous ground vehicles",
    team_roster: [
      { name: "Dr. Sarah Chen", role: "Chief AI Officer", clearance: "Secret" },
      { name: "Marcus Williams", role: "Robotics Lead", clearance: "TS/SCI" },
      { name: "Ana Ruiz", role: "ML Engineer", clearance: null },
    ],
    created_at: "2026-01-15T00:00:00",
  },
  {
    id: "demo-c2", name: "Cybersecurity",
    naics_codes: ["541690", "511210", "541519", "518210"],
    certifications: ["Small Business"],
    capability_description: "Cybersecurity operations, SOC management, penetration testing, vulnerability assessment, CMMC compliance, cloud security architecture, zero trust implementation, incident response",
    team_roster: [
      { name: "James Okafor", role: "CISO", clearance: "Secret" },
      { name: "Keisha Morris", role: "Pen Test Lead", clearance: "TS/SCI" },
    ],
    created_at: "2026-01-15T00:00:00",
  },
  {
    id: "demo-c3", name: "Facilities & Maintenance",
    naics_codes: ["561720", "561210", "561790", "238220"],
    certifications: ["Small Business"],
    capability_description: "Janitorial services, building maintenance, groundskeeping, facility management, custodial services, property maintenance, HVAC maintenance, general cleaning",
    team_roster: [],
    created_at: "2026-01-15T00:00:00",
  },
  {
    id: "demo-c4", name: "Cloud & IT Services",
    naics_codes: ["541519", "518210", "541513", "541611"],
    certifications: ["Small Business"],
    capability_description: "Cloud migration, AWS/Azure/GCP infrastructure, DevOps, IT modernization, data engineering, API development, system integration, IT consulting, Agile project management",
    team_roster: [
      { name: "Priya Patel", role: "Cloud Architect", clearance: null },
      { name: "David Kim", role: "DevOps Lead", clearance: null },
    ],
    created_at: "2026-01-15T00:00:00",
  },
];

const DEMO_OPPS = [
  { opportunity: { notice_id: "d001", title: "AI-Powered Intelligence Analysis Platform for Army Intelligence Center", solicitation_number: "W911NF-26-R-0042", department: "DEPT OF DEFENSE", sub_tier: "U.S. Army Research Laboratory", office: "ARL Computational Sciences", naics_code: "541511", naics_description: "Custom Computer Programming Services", set_aside: "Total Small Business", opportunity_type: "Solicitation", posted_date: "02/18/2026", response_deadline: "03/15/2026", description: "The Army Research Laboratory seeks a small business to develop an AI-powered intelligence analysis platform leveraging large language models, computer vision, and autonomous data ingestion pipelines for multi-INT fusion and rapid decision support.", place_of_performance: "Aberdeen Proving Ground, MD", estimated_value: 4500000, award_amount: null, link: "https://sam.gov/opp/d001/view", active: true, source: "sam.gov", complexity_tier: "STANDARD", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 80, naics_score: 30, set_aside_score: 20, agency_score: 10, geo_score: 10, semantic_score: 10, explanation: "Exact NAICS match (541511). SB set-aside eligible. DoD agency preference. MD geographic match." }, match_tier: "high", best_cluster_id: "demo-c1", best_cluster_name: "AI & Robotics" },
  { opportunity: { notice_id: "d008", title: "Penetration Testing and Red Team Services – DISA Classified Networks", solicitation_number: "HC104826Q0178", department: "DEPT OF DEFENSE", sub_tier: "Defense Information Systems Agency", office: "DISA Cybersecurity Operations", naics_code: "541690", naics_description: "Other Scientific and Technical Consulting", set_aside: "Total Small Business", opportunity_type: "RFQ", posted_date: "02/15/2026", response_deadline: "02/27/2026", description: "DISA requires penetration testing and red team assessments for 8 classified networks. Requires cleared personnel (TS/SCI). Work includes STIG validation, network segmentation testing, and post-engagement reporting.", place_of_performance: "Fort Meade, MD", estimated_value: 420000, award_amount: null, link: "https://sam.gov/opp/d008/view", active: true, source: "sam.gov", complexity_tier: "SIMPLIFIED", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 70, naics_score: 30, set_aside_score: 20, agency_score: 10, geo_score: 10, semantic_score: 0, explanation: "Exact NAICS match. SB set-aside eligible. DoD agency. MD geographic match." }, match_tier: "high", best_cluster_id: "demo-c2", best_cluster_name: "Cybersecurity" },
  { opportunity: { notice_id: "d002", title: "Zero Trust Architecture Implementation – Enterprise Cybersecurity Services", solicitation_number: "70CDCR26R00009", department: "HOMELAND SECURITY, DEPARTMENT OF", sub_tier: "CISA", office: "Cybersecurity Division", naics_code: "541519", naics_description: "Other Computer-Related Services", set_aside: "Total Small Business", opportunity_type: "Combined Synopsis/Solicitation", posted_date: "02/14/2026", response_deadline: "03/28/2026", description: "CISA seeks to implement zero trust network architecture across 12 federal agency environments. Work includes identity management, micro-segmentation, continuous monitoring, and incident response planning.", place_of_performance: "Washington, DC", estimated_value: 8200000, award_amount: null, link: "https://sam.gov/opp/d002/view", active: true, source: "sam.gov", complexity_tier: "STANDARD", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 70, naics_score: 30, set_aside_score: 20, agency_score: 0, geo_score: 10, semantic_score: 10, explanation: "Exact NAICS match. SB set-aside eligible. DC geographic match." }, match_tier: "high", best_cluster_id: "demo-c2", best_cluster_name: "Cybersecurity" },
  { opportunity: { notice_id: "d003", title: "DevSecOps Platform Engineering and Cloud Infrastructure – NAVWAR", solicitation_number: "N65236-26-Q-0012", department: "DEPT OF DEFENSE", sub_tier: "Navy", office: "NAVWAR San Diego", naics_code: "541512", naics_description: "Computer Systems Design Services", set_aside: "Total Small Business", opportunity_type: "Solicitation", posted_date: "02/16/2026", response_deadline: "03/05/2026", description: "NAVWAR seeks DevSecOps platform support including cloud infrastructure management on AWS GovCloud, CI/CD pipeline development, container orchestration via Kubernetes, and security automation tooling integration.", place_of_performance: "San Diego, CA", estimated_value: 2100000, award_amount: null, link: "https://sam.gov/opp/d003/view", active: true, source: "sam.gov", complexity_tier: "STANDARD", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 60, naics_score: 30, set_aside_score: 20, agency_score: 10, geo_score: 0, semantic_score: 0, explanation: "Exact NAICS match. SB set-aside eligible. DoD agency preference." }, match_tier: "medium", best_cluster_id: "demo-c4", best_cluster_name: "Cloud & IT Services" },
  { opportunity: { notice_id: "d004", title: "Pentagon Complex Janitorial and Custodial Services", solicitation_number: "HQ003426Q0021", department: "DEPT OF DEFENSE", sub_tier: "Washington Headquarters Services", office: "Pentagon Renovation Office", naics_code: "561720", naics_description: "Janitorial Services", set_aside: "Total Small Business", opportunity_type: "Solicitation", posted_date: "02/12/2026", response_deadline: "03/10/2026", description: "Comprehensive janitorial, custodial, and grounds maintenance services for the Pentagon complex. Includes common areas, conference rooms, E Ring offices, restrooms, and exterior grounds. Performance-based contract with QASP.", place_of_performance: "Arlington, VA", estimated_value: 950000, award_amount: null, link: "https://sam.gov/opp/d004/view", active: true, source: "sam.gov", complexity_tier: "SIMPLIFIED", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 60, naics_score: 30, set_aside_score: 20, agency_score: 10, geo_score: 0, semantic_score: 0, explanation: "Exact NAICS match. SB set-aside eligible. DoD agency preference." }, match_tier: "medium", best_cluster_id: "demo-c3", best_cluster_name: "Facilities & Maintenance" },
  { opportunity: { notice_id: "d005", title: "Autonomous UAS Integration for Counter-Drone Defense Systems", solicitation_number: "W912BU-26-R-C001", department: "DEPT OF DEFENSE", sub_tier: "U.S. Army Aviation & Missile Command", office: "AMCOM", naics_code: "334511", naics_description: "Search, Detection, Navigation Equipment Manufacturing", set_aside: "None", opportunity_type: "Sources Sought", posted_date: "02/20/2026", response_deadline: "03/20/2026", description: "Army seeks market research from vendors capable of integrating autonomous UAS platforms with existing C2 systems, incorporating AI-based threat detection, electronic warfare countermeasures, and edge-compute autonomy for contested environments.", place_of_performance: "Redstone Arsenal, AL", estimated_value: null, award_amount: null, link: "https://sam.gov/opp/d005/view", active: true, source: "sam.gov", complexity_tier: "STANDARD", estimated_competition: "OPEN" }, match_score: { overall_score: 50, naics_score: 20, set_aside_score: 0, agency_score: 10, geo_score: 0, semantic_score: 20, explanation: "Related NAICS (4-digit prefix match). DoD agency preference. AI: Strong alignment with autonomous systems and drone capability." }, match_tier: "medium", best_cluster_id: "demo-c1", best_cluster_name: "AI & Robotics" },
  { opportunity: { notice_id: "d006", title: "Subcontract: HVAC Controls Systems Integration – Fort Belvoir Facility", solicitation_number: "", department: "Leidos Federal (Prime on W900KK-24-D-0031)", sub_tier: "", office: "", naics_code: "238220", naics_description: "Plumbing, Heating, and Air-Conditioning Contractors", set_aside: "Small Business", opportunity_type: "Subcontracting Opportunity", posted_date: "02/19/2026", response_deadline: "03/01/2026", description: "Leidos is seeking a small business subcontractor for HVAC controls integration at Fort Belvoir Army Base, VA. Scope includes BAS integration, sensor installation, VAV box commissioning, and BACnet protocol programming. Must hold valid HVAC license in Virginia.", place_of_performance: "Fort Belvoir, VA", estimated_value: 180000, award_amount: null, link: "https://www.sba.gov/opportunity/hvac-fort-belvoir", active: true, source: "subnet", complexity_tier: "SIMPLIFIED", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 55, naics_score: 30, set_aside_score: 15, agency_score: 0, geo_score: 10, semantic_score: 0, explanation: "Exact NAICS match. Partial SB credit. VA geographic match." }, match_tier: "medium", best_cluster_id: "demo-c3", best_cluster_name: "Facilities & Maintenance" },
  { opportunity: { notice_id: "d007", title: "Machine Learning Operations (MLOps) Platform Support – NGA", solicitation_number: "HM047626R0004", department: "DEPT OF DEFENSE", sub_tier: "National Geospatial-Intelligence Agency", office: "NGA Digital Directorate", naics_code: "541512", naics_description: "Computer Systems Design Services", set_aside: "None", opportunity_type: "Presolicitation", posted_date: "02/17/2026", response_deadline: "04/15/2026", description: "NGA seeks support for MLOps platform including model training pipelines on classified cloud, deployment automation, model performance monitoring, data versioning, and team augmentation for geospatial AI applications.", place_of_performance: "Springfield, VA", estimated_value: 12000000, award_amount: null, link: "https://sam.gov/opp/d007/view", active: true, source: "sam.gov", complexity_tier: "MAJOR", estimated_competition: "OPEN" }, match_score: { overall_score: 50, naics_score: 30, set_aside_score: 0, agency_score: 10, geo_score: 10, semantic_score: 0, explanation: "Exact NAICS match. DoD agency. VA geographic match. Full & open competition." }, match_tier: "medium", best_cluster_id: "demo-c1", best_cluster_name: "AI & Robotics" },
  { opportunity: { notice_id: "d009", title: "IT Help Desk and End User Support Services – SSA Baltimore", solicitation_number: "28321826Q0042", department: "SOCIAL SECURITY ADMINISTRATION", sub_tier: "SSA Office of IT", office: "OITT", naics_code: "541513", naics_description: "Computer Facilities Management Services", set_aside: "Total Small Business", opportunity_type: "RFQ", posted_date: "02/10/2026", response_deadline: "03/03/2026", description: "SSA requires Tier 1-2 IT help desk, desktop support, and end-user device management for ~2,400 employees at headquarters in Baltimore, MD.", place_of_performance: "Baltimore, MD", estimated_value: 1200000, award_amount: null, link: "https://sam.gov/opp/d009/view", active: true, source: "sam.gov", complexity_tier: "STANDARD", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 50, naics_score: 30, set_aside_score: 20, agency_score: 0, geo_score: 10, semantic_score: 0, explanation: "Exact NAICS match. SB set-aside eligible. MD geographic match." }, match_tier: "medium", best_cluster_id: "demo-c4", best_cluster_name: "Cloud & IT Services" },
  { opportunity: { notice_id: "d010", title: "Building Groundskeeping and Landscaping – VA Medical Center NJ", solicitation_number: "36C24226Q0301", department: "VETERANS AFFAIRS, DEPARTMENT OF", sub_tier: "Veterans Health Administration", office: "VA NJ Healthcare System", naics_code: "561730", naics_description: "Landscaping Services", set_aside: "Total Small Business", opportunity_type: "RFQ", posted_date: "02/08/2026", response_deadline: "03/07/2026", description: "Grounds maintenance, landscaping, snow removal, and exterior upkeep for the East Orange and Lyons VA Medical Center campuses in New Jersey.", place_of_performance: "East Orange, NJ", estimated_value: 340000, award_amount: null, link: "https://sam.gov/opp/d010/view", active: true, source: "sam.gov", complexity_tier: "SIMPLIFIED", estimated_competition: "RESTRICTED" }, match_score: { overall_score: 40, naics_score: 20, set_aside_score: 20, agency_score: 0, geo_score: 0, semantic_score: 0, explanation: "Related NAICS (4-digit prefix match). SB set-aside eligible." }, match_tier: "low", best_cluster_id: "demo-c3", best_cluster_name: "Facilities & Maintenance" },
  { opportunity: { notice_id: "d011", title: "Sources Sought: Robotic Process Automation (RPA) for FEMA Claims", solicitation_number: "70FBR226SNOT001", department: "HOMELAND SECURITY, DEPARTMENT OF", sub_tier: "FEMA", office: "FEMA IT Directorate", naics_code: "541511", naics_description: "Custom Computer Programming Services", set_aside: "None", opportunity_type: "Sources Sought", posted_date: "02/21/2026", response_deadline: "03/14/2026", description: "FEMA seeks market information from vendors experienced in RPA, AI workflow automation, and intelligent document processing for disaster assistance claims processing, reducing manual review time by 60%.", place_of_performance: "Washington, DC", estimated_value: null, award_amount: null, link: "https://sam.gov/opp/d011/view", active: true, source: "sam.gov", complexity_tier: "STANDARD", estimated_competition: "OPEN" }, match_score: { overall_score: 40, naics_score: 30, set_aside_score: 0, agency_score: 0, geo_score: 10, semantic_score: 0, explanation: "Exact NAICS match. DC geographic match. Full & open competition." }, match_tier: "low", best_cluster_id: "demo-c1", best_cluster_name: "AI & Robotics" },
];

const DEMO_SCOUT = {
  last_run_at: "2026-02-22T06:00:00",
  next_run_at: "2026-02-22T12:00:00",
  total_runs: 12,
  total_fetched_all_runs: 576,
  total_new_all_runs: 31,
  total_tracked_notice_ids: 312,
  last_run_summary: { run_at: "2026-02-22T06:00:00", total_fetched: 48, new_above_threshold: 3, alerts_sent: 1 },
  scheduler_running: true,
};

const SCOUT_RUN_HISTORY_DEMO = [
  { run_at: "2026-02-22T06:00:00", total_fetched: 48, new_count: 3 },
  { run_at: "2026-02-22T00:00:00", total_fetched: 52, new_count: 5 },
  { run_at: "2026-02-21T18:00:00", total_fetched: 44, new_count: 2 },
  { run_at: "2026-02-21T12:00:00", total_fetched: 61, new_count: 8 },
  { run_at: "2026-02-21T06:00:00", total_fetched: 39, new_count: 1 },
  { run_at: "2026-02-21T00:00:00", total_fetched: 55, new_count: 4 },
  { run_at: "2026-02-20T18:00:00", total_fetched: 47, new_count: 3 },
  { run_at: "2026-02-20T12:00:00", total_fetched: 58, new_count: 5 },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function ConnectionBadge({ isLive, oppCount }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${isLive ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" : "bg-amber-500/10 text-amber-400 border-amber-500/30"}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
        {isLive ? "LIVE" : "DEMO"}
      </div>
      {oppCount > 0 && (
        <span className="text-xs text-slate-500">
          {oppCount} opportunit{oppCount === 1 ? "y" : "ies"}
        </span>
      )}
    </div>
  );
}

function NavTab({ label, active, onClick, count }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
        active
          ? "bg-slate-800 text-white border border-slate-700"
          : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
      }`}
    >
      {label}
      {count != null && (
        <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${active ? "bg-slate-700 text-slate-300" : "bg-slate-800 text-slate-500"}`}>
          {count}
        </span>
      )}
    </button>
  );
}

function ScoreBar({ score, max = 100 }) {
  const pct = Math.min((score / max) * 100, 100);
  return (
    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${tierBarColor(score)}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function Pill({ children, className = "" }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${className}`}>
      {children}
    </span>
  );
}

function StatsRow({ opps, clusters, isLive }) {
  const stats = useMemo(() => {
    const high = opps.filter(o => o.match_tier === "high").length;
    const medium = opps.filter(o => o.match_tier === "medium").length;
    const low = opps.filter(o => ["low", "unscored"].includes(o.match_tier)).length;
    const samCount = opps.filter(o => o.opportunity.source === "sam.gov").length;
    const subnetCount = opps.filter(o => o.opportunity.source === "subnet").length;
    const byCluster = clusters.map((c, i) => ({
      name: c.name,
      count: opps.filter(o => o.best_cluster_id === c.id).length,
      color: i,
    })).filter(x => x.count > 0);
    return { total: opps.length, high, medium, low, samCount, subnetCount, byCluster };
  }, [opps, clusters]);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
      {/* Total */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="text-3xl font-bold text-blue-400 tracking-tight">{stats.total}</div>
        <div className="text-xs text-slate-500 mt-1 uppercase tracking-wide">Total Matches</div>
        <div className="flex gap-2 mt-2">
          <span className="text-xs text-slate-500">
            <span className="text-sky-400 font-medium">{stats.samCount}</span> SAM.gov
          </span>
          <span className="text-slate-700">·</span>
          <span className="text-xs text-slate-500">
            <span className="text-orange-400 font-medium">{stats.subnetCount}</span> SubNet
          </span>
        </div>
      </div>
      {/* Tier breakdown */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="flex items-end gap-3">
          <div>
            <div className="text-3xl font-bold text-emerald-400 tracking-tight">{stats.high}</div>
            <div className="text-xs text-slate-500 mt-1 uppercase tracking-wide">High Match</div>
          </div>
          <div className="mb-1">
            <div className="text-xl font-semibold text-amber-400">{stats.medium}</div>
            <div className="text-xs text-slate-500 uppercase tracking-wide">Med</div>
          </div>
          <div className="mb-1">
            <div className="text-xl font-semibold text-slate-500">{stats.low}</div>
            <div className="text-xs text-slate-600 uppercase tracking-wide">Low</div>
          </div>
        </div>
        {stats.total > 0 && (
          <div className="flex h-1 rounded-full overflow-hidden mt-3 gap-px">
            {stats.high > 0 && <div className="bg-emerald-500" style={{ flex: stats.high }} />}
            {stats.medium > 0 && <div className="bg-amber-500" style={{ flex: stats.medium }} />}
            {stats.low > 0 && <div className="bg-slate-600" style={{ flex: stats.low }} />}
          </div>
        )}
      </div>
      {/* By cluster */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 col-span-2 lg:col-span-2">
        <div className="text-xs text-slate-500 uppercase tracking-wide mb-2.5">By Cluster</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {stats.byCluster.map(({ name, count, color }) => (
            <div key={name} className="flex items-center justify-between gap-2">
              <span className={`text-xs font-medium truncate ${CLUSTER_COLORS[color % CLUSTER_COLORS.length].split(" ")[1]}`}>
                {name}
              </span>
              <span className="text-xs text-slate-400 font-semibold shrink-0">{count}</span>
            </div>
          ))}
          {stats.byCluster.length === 0 && (
            <span className="text-xs text-slate-600 col-span-2">No matches yet</span>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterBar({ clusters, filters, setFilters, onSearch, loading }) {
  const TIERS = ["MICRO", "SIMPLIFIED", "STANDARD", "MAJOR"];
  const COMPETITION = ["OPEN", "RESTRICTED", "PARTIAL"];

  function toggleArr(arr, val) {
    return arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val];
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-5 space-y-3">
      {/* Row 1: Cluster filter + search */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs text-slate-500 font-medium uppercase tracking-wide shrink-0">Cluster:</span>
        <button
          onClick={() => setFilters(f => ({ ...f, clusterIds: [] }))}
          className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
            filters.clusterIds.length === 0
              ? "bg-blue-600 text-white border-blue-500"
              : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-600"
          }`}
        >
          All
        </button>
        {clusters.map((c, i) => (
          <button
            key={c.id}
            onClick={() => setFilters(f => ({ ...f, clusterIds: toggleArr(f.clusterIds, c.id) }))}
            className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
              filters.clusterIds.includes(c.id)
                ? `${CLUSTER_COLORS[i % CLUSTER_COLORS.length]}`
                : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-600"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>
      {/* Row 2: Tiers + Competition */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="flex gap-1.5 items-center">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wide mr-1">Tier:</span>
          <button
            onClick={() => setFilters(f => ({ ...f, tiers: [] }))}
            className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all ${
              filters.tiers.length === 0
                ? "bg-blue-600 text-white border-blue-500"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-600"
            }`}
          >
            All
          </button>
          {TIERS.map(t => (
            <button
              key={t}
              onClick={() => setFilters(f => ({ ...f, tiers: toggleArr(f.tiers, t) }))}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-all ${
                filters.tiers.includes(t)
                  ? complexityBadge(t) + " ring-1 ring-inset ring-current/40"
                  : "bg-slate-800 text-slate-500 hover:text-slate-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="w-px h-4 bg-slate-800" />
        <div className="flex gap-1.5 items-center">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wide mr-1">Competition:</span>
          <button
            onClick={() => setFilters(f => ({ ...f, competition: [] }))}
            className={`px-2.5 py-1 rounded text-xs font-semibold border transition-all ${
              filters.competition.length === 0
                ? "bg-blue-600 text-white border-blue-500"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-600"
            }`}
          >
            All
          </button>
          {COMPETITION.map(c => (
            <button
              key={c}
              onClick={() => setFilters(f => ({ ...f, competition: toggleArr(f.competition, c) }))}
              className={`px-2.5 py-1 rounded text-xs font-semibold transition-all ${
                filters.competition.includes(c)
                  ? competitionBadge(c) + " ring-1 ring-inset ring-current/40"
                  : "bg-slate-800 text-slate-500 hover:text-slate-300"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>
      {/* Row 3: Keyword search */}
      <div className="flex gap-2">
        <input
          type="text"
          value={filters.keyword}
          onChange={e => setFilters(f => ({ ...f, keyword: e.target.value }))}
          onKeyDown={e => e.key === "Enter" && onSearch()}
          placeholder="Filter by title, department, NAICS code…"
          className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
        />
        <button
          onClick={onSearch}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          {loading ? "…" : "Search"}
        </button>
      </div>
    </div>
  );
}

function DeadlineChip({ dateStr }) {
  const days = daysUntil(dateStr);
  const label = fmtDate(dateStr);
  if (!label) return <span className="text-slate-600 text-xs">No deadline</span>;
  const urgency = days == null ? "normal" : days < 0 ? "past" : days <= 7 ? "urgent" : days <= 30 ? "soon" : "normal";
  const cls = urgency === "past" ? "text-slate-600 line-through" : urgency === "urgent" ? "text-red-400 font-semibold" : urgency === "soon" ? "text-amber-400" : "text-slate-400";
  return (
    <span className={`text-xs ${cls}`}>
      {label}
      {days != null && days >= 0 && (
        <span className={`ml-1 ${urgency === "urgent" ? "text-red-400" : "text-slate-500"}`}>
          ({days}d)
        </span>
      )}
      {days != null && days < 0 && <span className="ml-1 text-slate-600">(closed)</span>}
    </span>
  );
}

function SourceTag({ source }) {
  return source === "subnet"
    ? <Pill className="bg-orange-500/15 text-orange-400">SubNet</Pill>
    : <Pill className="bg-sky-500/15 text-sky-400">SAM.gov</Pill>;
}

function OpportunityCard({ item, isSelected, onClick, clusterIndex }) {
  const opp = item.opportunity;
  const score = item.match_score;
  const tier = item.match_tier;
  const days = daysUntil(opp.response_deadline);
  const isUrgent = days != null && days >= 0 && days <= 7;

  return (
    <div
      onClick={onClick}
      className={`relative rounded-xl border p-4 cursor-pointer transition-all duration-150 ${tierBg(tier)} ${
        isSelected ? "ring-1 ring-blue-500 border-blue-500/50" : ""
      }`}
    >
      {/* Top row: badges + score */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Pill className={tierBadge(tier)}>{tier.toUpperCase()}</Pill>
          {item.best_cluster_name && (
            <Pill className={clusterColor(clusterIndex)}>{item.best_cluster_name}</Pill>
          )}
          <SourceTag source={opp.source} />
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-blue-400 font-bold text-sm">{score.overall_score.toFixed(0)}</span>
          <span className="text-slate-600 text-xs">/ 100</span>
        </div>
      </div>

      {/* Title */}
      <h3 className="text-sm font-semibold text-white leading-snug mb-1.5 line-clamp-2">
        {opp.title}
      </h3>

      {/* Dept + NAICS */}
      <div className="text-xs text-slate-500 mb-2.5 truncate">
        {opp.department || "Unknown Agency"}
        {opp.naics_code && <span className="text-slate-600"> · NAICS {opp.naics_code}</span>}
        {opp.naics_description && <span className="text-slate-600"> · {opp.naics_description}</span>}
      </div>

      {/* Score bar */}
      <ScoreBar score={score.overall_score} />

      {/* Bottom row: tier badges + deadline + value + link */}
      <div className="flex items-center justify-between gap-2 mt-2.5 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Pill className={complexityBadge(opp.complexity_tier)}>{opp.complexity_tier}</Pill>
          <Pill className={competitionBadge(opp.estimated_competition)}>{opp.estimated_competition}</Pill>
          {opp.estimated_value && (
            <span className="text-xs text-slate-500 font-mono">{fmtValue(opp.estimated_value)}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {isUrgent && <span className="text-xs text-red-400 font-semibold animate-pulse">⚠ {days}d left</span>}
          <DeadlineChip dateStr={opp.response_deadline} />
          {opp.link && (
            <a
              href={opp.link}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="text-xs text-blue-500 hover:text-blue-400 font-medium"
            >
              View →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function ScoreBreakdown({ score }) {
  const dims = [
    { label: "NAICS", val: score.naics_score, max: 30 },
    { label: "Set-Aside", val: score.set_aside_score, max: 20 },
    { label: "Agency", val: score.agency_score, max: 10 },
    { label: "Geography", val: score.geo_score, max: 10 },
    { label: "AI Semantic", val: score.semantic_score, max: 30 },
  ];
  return (
    <div className="space-y-2.5">
      {dims.map(d => (
        <div key={d.label}>
          <div className="flex justify-between mb-1">
            <span className="text-xs text-slate-500">{d.label}</span>
            <span className={`text-xs font-mono font-semibold ${d.val > 0 ? "text-blue-400" : "text-slate-600"}`}>
              {d.val}/{d.max}
            </span>
          </div>
          <ScoreBar score={d.val} max={d.max} />
        </div>
      ))}
      {score.explanation && (
        <p className="text-xs text-slate-500 mt-3 pt-3 border-t border-slate-800 leading-relaxed">
          {score.explanation}
        </p>
      )}
    </div>
  );
}

function DetailPanel({ item, onClose, clusterIndex }) {
  const opp = item.opportunity;
  const score = item.match_score;
  const tier = item.match_tier;

  const metaRows = [
    { label: "Solicitation #", value: opp.solicitation_number },
    { label: "Department", value: opp.department },
    { label: "Sub-tier", value: opp.sub_tier },
    { label: "Office", value: opp.office },
    { label: "NAICS", value: opp.naics_code ? `${opp.naics_code}${opp.naics_description ? " — " + opp.naics_description : ""}` : null },
    { label: "Set-Aside", value: opp.set_aside || "Full & Open" },
    { label: "Type", value: opp.opportunity_type },
    { label: "Posted", value: fmtDate(opp.posted_date) },
    { label: "Deadline", value: opp.response_deadline ? `${fmtDate(opp.response_deadline)} (${daysUntil(opp.response_deadline)}d remaining)` : null },
    { label: "Location", value: opp.place_of_performance },
    { label: "Est. Value", value: opp.estimated_value ? fmtValue(opp.estimated_value) : null },
    { label: "Source", value: opp.source === "subnet" ? "SBA SubNet (subcontract)" : "SAM.gov (prime)" },
  ].filter(r => r.value);

  return (
    <div className="h-full flex flex-col bg-slate-900 border-l border-slate-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 p-5 border-b border-slate-800 shrink-0">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Pill className={tierBadge(tier)}>{tier.toUpperCase()} MATCH</Pill>
            {item.best_cluster_name && (
              <Pill className={clusterColor(clusterIndex)}>{item.best_cluster_name}</Pill>
            )}
            <SourceTag source={opp.source} />
          </div>
          <h2 className="text-base font-bold text-white leading-snug">{opp.title}</h2>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-3xl font-bold tracking-tight ${score.overall_score >= 70 ? "text-emerald-400" : score.overall_score >= 50 ? "text-amber-400" : "text-slate-500"}`}>
            {score.overall_score.toFixed(0)}
          </div>
          <div className="text-xs text-slate-600">/ 100</div>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Complexity + competition */}
        <div className="flex gap-2 flex-wrap">
          <Pill className={complexityBadge(opp.complexity_tier)}>{opp.complexity_tier}</Pill>
          <Pill className={competitionBadge(opp.estimated_competition)}>{opp.estimated_competition}</Pill>
          {opp.estimated_value && (
            <Pill className="bg-slate-800 text-slate-300">{fmtValue(opp.estimated_value)}</Pill>
          )}
          {opp.response_deadline && (
            <span className="self-center"><DeadlineChip dateStr={opp.response_deadline} /></span>
          )}
        </div>

        {/* Score breakdown */}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">Score Breakdown</h3>
          <ScoreBreakdown score={score} />
        </div>

        {/* Metadata */}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">Details</h3>
          <dl className="space-y-2">
            {metaRows.map(({ label, value }) => (
              <div key={label} className="grid grid-cols-[120px_1fr] gap-2 text-xs">
                <dt className="text-slate-500 pt-0.5">{label}</dt>
                <dd className="text-slate-300 leading-relaxed">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {/* Description */}
        {opp.description && (
          <div>
            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">Description</h3>
            <p className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
              {opp.description}
            </p>
          </div>
        )}

        {/* Actions */}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">Quick Actions</h3>
          <div className="space-y-2">
            {opp.link && (
              <a
                href={opp.link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 w-full px-3 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <span>View Full Solicitation</span>
                <span className="ml-auto">↗</span>
              </a>
            )}
            <button
              onClick={() => navigator.clipboard?.writeText(opp.link || opp.notice_id)}
              className="flex items-center gap-2 w-full px-3 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-lg transition-colors"
            >
              Copy Link
            </button>
          </div>
        </div>
      </div>

      {/* Close button */}
      <div className="shrink-0 p-3 border-t border-slate-800">
        <button
          onClick={onClose}
          className="w-full py-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          Close panel
        </button>
      </div>
    </div>
  );
}

function ClustersView({ clusters, opportunities }) {
  const clusterIndex = Object.fromEntries(clusters.map((c, i) => [c.id, i]));
  const matchCountByCluster = useMemo(() =>
    Object.fromEntries(clusters.map(c => [
      c.id,
      opportunities.filter(o => o.best_cluster_id === c.id).length,
    ])),
    [clusters, opportunities]
  );

  if (clusters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-600">
        <div className="text-4xl mb-4">🧩</div>
        <div className="font-medium text-slate-500">No clusters configured</div>
        <div className="text-sm mt-2">POST to /api/v1/clusters to create your first capability cluster</div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {clusters.map((c) => {
        const idx = clusterIndex[c.id] ?? 0;
        const matchCount = matchCountByCluster[c.id] ?? 0;
        const cleared = c.team_roster.filter(m => m.clearance).length;
        return (
          <div key={c.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-colors">
            {/* Header */}
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className={`text-base font-bold ${CLUSTER_COLORS[idx % CLUSTER_COLORS.length].split(" ")[1]}`}>
                  {c.name}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-2 leading-relaxed">{c.capability_description}</p>
              </div>
              {matchCount > 0 && (
                <div className="text-right shrink-0">
                  <div className="text-2xl font-bold text-blue-400">{matchCount}</div>
                  <div className="text-xs text-slate-600">matches</div>
                </div>
              )}
            </div>

            {/* NAICS codes */}
            <div className="mb-3">
              <div className="text-xs text-slate-600 mb-1.5 uppercase tracking-wide">NAICS</div>
              <div className="flex flex-wrap gap-1.5">
                {c.naics_codes.map(n => (
                  <span key={n} className="font-mono text-xs px-2 py-0.5 bg-slate-800 text-slate-300 rounded border border-slate-700">{n}</span>
                ))}
              </div>
            </div>

            {/* Certifications */}
            <div className="mb-3">
              <div className="text-xs text-slate-600 mb-1.5 uppercase tracking-wide">Certifications</div>
              <div className="flex flex-wrap gap-1.5">
                {c.certifications.length > 0
                  ? c.certifications.map(cert => (
                    <Pill key={cert} className={certBadge(cert)}>{cert}</Pill>
                  ))
                  : <span className="text-xs text-slate-600">None listed</span>
                }
              </div>
            </div>

            {/* Team roster */}
            <div className="border-t border-slate-800 pt-3 mt-3">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs text-slate-600 uppercase tracking-wide">Team Roster</div>
                <div className="text-xs text-slate-500">
                  {c.team_roster.length} member{c.team_roster.length !== 1 ? "s" : ""}
                  {cleared > 0 && <span className="ml-2 text-yellow-500">· {cleared} cleared</span>}
                </div>
              </div>
              {c.team_roster.length > 0 ? (
                <div className="space-y-1.5">
                  {c.team_roster.map((m, mi) => (
                    <div key={mi} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 font-semibold text-xs shrink-0">
                          {m.name.charAt(0)}
                        </div>
                        <span className="text-slate-300 font-medium">{m.name}</span>
                        <span className="text-slate-500">{m.role}</span>
                      </div>
                      {m.clearance && (
                        <Pill className="bg-yellow-500/15 text-yellow-400">{m.clearance}</Pill>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-slate-600">No team members listed</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ScoutView({ status, onRun, running, isLive }) {
  const runs = status?.runs || SCOUT_RUN_HISTORY_DEMO;
  const isScheduled = status?.scheduler_running ?? false;

  return (
    <div className="max-w-3xl space-y-5">
      {/* Status card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-base font-bold text-white">Scout Agent</h2>
              <Pill className={isScheduled ? "bg-emerald-500/20 text-emerald-400" : "bg-slate-800 text-slate-500"}>
                {isScheduled ? "● Running" : "○ Stopped"}
              </Pill>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              Scans SAM.gov + SBA SubNet every 6 hours for new opportunities. Scores against all
              capability clusters and sends email alerts when high-scoring matches are found.
            </p>
          </div>
          <button
            onClick={onRun}
            disabled={running}
            className="shrink-0 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors flex items-center gap-2"
          >
            {running ? (
              <>
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Scanning…
              </>
            ) : (
              "▶ Run Now"
            )}
          </button>
        </div>

        {/* Timing grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 pt-5 border-t border-slate-800">
          {[
            { label: "Last Run", value: fmtDateTime(status?.last_run_at) },
            { label: "Next Run", value: fmtDateTime(status?.next_run_at) },
            { label: "Total Runs", value: status?.total_runs ?? "—" },
            { label: "Tracked IDs", value: status?.total_tracked_notice_ids?.toLocaleString() ?? "—" },
          ].map(({ label, value }) => (
            <div key={label}>
              <div className="text-xs text-slate-600 mb-0.5">{label}</div>
              <div className="text-sm font-semibold text-slate-300">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Last run summary */}
      {status?.last_run_summary && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Last Run Summary</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Fetched", value: status.last_run_summary.total_fetched, color: "text-blue-400" },
              { label: "New Matches", value: status.last_run_summary.new_above_threshold, color: "text-emerald-400" },
              { label: "Alerts Sent", value: status.last_run_summary.alerts_sent, color: status.last_run_summary.alerts_sent > 0 ? "text-amber-400" : "text-slate-600" },
              { label: "Run At", value: fmtDateTime(status.last_run_summary.run_at), color: "text-slate-400" },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <div className="text-xs text-slate-600 mb-0.5">{label}</div>
                <div className={`text-lg font-bold ${color}`}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Run history */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Run History</h3>
        {runs.length === 0 ? (
          <p className="text-sm text-slate-600">No runs yet. Click "Run Now" to trigger the first scan.</p>
        ) : (
          <div className="space-y-2">
            {runs.slice(0, 10).map((run, i) => (
              <div key={i} className="flex items-center gap-4 py-2.5 border-b border-slate-800 last:border-0">
                <div className="text-xs font-mono text-slate-400 w-44 shrink-0">{fmtDateTime(run.run_at)}</div>
                <div className="flex-1 flex items-center gap-3 text-xs">
                  <span className="text-slate-500">{run.total_fetched} fetched</span>
                  <span className="text-slate-700">·</span>
                  <span className={run.new_count > 0 ? "text-emerald-400 font-semibold" : "text-slate-600"}>
                    {run.new_count} new
                  </span>
                </div>
                {run.new_count > 0 && (
                  <div className="flex items-center gap-1">
                    {Array.from({ length: Math.min(run.new_count, 8) }).map((_, j) => (
                      <div key={j} className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    ))}
                    {run.new_count > 8 && <span className="text-xs text-slate-600">+{run.new_count - 8}</span>}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pipeline overview */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-4">Autonomous Pipeline</h3>
        <div className="space-y-2">
          {[
            { n: 1, name: "Scout", status: "live", desc: "Scans SAM.gov + SubNet every 6h, scores against clusters, sends alerts" },
            { n: 2, name: "Qualifier", status: "planned", desc: "Deep-qualifies flagged opportunities, extracts RFP requirements, go/no-go scoring" },
            { n: 3, name: "Drafter", status: "planned", desc: "Generates proposal drafts section by section using company knowledge base (Claude)" },
            { n: 4, name: "Reviewer", status: "planned", desc: "Red-teams proposals with GPT-5 + Gemini, merges feedback, returns revision instructions" },
            { n: 5, name: "Submitter", status: "planned", desc: "Packages and submits final proposals" },
            { n: 6, name: "Tracker", status: "planned", desc: "Monitors amendments, Q&A, and award announcements" },
          ].map(agent => (
            <div key={agent.n} className={`flex items-start gap-3 p-3 rounded-lg ${agent.status === "live" ? "bg-emerald-500/5 border border-emerald-500/20" : "bg-slate-950 border border-slate-800"}`}>
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 mt-0.5 ${agent.status === "live" ? "bg-emerald-500 text-slate-900" : "bg-slate-800 text-slate-600"}`}>
                {agent.n}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold ${agent.status === "live" ? "text-emerald-400" : "text-slate-500"}`}>
                    {agent.name}
                  </span>
                  {agent.status === "live"
                    ? <Pill className="bg-emerald-500/20 text-emerald-400 text-xs">Live</Pill>
                    : <Pill className="bg-slate-800 text-slate-600 text-xs">Planned</Pill>
                  }
                </div>
                <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{agent.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4 h-28">
          <div className="flex gap-2 mb-3">
            <div className="h-4 w-12 bg-slate-800 rounded" />
            <div className="h-4 w-20 bg-slate-800 rounded" />
          </div>
          <div className="h-4 bg-slate-800 rounded w-3/4 mb-2" />
          <div className="h-3 bg-slate-800 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("opportunities");
  const [isLive, setIsLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [clusters, setClusters] = useState([]);
  const [opportunities, setOpportunities] = useState([]);
  const [scoutStatus, setScoutStatus] = useState(null);
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [scoutRunning, setScoutRunning] = useState(false);
  const [scoutNotice, setScoutNotice] = useState(null);
  const [error, setError] = useState(null);
  const [samWarning, setSamWarning] = useState(null);
  const [filters, setFilters] = useState({
    clusterIds: [],
    tiers: [],
    competition: [],
    keyword: "",
  });

  // Build cluster index for colors (stable across renders)
  const clusterIndexMap = useMemo(
    () => Object.fromEntries(clusters.map((c, i) => [c.id, i])),
    [clusters]
  );

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      try {
        const health = await fetch("http://localhost:8000/health", { signal: AbortSignal.timeout(3000) });
        if (!health.ok) throw new Error("unhealthy");
        setIsLive(true);

        // Load clusters
        const clRes = await fetch(`${API}/clusters`);
        const cls = await clRes.json();
        setClusters(cls.length > 0 ? cls : DEMO_CLUSTERS);

        const activeClusters = cls.length > 0 ? cls : DEMO_CLUSTERS;

        // Search with all cluster IDs
        const qs = activeClusters.map(c => `cluster_ids=${c.id}`).join("&");
        const opRes = await fetch(`${API}/opportunities/search?${qs}&include_subnet=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ limit: 100, min_score: 0 }),
        });
        if (!opRes.ok) {
          setSamWarning("SAM.gov temporarily unavailable — showing SubNet results only.");
        }
        const opps = await opRes.json().catch(() => []);
        setOpportunities(Array.isArray(opps) ? opps : []);

        // Load scout status
        try {
          const scRes = await fetch(`${API}/scout/status`);
          const sc = await scRes.json();
          setScoutStatus(sc);
        } catch { setScoutStatus(DEMO_SCOUT); }
      } catch {
        // Demo mode
        setIsLive(false);
        setClusters(DEMO_CLUSTERS);
        setOpportunities(DEMO_OPPS);
        setScoutStatus(DEMO_SCOUT);
      }
      setLoading(false);
    };
    init();
  }, []);

  // ── Filtered opportunities ────────────────────────────────────────────────
  const displayOpps = useMemo(() => {
    let result = opportunities;
    if (filters.clusterIds.length > 0) {
      result = result.filter(o => filters.clusterIds.includes(o.best_cluster_id));
    }
    if (filters.tiers.length > 0) {
      result = result.filter(o => filters.tiers.includes(o.opportunity.complexity_tier));
    }
    if (filters.competition.length > 0) {
      result = result.filter(o => filters.competition.includes(o.opportunity.estimated_competition));
    }
    if (filters.keyword) {
      const kw = filters.keyword.toLowerCase();
      result = result.filter(o =>
        o.opportunity.title.toLowerCase().includes(kw) ||
        (o.opportunity.department || "").toLowerCase().includes(kw) ||
        (o.opportunity.naics_code || "").includes(kw)
      );
    }
    return result;
  }, [opportunities, filters]);

  // ── Keyword search (server-side re-fetch) ────────────────────────────────
  const handleSearch = useCallback(async () => {
    if (!isLive) return;
    setLoading(true);
    setSamWarning(null);
    try {
      const qs = clusters.map(c => `cluster_ids=${c.id}`).join("&");
      const body = { limit: 100, min_score: 0, keywords: filters.keyword || undefined };
      const opRes = await fetch(`${API}/opportunities/search?${qs}&include_subnet=true`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!opRes.ok) {
        setSamWarning("SAM.gov temporarily unavailable — showing SubNet results only.");
      }
      const opps = await opRes.json().catch(() => []);
      setOpportunities(Array.isArray(opps) ? opps : []);
    } catch (e) {
      setError("Search failed — check backend connection.");
    }
    setLoading(false);
  }, [isLive, clusters, filters.keyword]);

  // ── Scout manual trigger ──────────────────────────────────────────────────
  const handleRunScout = useCallback(async () => {
    if (!isLive) {
      setScoutNotice("Demo mode — Scout would scan SAM.gov + SubNet and email results.");
      setTimeout(() => setScoutNotice(null), 4000);
      return;
    }
    setScoutRunning(true);
    setScoutNotice(null);
    try {
      const res = await fetch(`${API}/scout/run`, { method: "POST" });
      const result = await res.json();
      const n = result.new_above_threshold ?? 0;
      setScoutNotice(`Scout complete: ${result.total_fetched} fetched, ${n} new match${n !== 1 ? "es" : ""} found.`);
      // Refresh scout status
      const scRes = await fetch(`${API}/scout/status`);
      setScoutStatus(await scRes.json());
      // Refresh opportunities
      if (n > 0) {
        const qs = clusters.map(c => `cluster_ids=${c.id}`).join("&");
        const opRes = await fetch(`${API}/opportunities/search?${qs}&include_subnet=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ limit: 100, min_score: 0 }),
        });
        if (!opRes.ok) {
          setSamWarning("SAM.gov temporarily unavailable — showing SubNet results only.");
        }
        const opps = await opRes.json().catch(() => []);
        setOpportunities(Array.isArray(opps) ? opps : []);
      }
    } catch {
      setScoutNotice("Scout run failed — check backend.");
    }
    setScoutRunning(false);
  }, [isLive, clusters]);

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* ── Header ── */}
      <header className="shrink-0 border-b border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950 px-6 py-4">
        <div className="max-w-screen-2xl mx-auto flex items-center justify-between gap-4">
          {/* Logo + name */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white text-base font-bold select-none">G</div>
            <div>
              <div className="text-sm font-bold text-white tracking-tight">GovContract AI</div>
              <div className="text-xs text-slate-600 leading-none">Contract Discovery & Pursuit</div>
            </div>
          </div>

          {/* Nav tabs */}
          <nav className="flex items-center gap-1">
            <NavTab label="Opportunities" active={tab === "opportunities"} onClick={() => setTab("opportunities")} count={displayOpps.length || undefined} />
            <NavTab label="Clusters" active={tab === "clusters"} onClick={() => setTab("clusters")} count={clusters.length || undefined} />
            <NavTab label="Scout Agent" active={tab === "scout"} onClick={() => setTab("scout")} />
          </nav>

          {/* Connection status */}
          <ConnectionBadge isLive={isLive} oppCount={displayOpps.length} />
        </div>
      </header>

      {/* ── Toast notifications ── */}
      {samWarning && (
        <div className="shrink-0 px-6 py-2.5 text-sm flex items-center justify-between border-b bg-amber-500/10 border-amber-500/25 text-amber-300">
          <div className="flex items-center gap-2">
            <span className="text-amber-400">⚠</span>
            <span>{samWarning}</span>
          </div>
          <button onClick={() => setSamWarning(null)} className="text-xs opacity-60 hover:opacity-100 ml-6">✕</button>
        </div>
      )}
      {(scoutNotice || error) && (
        <div className={`shrink-0 px-6 py-3 text-sm flex items-center justify-between border-b ${
          error
            ? "bg-red-500/10 border-red-500/20 text-red-400"
            : "bg-blue-500/10 border-blue-500/20 text-blue-300"
        }`}>
          <span>{error || scoutNotice}</span>
          <button onClick={() => { setError(null); setScoutNotice(null); }} className="text-xs opacity-60 hover:opacity-100 ml-6">✕</button>
        </div>
      )}

      {/* ── Main content ── */}
      <main className="flex-1 overflow-hidden">
        <div className="max-w-screen-2xl mx-auto h-full px-6 py-5">

          {/* Opportunities tab */}
          {tab === "opportunities" && (
            <div className="h-full flex flex-col">
              <StatsRow opps={displayOpps} clusters={clusters} isLive={isLive} />
              <FilterBar
                clusters={clusters}
                filters={filters}
                setFilters={setFilters}
                onSearch={handleSearch}
                loading={loading}
              />
              {/* Cards + detail split */}
              <div className={`flex-1 overflow-hidden grid gap-4 transition-all duration-300 ${selectedOpp ? "grid-cols-[1fr_460px]" : "grid-cols-1"}`}>
                {/* Card list */}
                <div className="overflow-y-auto space-y-2.5 pr-1">
                  {loading ? (
                    <LoadingSkeleton />
                  ) : displayOpps.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center">
                      <div className="text-4xl mb-4">🎯</div>
                      <div className="text-base font-semibold text-slate-500">No opportunities match your filters</div>
                      <div className="text-sm text-slate-600 mt-2">
                        {isLive ? "Try widening your filters or running the Scout agent." : "Switch to live mode to search SAM.gov."}
                      </div>
                    </div>
                  ) : (
                    displayOpps.map(item => (
                      <OpportunityCard
                        key={item.opportunity.notice_id}
                        item={item}
                        isSelected={selectedOpp?.opportunity.notice_id === item.opportunity.notice_id}
                        onClick={() => setSelectedOpp(
                          selectedOpp?.opportunity.notice_id === item.opportunity.notice_id ? null : item
                        )}
                        clusterIndex={clusterIndexMap[item.best_cluster_id] ?? 0}
                      />
                    ))
                  )}
                </div>

                {/* Detail panel */}
                {selectedOpp && (
                  <div className="overflow-hidden rounded-xl border border-slate-800 shadow-2xl">
                    <DetailPanel
                      item={selectedOpp}
                      onClose={() => setSelectedOpp(null)}
                      clusterIndex={clusterIndexMap[selectedOpp.best_cluster_id] ?? 0}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Clusters tab */}
          {tab === "clusters" && (
            <div className="overflow-y-auto h-full">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h1 className="text-lg font-bold text-white">Capability Clusters</h1>
                  <p className="text-sm text-slate-500 mt-0.5">
                    Distinct areas of expertise — each scored independently against every opportunity
                  </p>
                </div>
                <a
                  href="http://localhost:8000/docs#/default/create_cluster_api_v1_clusters_post"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors border border-slate-700"
                >
                  + Add via API
                </a>
              </div>
              <ClustersView clusters={clusters} opportunities={opportunities} />
            </div>
          )}

          {/* Scout tab */}
          {tab === "scout" && (
            <div className="overflow-y-auto h-full">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h1 className="text-lg font-bold text-white">Scout Agent</h1>
                  <p className="text-sm text-slate-500 mt-0.5">Agent 1 of 6 in the autonomous contract pursuit pipeline</p>
                </div>
              </div>
              <ScoutView
                status={scoutStatus}
                onRun={handleRunScout}
                running={scoutRunning}
                isLive={isLive}
              />
            </div>
          )}

        </div>
      </main>
    </div>
  );
}
