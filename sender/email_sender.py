"""
sender/email_sender.py — send job application email with CV attached
Uses Gmail SMTP (or any SMTP). For Gmail, use an App Password:
  https://myaccount.google.com/apppasswords
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_application(
    to_email: str,
    job_title: str,
    company: str,
    cover_letter: str,
    cv_path: str,
    sender_email: str,
    sender_password: str,
    sender_name: str,
) -> bool:
    """
    Send a job application email.
    Returns True on success, False on failure.
    """

    if not os.path.exists(cv_path):
        log.error(f"CV not found at: {cv_path}")
        return False

    subject = f"Application for {job_title} — {sender_name}"

    # Build email body (plain text + HTML versions)
    html_body = _build_html(cover_letter, sender_name)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = formataddr((sender_name, sender_email))
    msg["To"]      = to_email

    msg.attach(MIMEText(cover_letter, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # Attach CV PDF
    with open(cv_path, "rb") as f:
        cv_filename = os.path.basename(cv_path)
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header(
            "Content-Disposition", "attachment",
            filename=f"{sender_name} — CV.pdf"
        )
        msg.attach(attachment)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        log.info(f"Application sent to {to_email} for {job_title} @ {company}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error("SMTP auth failed — check SENDER_EMAIL and SENDER_PASSWORD (use Gmail App Password)")
        return False
    except Exception as e:
        log.error(f"Failed to send email to {to_email}: {e}")
        return False


def _build_html(cover_letter: str, sender_name: str) -> str:
    paragraphs = "".join(
        f"<p style='margin:0 0 12px 0'>{p.strip()}</p>"
        for p in cover_letter.split("\n\n")
        if p.strip()
    )
    return f"""
<html><body style="font-family:Arial,sans-serif;font-size:15px;color:#222;max-width:620px;margin:0 auto;padding:24px">
{paragraphs}
<hr style="border:none;border-top:1px solid #ddd;margin:24px 0"/>
<p style="font-size:13px;color:#666">CV attached as PDF · Sent by {sender_name}</p>
</body></html>
""".strip()
