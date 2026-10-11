import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

def mask_email(email: str) -> str:
    """Masks email for audit logs without leaking full address (e.g. v***1@gmail.com)."""
    if not email or "@" not in email:
        return "***"
    local_part, domain = email.split("@", 1)
    if len(local_part) <= 2:
        masked_local = local_part[0] + "***"
    else:
        masked_local = local_part[0] + "***" + local_part[-1]
    return f"{masked_local}@{domain}"


from app.services.verification_service import mask_registration_number


class DemoMockEmailAdapter:
    """
    Demo / Mock email dispatch adapter.
    Captures verification messages in an in-memory test buffer.
    Outbound SMTP transmission is strictly disabled by default for demos.
    Never logs plaintext verification codes or passwords.
    """

    # In-memory buffer for testing and demo verification
    _test_inbox: List[Dict[str, Any]] = []

    @classmethod
    def clear_test_inbox(cls):
        cls._test_inbox.clear()

    @classmethod
    def get_test_inbox(cls) -> List[Dict[str, Any]]:
        return list(cls._test_inbox)

    @classmethod
    async def send_verification_otp(
        cls,
        to_email: str,
        registration_number: str,
        otp_code: str,
        expires_minutes: int = 10,
    ) -> bool:
        """
        Processes registration OTP dispatch in demo/test mode.
        Masks all PII in logs; never logs plaintext OTP codes or passwords.
        """
        masked = mask_email(to_email)
        masked_roll = mask_registration_number(registration_number)
        logger.info(f"Initiating registration OTP dispatch to {masked} (Roll: {masked_roll}) [Demo Mode: Outbound SMTP Disabled]")

        # Record event in demo test buffer
        cls._test_inbox.append({
            "to_email": to_email,
            "registration_number": registration_number,
            "otp_code": otp_code,
            "timestamp": datetime.now(timezone.utc),
            "expires_minutes": expires_minutes,
        })

        if not settings.EMAIL_DISPATCH_ENABLED or not settings.SMTP_HOST:
            logger.info(f"Email dispatch completed via DemoMockEmailAdapter for {masked} [Simulated].")
            return True

        # Production Live SMTP Dispatch
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"VFSTR Adaptive Interview Platform - Verification Code"
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = to_email

            text_content = (
                f"Hello,\n\n"
                f"Your verification code for Adaptive Interview Intelligence (VFSTR) is: {otp_code}\n\n"
                f"This code will expire in {expires_minutes} minutes.\n"
                f"If you did not request this registration, please ignore this email.\n\n"
                f"Vignan's Foundation for Science, Technology and Research (VFSTR)\n"
            )

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                <h2 style="color: #4f46e5;">Adaptive Interview Intelligence – VFSTR</h2>
                <p>Hello,</p>
                <p>Your single-use verification code to complete your student registration is:</p>
                <div style="background-color: #f1f5f9; padding: 16px; border-radius: 6px; text-align: center; font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #1e293b;">
                    {otp_code}
                </div>
                <p style="margin-top: 16px; color: #64748b; font-size: 14px;">
                    This code will expire in <strong>{expires_minutes} minutes</strong>. It can only be used once.
                </p>
                <p style="color: #64748b; font-size: 14px;">
                    If you did not request this registration, please disregard this email.
                </p>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
                <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                    Vignan's Foundation for Science, Technology and Research (Deemed to be University)
                </p>
            </div>
            """

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f"Live SMTP email successfully dispatched to {masked}.")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch live email to {masked}: {str(e)}")
            return False

# Backward-compatible alias
EmailService = DemoMockEmailAdapter
