import logging
import smtplib
import ssl
import socket
import asyncio
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from app.core.config import settings
from app.services.verification_service import mask_registration_number

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


class DemoMockEmailAdapter:
    """
    Email dispatch service with dual-mode operational support:
    1. Demo/Test Mode: Records dispatched messages in in-memory test buffer.
    2. Live Production SMTP: Executes non-blocking delivery in a worker thread pool,
       supporting Port 587 (STARTTLS), Port 465 (SMTPS), and automatic Gmail port fallback.
    Never logs plaintext verification codes, passwords, or SMTP secrets.
    """

    # In-memory buffer for testing and demo verification
    _test_inbox: List[Dict[str, Any]] = []
    _last_error: Optional[str] = None

    @classmethod
    def clear_test_inbox(cls):
        cls._test_inbox.clear()
        cls._last_error = None

    @classmethod
    def get_test_inbox(cls) -> List[Dict[str, Any]]:
        return list(cls._test_inbox)

    @classmethod
    def get_last_error(cls) -> Optional[str]:
        return cls._last_error

    @classmethod
    def _dispatch_sync_smtp(cls, msg: MIMEMultipart, masked: str) -> bool:
        """
        Synchronous SMTP transmission executed inside a worker thread via asyncio.to_thread.
        Guarantees that the main asyncio event loop is never blocked by socket I/O.
        """
        cls._last_error = None
        host = settings.SMTP_HOST
        port = settings.SMTP_PORT or 587
        username = settings.SMTP_USERNAME
        password = settings.SMTP_PASSWORD
        timeout = float(settings.SMTP_TIMEOUT_SECONDS or 5.0)
        use_ssl = bool(settings.SMTP_USE_SSL or port == 465)

        if password:
            password = password.strip()
            if "gmail" in (host or "").lower():
                password = password.replace(" ", "")

        def _attempt_send(target_port: int, ssl_mode: bool) -> Tuple[bool, Optional[str]]:
            t_start = time.perf_counter()
            ssl_ctx = ssl.create_default_context()
            proto_str = "SMTPS (SSL)" if ssl_mode else "SMTP+STARTTLS"
            try:
                if ssl_mode:
                    server = smtplib.SMTP_SSL(host, target_port, context=ssl_ctx, timeout=timeout)
                else:
                    server = smtplib.SMTP(host, target_port, timeout=timeout)

                with server:
                    server.ehlo()
                    if not ssl_mode and settings.SMTP_USE_TLS:
                        server.starttls(context=ssl_ctx)
                        server.ehlo()
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)

                elapsed_ms = (time.perf_counter() - t_start) * 1000
                logger.info(
                    f"Live SMTP email successfully dispatched to {masked} "
                    f"via {host}:{target_port} ({proto_str}) in {elapsed_ms:.1f}ms."
                )
                return True, None
            except smtplib.SMTPAuthenticationError as auth_err:
                elapsed_ms = (time.perf_counter() - t_start) * 1000
                logger.error(
                    f"SMTP authentication rejected by {host}:{target_port} after {elapsed_ms:.1f}ms. "
                    f"Check SMTP credentials / Google App Password. Code: {auth_err.smtp_code}"
                )
                return False, "SMTP authentication rejected. Please verify email credentials."
            except (socket.timeout, TimeoutError):
                elapsed_ms = (time.perf_counter() - t_start) * 1000
                logger.warning(
                    f"SMTP connection to {host}:{target_port} ({proto_str}) timed out after {elapsed_ms:.1f}ms."
                )
                return False, f"SMTP connection to {host}:{target_port} timed out."
            except (smtplib.SMTPConnectError, ConnectionRefusedError, OSError) as conn_err:
                elapsed_ms = (time.perf_counter() - t_start) * 1000
                logger.warning(
                    f"SMTP connection to {host}:{target_port} ({proto_str}) failed after {elapsed_ms:.1f}ms: {conn_err}"
                )
                return False, f"SMTP network connection failed on port {target_port}."
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t_start) * 1000
                logger.error(
                    f"Unexpected SMTP error communicating with {host}:{target_port} after {elapsed_ms:.1f}ms: {type(exc).__name__}: {exc}"
                )
                return False, f"SMTP delivery error: {type(exc).__name__}"

        # 1. Primary Attempt with configured port & mode
        success, err = _attempt_send(port, use_ssl)
        if success:
            return True

        # 2. Automatic Fallback for Gmail between Port 587 and Port 465
        # If port 587 failed due to network/timeout (common on cloud egress), try SSL on port 465
        is_gmail = "gmail" in (host or "").lower()
        if is_gmail and not success and "authentication rejected" not in (err or "").lower():
            fallback_port = 465 if port != 465 else 587
            fallback_ssl = (fallback_port == 465)
            logger.info(f"Attempting automatic Gmail fallback to port {fallback_port} (SSL={fallback_ssl})...")
            fb_success, fb_err = _attempt_send(fallback_port, fallback_ssl)
            if fb_success:
                return True
            err = fb_err or err

        cls._last_error = err
        return False

    @classmethod
    async def send_verification_otp(
        cls,
        to_email: str,
        registration_number: str,
        otp_code: str,
        expires_minutes: int = 10,
    ) -> bool:
        """
        Dispatches verification OTP code.
        - When EMAIL_DISPATCH_ENABLED is False (development/testing): records in in-memory test buffer.
        - When EMAIL_DISPATCH_ENABLED is True (production): executes non-blocking thread delivery.
        Masks all PII in logs; never logs plaintext OTP codes or passwords.
        """
        masked = mask_email(to_email)
        masked_roll = mask_registration_number(registration_number)
        logger.info(f"Initiating registration OTP dispatch to {masked} (Roll: {masked_roll})")

        # Record in test buffer (for unit testing and verification)
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

        # Live SMTP delivery in worker thread preventing asyncio event loop stalls
        max_ceiling = float(settings.SMTP_TIMEOUT_SECONDS or 5.0) * 2.0 + 1.0
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "VFSTR Adaptive Interview Platform - Verification Code"
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

            return await asyncio.wait_for(
                asyncio.to_thread(cls._dispatch_sync_smtp, msg, masked),
                timeout=max_ceiling
            )
        except asyncio.TimeoutError:
            cls._last_error = "Email dispatch timed out on all attempted connection ports."
            logger.error(f"Email dispatch to {masked} exceeded thread ceiling ({max_ceiling:.1f}s).")
            return False
        except Exception as exc:
            cls._last_error = str(exc)
            logger.error(f"Failed to initiate email dispatch for {masked}: {exc}")
            return False

# Backward-compatible alias
EmailService = DemoMockEmailAdapter
