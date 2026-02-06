"""SMTP email service for sending daily summaries and weekly reports."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import client_config, settings

logger = logging.getLogger(__name__)


class EmailService:
    """Send HTML emails via SMTP (Gmail)."""

    def __init__(self):
        self.smtp_config = client_config.smtp_config
        self.enabled = self.smtp_config.get("enabled", False)

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """Send an email. Returns True on success."""
        if not self.enabled:
            logger.info(f"Email disabled — would send to {to}: {subject}")
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_config.get("from_email", settings.smtp_username)
        msg["To"] = to

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(
                self.smtp_config["host"],
                self.smtp_config["port"],
            ) as server:
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(msg["From"], [to], msg.as_string())

            logger.info(f"Email sent to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False

    def send_daily_summary(
        self,
        new_leads: int,
        letters_pending: int,
        letters_sent: int,
        qr_scans: int,
    ) -> bool:
        """Send the daily summary email."""
        html = f"""
        <html>
        <body style="font-family: Georgia, serif; color: #1a365d;">
            <h2 style="color: #1a365d;">Daily Lead Summary — {client_config.company_name}</h2>
            <table style="border-collapse: collapse; width: 100%;">
                <tr style="background: #f0f4f8;">
                    <td style="padding: 12px; border: 1px solid #e2e8f0;"><strong>New Leads</strong></td>
                    <td style="padding: 12px; border: 1px solid #e2e8f0; font-size: 24px;">{new_leads}</td>
                </tr>
                <tr>
                    <td style="padding: 12px; border: 1px solid #e2e8f0;"><strong>Letters Pending Approval</strong></td>
                    <td style="padding: 12px; border: 1px solid #e2e8f0; font-size: 24px;">{letters_pending}</td>
                </tr>
                <tr style="background: #f0f4f8;">
                    <td style="padding: 12px; border: 1px solid #e2e8f0;"><strong>Letters Sent</strong></td>
                    <td style="padding: 12px; border: 1px solid #e2e8f0; font-size: 24px;">{letters_sent}</td>
                </tr>
                <tr>
                    <td style="padding: 12px; border: 1px solid #e2e8f0;"><strong>QR Code Scans</strong></td>
                    <td style="padding: 12px; border: 1px solid #e2e8f0; font-size: 24px;">{qr_scans}</td>
                </tr>
            </table>
            <p style="margin-top: 20px;">
                <a href="{settings.frontend_url}" style="color: #2c5282;">View Dashboard →</a>
            </p>
        </body>
        </html>
        """
        return self.send_email(
            to=client_config.reporting["daily_summary_email"],
            subject=f"Daily Lead Summary — {new_leads} new leads",
            html_body=html,
        )

    def send_weekly_report(self, stats: dict) -> bool:
        """Send the weekly performance report."""
        html = f"""
        <html>
        <body style="font-family: Georgia, serif; color: #1a365d;">
            <h2>Weekly Performance Report — {client_config.company_name}</h2>
            <table style="border-collapse: collapse; width: 100%;">
                <tr style="background: #1a365d; color: white;">
                    <th style="padding: 12px; text-align: left;">Metric</th>
                    <th style="padding: 12px; text-align: right;">Value</th>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">Leads Generated</td>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">{stats.get('leads_generated', 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">Letters Sent</td>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">{stats.get('letters_sent', 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">QR Scans</td>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">{stats.get('qr_scans', 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">Conversion Rate</td>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">{stats.get('conversion_rate', 0):.1f}%</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">Pipeline Value</td>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">£{stats.get('pipeline_value', 0):,.0f}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">Cost per Lead</td>
                    <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">£{stats.get('cost_per_lead', 0):.2f}</td>
                </tr>
            </table>
            <p style="margin-top: 20px;">
                <a href="{settings.frontend_url}" style="color: #2c5282;">View Full Dashboard →</a>
            </p>
        </body>
        </html>
        """
        return self.send_email(
            to=client_config.reporting["weekly_report_email"],
            subject=f"Weekly Report — {stats.get('leads_generated', 0)} leads, £{stats.get('pipeline_value', 0):,.0f} pipeline",
            html_body=html,
        )
