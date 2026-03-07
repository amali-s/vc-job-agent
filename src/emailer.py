"""Email sender using SendGrid or Gmail SMTP."""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from .models import MatchResult, ScrapeSummary

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends job digest emails via SendGrid or Gmail SMTP."""

    def __init__(self):
        """Initialize with available email provider."""
        self.to_email = os.environ.get("EMAIL_TO")
        if not self.to_email:
            raise ValueError("EMAIL_TO not set")

        # Check for Gmail first, then SendGrid
        self.gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
        self.gmail_user = os.environ.get("GMAIL_USER") or self.to_email

        self.sendgrid_key = os.environ.get("SENDGRID_API_KEY")
        self.sendgrid_from = os.environ.get("EMAIL_FROM")

        if self.gmail_password:
            self.provider = "gmail"
            logger.info("Using Gmail SMTP for email delivery")
        elif self.sendgrid_key and self.sendgrid_from:
            self.provider = "sendgrid"
            from sendgrid import SendGridAPIClient
            self.client = SendGridAPIClient(api_key=self.sendgrid_key)
            logger.info("Using SendGrid for email delivery")
        else:
            raise ValueError(
                "No email provider configured. Set GMAIL_APP_PASSWORD + GMAIL_USER, "
                "or SENDGRID_API_KEY + EMAIL_FROM"
            )

    def send_daily_digest(
        self,
        matches: list[MatchResult],
        scrape_summaries: list[ScrapeSummary] | None = None,
        dry_run: bool = False,
    ) -> bool:
        """Send daily job digest email."""
        if not matches:
            logger.info("No matches to send")
            return True

        subject = f"🎯 {len(matches)} Product Designer Jobs - {datetime.now().strftime('%b %d, %Y')}"
        html_content = self._generate_html(matches, scrape_summaries)

        if dry_run:
            logger.info(f"DRY RUN: Would send email to {self.to_email}")
            logger.info(f"Subject: {subject}")
            logger.info(f"Jobs: {len(matches)}")
            return True

        if self.provider == "gmail":
            return self._send_gmail(subject, html_content)
        else:
            return self._send_sendgrid(subject, html_content)

    def _send_gmail(self, subject: str, html_content: str) -> bool:
        """Send email via Gmail SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.gmail_user
            msg["To"] = self.to_email

            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.gmail_user, self.gmail_password)
                server.sendmail(self.gmail_user, self.to_email, msg.as_string())

            logger.info(f"Email sent successfully via Gmail to {self.to_email}")
            return True

        except Exception as e:
            logger.error(f"Gmail error: {e}")
            return False

    def _send_sendgrid(self, subject: str, html_content: str) -> bool:
        """Send email via SendGrid."""
        try:
            from sendgrid.helpers.mail import Mail, Email, To, HtmlContent

            message = Mail(
                from_email=Email(self.sendgrid_from),
                to_emails=To(self.to_email),
                subject=subject,
                html_content=HtmlContent(html_content),
            )

            response = self.client.send(message)

            if response.status_code in (200, 201, 202):
                logger.info(f"Email sent successfully via SendGrid to {self.to_email}")
                return True
            else:
                logger.error(f"SendGrid error: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False

    def _generate_html(
        self,
        matches: list[MatchResult],
        scrape_summaries: list[ScrapeSummary] | None = None,
    ) -> str:
        """Generate HTML email content."""
        job_cards = "\n".join(self._generate_job_card(m) for m in matches)
        summary_html = self._generate_scrape_summary_html(scrape_summaries) if scrape_summaries else ""

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Job Digest</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
    <div style="background-color: #fff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <h1 style="color: #1a1a1a; font-size: 24px; margin-bottom: 8px; font-weight: 600;">
            Daily Job Digest
        </h1>
        <p style="color: #666; margin-bottom: 24px; font-size: 14px;">
            {datetime.now().strftime('%B %d, %Y')} &bull; {len(matches)} matches found
        </p>

        {job_cards}

        {summary_html}

        <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;">

        <p style="color: #999; font-size: 12px; text-align: center;">
            Powered by VC Job Agent &bull; AI-matched product designer opportunities
        </p>
    </div>
</body>
</html>
"""

    def _format_rank_delta(self, delta: int | None) -> str:
        """Format rank delta for email display."""
        if delta is None:
            return '<span style="color: #8b5cf6; font-size: 11px;">NEW</span>'
        if delta > 0:
            return f'<span style="color: #10b981; font-size: 11px;">↑{delta}</span>'
        if delta < 0:
            return f'<span style="color: #ef4444; font-size: 11px;">↓{abs(delta)}</span>'
        return '<span style="color: #888; font-size: 11px;">—</span>'

    def _format_match_delta(self, delta: int | None) -> str:
        """Format match % delta for email display."""
        if delta is None:
            return ""
        if delta > 0:
            return f' <span style="color: #10b981; font-size: 11px;">↑{delta}%</span>'
        if delta < 0:
            return f' <span style="color: #ef4444; font-size: 11px;">↓{abs(delta)}%</span>'
        return ""

    def _generate_job_card(self, match: MatchResult) -> str:
        """Generate HTML for a single job card."""
        job = match.job

        # Color for match percentage text (no background badge)
        if match.match_percentage >= 80:
            match_color = "#10b981"  # Green
        elif match.match_percentage >= 70:
            match_color = "#3b82f6"  # Blue
        else:
            match_color = "#f59e0b"  # Amber

        # Rank and delta line
        rank_html = ""
        if match.rank > 0:
            rank_delta_str = self._format_rank_delta(match.rank_delta)
            match_delta_str = self._format_match_delta(match.match_delta)
            rank_html = f"""
            <p style="font-size: 12px; color: #888; margin: 4px 0 0 0;">
                Rank: #{match.rank} {rank_delta_str} &bull; Match: {match.match_percentage}%{match_delta_str}
            </p>
            """

        # Company bio section
        company_bio_html = ""
        if match.company_bio:
            company_bio_html = f"""
            <p style="font-size: 13px; color: #555; margin: 8px 0 4px 0;">
                {match.company_bio}
            </p>
            """

        # Series and posting date metadata line
        meta_parts = []
        if match.company_series:
            meta_parts.append(match.company_series)
        if job.posted_date:
            meta_parts.append(f"Posted {job.posted_date.strftime('%b %d, %Y')}")
        meta_html = ""
        if meta_parts:
            meta_html = f"""
            <p style="font-size: 12px; color: #888; margin: 4px 0;">
                {' &bull; '.join(meta_parts)}
            </p>
            """

        # Salary range
        salary_html = ""
        if job.salary_range:
            salary_html = f"""
            <p style="font-size: 13px; color: #1a1a1a; margin: 8px 0 4px 0; font-weight: 500;">
                💰 {job.salary_range}
            </p>
            """

        # Matched keywords as inline tags
        keywords_html = ""
        if match.matched_keywords:
            tags = "".join(
                f'<span style="display: inline-block; background-color: #f0f0f0; color: #555; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px 4px 2px 0;">{kw}</span>'
                for kw in match.matched_keywords[:8]
            )
            keywords_html = f"""
            <div style="margin-top: 10px;">
                <span style="color: #888; font-size: 11px;">Matched: </span>
                {tags}
            </div>
            """

        return f"""
        <div style="background-color: #fafafa; border-radius: 8px; padding: 20px; margin-bottom: 16px; border: 1px solid #eee;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div>
                    <h2 style="font-size: 16px; font-weight: 600; color: #1a1a1a; margin: 0 0 4px 0;">
                        {job.title}
                    </h2>
                    <p style="font-size: 14px; color: #666; margin: 0;">
                        {job.company}
                    </p>
                </div>
                <span style="color: {match_color}; font-size: 16px; font-weight: 700; white-space: nowrap;">
                    {match.match_percentage}%
                </span>
            </div>

            {rank_html}

            <p style="font-size: 13px; color: #888; margin: 8px 0 4px 0;">
                📍 {job.location} &bull; 🏢 {job.source}
            </p>

            {meta_html}
            {company_bio_html}
            {salary_html}
            {keywords_html}

            <a href="{job.url}" style="display: inline-block; margin-top: 16px; background-color: #1a1a1a; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 500;">
                Apply Now →
            </a>
        </div>
        """

    def _generate_scrape_summary_html(self, summaries: list[ScrapeSummary]) -> str:
        """Generate HTML table for per-source scrape summary (Task 4)."""
        if not summaries:
            return ""

        total_all = sum(s.total for s in summaries)
        new_all = sum(s.new for s in summaries)
        seen_all = sum(s.previously_seen for s in summaries)

        rows = ""
        for s in summaries:
            rows += f"""
            <tr>
                <td style="padding: 6px 10px; font-size: 12px; color: #555; border-bottom: 1px solid #f0f0f0;">{s.source}</td>
                <td style="padding: 6px 10px; font-size: 12px; color: #555; border-bottom: 1px solid #f0f0f0; text-align: center;">{s.total}</td>
                <td style="padding: 6px 10px; font-size: 12px; color: #10b981; border-bottom: 1px solid #f0f0f0; text-align: center; font-weight: 600;">{s.new}</td>
                <td style="padding: 6px 10px; font-size: 12px; color: #888; border-bottom: 1px solid #f0f0f0; text-align: center;">{s.previously_seen}</td>
            </tr>
            """

        return f"""
        <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0 24px 0;">

        <h3 style="font-size: 14px; font-weight: 600; color: #1a1a1a; margin-bottom: 12px;">
            Scrape Summary
        </h3>

        <table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
            <thead>
                <tr style="background-color: #fafafa;">
                    <th style="padding: 8px 10px; font-size: 11px; color: #888; text-align: left; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Source</th>
                    <th style="padding: 8px 10px; font-size: 11px; color: #888; text-align: center; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Total</th>
                    <th style="padding: 8px 10px; font-size: 11px; color: #888; text-align: center; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">New</th>
                    <th style="padding: 8px 10px; font-size: 11px; color: #888; text-align: center; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Seen</th>
                </tr>
            </thead>
            <tbody>
                {rows}
                <tr style="background-color: #fafafa; font-weight: 600;">
                    <td style="padding: 8px 10px; font-size: 12px; color: #1a1a1a;">Total</td>
                    <td style="padding: 8px 10px; font-size: 12px; color: #1a1a1a; text-align: center;">{total_all}</td>
                    <td style="padding: 8px 10px; font-size: 12px; color: #10b981; text-align: center;">{new_all}</td>
                    <td style="padding: 8px 10px; font-size: 12px; color: #888; text-align: center;">{seen_all}</td>
                </tr>
            </tbody>
        </table>
        """


def send_digest(
    matches: list[MatchResult],
    scrape_summaries: list[ScrapeSummary] | None = None,
    dry_run: bool = False,
) -> bool:
    """Convenience function to send job digest."""
    sender = EmailSender()
    return sender.send_daily_digest(matches, scrape_summaries=scrape_summaries, dry_run=dry_run)
