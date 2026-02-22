"""
Email alert service using SendGrid.

Sends an HTML digest of new high-scoring opportunities grouped by capability cluster.
Degrades gracefully when SENDGRID_API_KEY or ALERT_EMAIL_TO is not configured.
"""
import logging
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.models.schemas import ScoredOpportunity

logger = logging.getLogger(__name__)


def _build_html(opportunities: list[ScoredOpportunity], run_at: str) -> str:
    """Build HTML email body grouping opportunities by cluster."""

    # Group by cluster
    by_cluster: dict[str, list[ScoredOpportunity]] = {}
    for opp in opportunities:
        cluster_name = opp.best_cluster_name or "General"
        by_cluster.setdefault(cluster_name, []).append(opp)

    date_str = datetime.utcnow().strftime("%B %d, %Y")

    rows_html = ""
    for cluster_name, opps in by_cluster.items():
        rows_html += f"""
        <tr>
          <td colspan="5" style="background:#1e3a5f;color:#fff;padding:8px 12px;
                                  font-weight:bold;font-size:13px;">
            {cluster_name}
          </td>
        </tr>"""
        for s in opps:
            o = s.opportunity
            score_color = (
                "#16a34a" if s.match_tier == "high"
                else "#d97706" if s.match_tier == "medium"
                else "#6b7280"
            )
            deadline = o.response_deadline or "—"
            value = f"${o.estimated_value:,.0f}" if o.estimated_value else "—"
            link = o.link or "#"
            rows_html += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:10px 12px;max-width:260px;">
            <a href="{link}" style="color:#1d4ed8;text-decoration:none;font-weight:500;">
              {o.title[:80]}{"…" if len(o.title) > 80 else ""}
            </a><br>
            <span style="color:#6b7280;font-size:12px;">{o.department or "—"}</span>
          </td>
          <td style="padding:10px 12px;color:#374151;font-size:13px;">{o.naics_code or "—"}</td>
          <td style="padding:10px 12px;color:#374151;font-size:13px;">{value}</td>
          <td style="padding:10px 12px;color:#374151;font-size:13px;">{deadline}</td>
          <td style="padding:10px 12px;text-align:center;">
            <span style="background:{score_color};color:#fff;border-radius:4px;
                         padding:2px 8px;font-size:12px;font-weight:bold;">
              {s.match_score.overall_score:.0f}
            </span>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f9fafb;margin:0;padding:0;">
  <div style="max-width:700px;margin:24px auto;background:#fff;
               border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">

    <!-- Header -->
    <div style="background:#1e3a5f;padding:20px 24px;">
      <h1 style="color:#fff;margin:0;font-size:20px;">GovContract AI</h1>
      <p style="color:#93c5fd;margin:4px 0 0;font-size:14px;">
        New opportunity alert — {date_str}
      </p>
    </div>

    <!-- Summary -->
    <div style="padding:16px 24px;background:#eff6ff;border-bottom:1px solid #bfdbfe;">
      <p style="margin:0;font-size:14px;color:#1e40af;">
        <strong>{len(opportunities)} new opportunities</strong> matched your capability
        clusters since the last scan.
      </p>
    </div>

    <!-- Table -->
    <div style="padding:16px 24px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#f3f4f6;color:#374151;">
            <th style="padding:8px 12px;text-align:left;">Opportunity</th>
            <th style="padding:8px 12px;text-align:left;">NAICS</th>
            <th style="padding:8px 12px;text-align:left;">Value</th>
            <th style="padding:8px 12px;text-align:left;">Deadline</th>
            <th style="padding:8px 12px;text-align:center;">Score</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>

    <!-- Footer -->
    <div style="padding:16px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;">
        Sent by GovContract AI · Scout scan at {run_at}
      </p>
    </div>
  </div>
</body>
</html>"""


async def send_opportunity_digest(
    opportunities: list[ScoredOpportunity],
    run_at: str,
) -> bool:
    """
    Send an HTML email digest of new opportunities via SendGrid.

    Returns True if email was sent, False if skipped (missing config) or failed.
    """
    settings = get_settings()

    if not settings.sendgrid_api_key:
        logger.info("Email alerts disabled: SENDGRID_API_KEY not set")
        return False

    if not settings.alert_email_to:
        logger.info("Email alerts disabled: ALERT_EMAIL_TO not set")
        return False

    if not opportunities:
        logger.info("Email alert skipped: no new opportunities to report")
        return False

    try:
        import sendgrid  # type: ignore
        from sendgrid.helpers.mail import Mail, Content  # type: ignore
    except ImportError:
        logger.warning(
            "sendgrid package not installed. Run: pip install sendgrid. "
            "Email alert skipped."
        )
        return False

    subject = f"GovContract AI: {len(opportunities)} new opportunities found"
    html_body = _build_html(opportunities, run_at)

    message = Mail(
        from_email="alerts@govcontract.ai",
        to_emails=settings.alert_email_to,
        subject=subject,
        html_content=Content("text/html", html_body),
    )

    try:
        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        response = sg.send(message)
        if response.status_code in (200, 202):
            logger.info(
                f"Email digest sent to {settings.alert_email_to} "
                f"({len(opportunities)} opportunities)"
            )
            return True
        else:
            logger.error(
                f"SendGrid returned unexpected status {response.status_code}"
            )
            return False
    except Exception as e:
        logger.error(f"Failed to send email digest: {e}")
        return False
