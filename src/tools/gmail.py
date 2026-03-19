import os
import smtplib
from email.message import EmailMessage
from fastapi import HTTPException
from dotenv import load_dotenv
import asyncio
from googletrans import Translator, LANGUAGES

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

class GmailSender:
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'mail.namanskshetty.in')
        self.smtp_port = int(os.getenv('SMTP_PORT', 465))
        self.smtp_username = os.getenv('SMTP_USERNAME', 'support@namanskshetty.in')
        self.smtp_password = os.getenv('SMTP_PASSWORD')

    def _send_email_smtp(self, message):
        if not self.smtp_password:
            raise RuntimeError("SMTP_PASSWORD is not set in the environment variables.")
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)
            print("Successfully sent email via SMTP.")
            return True
        except Exception as e:
            print(f"SMTP Error: {e}")
            raise HTTPException(status_code=500, detail=f"Email failed: {str(e)}")

    async def _translate_text(self, text, language):
        lang_code = language.strip().lower()
        if not lang_code or lang_code == "en" or lang_code == "english":
            return text

        LANGUAGE_NAMES = {v: k for k, v in LANGUAGES.items()}
        lang_code = LANGUAGE_NAMES.get(lang_code, lang_code)

        try:
            translator = Translator()
            result = await asyncio.wait_for(
                translator.translate(text, dest=lang_code),
                timeout=5.0
            )
            return result.text
        except Exception as e:
            print(f"Translation failed for '{lang_code}': {e}. Falling back to English.")
            return text

    async def send_email(self, sender, to, name, role, hire_date, language="en"):
        print("In mail")
        lang = language.strip().lower()

        subject         = await self._translate_text("Welcome to the Revolution: You're officially part of SeedSense!", lang)
        greeting        = await self._translate_text("Thank you for joining SeedSense. We are thrilled to have you as part of our mission to digitize and revolutionize the way we grow and connect.", lang)
        account_details = await self._translate_text("Your Account Details:", lang)
        label_name      = await self._translate_text("Name:", lang)
        label_email     = await self._translate_text("Email:", lang)
        label_role      = await self._translate_text("Role:", lang)
        label_joined    = await self._translate_text("Joined On:", lang)
        whats_next      = await self._translate_text("What's next? You can now access your dashboard, explore, and collaborate with other visionaries.", lang)
        login_btn       = await self._translate_text("Login to your account", lang)
        security_tip    = await self._translate_text("For your protection, we recommend that you change your password immediately after your first login. You can do this easily using the \"Forgot Password?\" link on the login page.", lang)
        security_label  = await self._translate_text("Security Tip:", lang)
        footer1         = await self._translate_text("You received this email because you signed up for the digital revolution.", lang)
        welcome_heading = await self._translate_text("Welcome to the Digital Revolution!", lang)

        content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333333;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; margin-top: 20px; margin-bottom: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0px 4px 10px rgba(0,0,0,0.05);">
        <tr>
            <td align="center" style="padding: 40px 0 30px 0; background-color: #2e7d32;">
                <h1 style="margin: 0; color: #ffffff; font-size: 28px; letter-spacing: 1px;">SeedSense</h1>
            </td>
        </tr>
        <tr>
            <td style="padding: 40px 30px;">
                <h2 style="margin: 0 0 20px 0; color: #2e7d32; font-size: 24px;">{welcome_heading}</h2>
                <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
                    Hi <strong>{name}</strong>, <br><br>
                    {greeting}
                </p>
                <div style="background-color: #f9f9f9; border-left: 4px solid #2e7d32; padding: 20px; margin-bottom: 30px;">
                    <h3 style="margin: 0 0 15px 0; font-size: 18px; color: #555;">{account_details}</h3>
                    <table width="100%" style="font-size: 15px; line-height: 2;">
                        <tr>
                            <td width="30%"><strong>{label_name}</strong></td>
                            <td>{name}</td>
                        </tr>
                        <tr>
                            <td><strong>{label_email}</strong></td>
                            <td>{to}</td>
                        </tr>
                        <tr>
                            <td><strong>{label_role}</strong></td>
                            <td><span style="background-color: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 4px; font-size: 13px; font-weight: bold;">{role}</span></td>
                        </tr>
                        <tr>
                            <td><strong>{label_joined}</strong></td>
                            <td>{str(hire_date)}</td>
                        </tr>
                    </table>
                </div>
                <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">{whats_next}</p>
                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                        <td align="center">
                            <a href="https://agrinow-ui.vercel.app/" style="background-color: #2e7d32; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">{login_btn}</a>
                        </td>
                    </tr>
                </table>
                <div style="margin-top: 30px; padding: 15px; background-color: #fff9c4; border-radius: 5px; text-align: center;">
                    <p style="margin: 0; font-size: 14px; color: #f57f17;">
                        <strong>🔒 {security_label}</strong> {security_tip}
                    </p>
                </div>
            </td>
        </tr>
        <tr>
            <td style="padding: 30px; background-color: #eeeeee; text-align: center; font-size: 12px; color: #777777;">
                <p style="margin: 0 0 10px 0;">&copy; 2026 SeedSense | Bengaluru, India</p>
                <p style="margin: 0;">{footer1}</p>
            </td>
        </tr>
    </table>
</body>
</html>"""

        message = EmailMessage()
        message.set_content(content, subtype='html')
        message['To'] = to
        message['From'] = self.smtp_username # always use authenticating user as sender to avoid relay issues
        message['Subject'] = subject

        self._send_email_smtp(message)
        return "sent"

    async def send_reset_email(self, sender, to, name, reset_link):
        subject = "Reset Your SeedSense Password"
        content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333333;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; margin-top: 20px; margin-bottom: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0px 4px 10px rgba(0,0,0,0.05);">
        <tr>
            <td align="center" style="padding: 40px 0 30px 0; background-color: #2e7d32;">
                <h1 style="margin: 0; color: #ffffff; font-size: 28px; letter-spacing: 1px;">SeedSense</h1>
            </td>
        </tr>
        <tr>
            <td style="padding: 40px 30px;">
                <h2 style="margin: 0 0 20px 0; color: #2e7d32; font-size: 24px;">Password Reset Request</h2>
                <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
                    Hi <strong>{name}</strong>, <br><br>
                    We received a request to reset your password for your <strong>SeedSense</strong> account. Click the button below to set a new password.
                </p>
                <div style="background-color: #fff3e0; border-left: 4px solid #ff9800; padding: 15px 20px; margin-bottom: 25px;">
                    <p style="margin: 0; font-size: 14px; color: #e65100;">
                        ⏰ This link will expire in <strong>15 minutes</strong>. If you didn't request this, you can safely ignore this email.
                    </p>
                </div>
                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                        <td align="center">
                            <a href="{reset_link}" style="background-color: #2e7d32; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">🔑 Reset My Password</a>
                        </td>
                    </tr>
                </table>
                <p style="margin: 25px 0 0 0; line-height: 1.6; font-size: 13px; color: #777777;">
                    If the button doesn't work, copy and paste this link into your browser:<br>
                    <span style="color: #2e7d32; word-break: break-all;">{reset_link}</span>
                </p>
            </td>
        </tr>
        <tr>
            <td style="padding: 30px; background-color: #eeeeee; text-align: center; font-size: 12px; color: #777777;">
                <p style="margin: 0 0 10px 0;">&copy; 2026 SeedSense | Bengaluru, India</p>
                <p style="margin: 0;">You received this email because a password reset was requested for your account.</p>
            </td>
        </tr>
    </table>
</body>
</html>"""

        message = EmailMessage()
        message.set_content(content, subtype='html')
        message['To'] = to
        message['From'] = self.smtp_username
        message['Subject'] = subject

        self._send_email_smtp(message)
        return "sent"

    async def send_attendance_email(
        self,
        sender,
        to,
        name,
        date_str,
        time_str,
        action_type,
        language="en",
        notes=None,
        latitude=None,
        longitude=None,
        compliance=None,
        distance_km=None,
    ):
        lang = language.strip().lower()
        is_checkin = action_type.lower() in ("check-in", "checkin", "check in")

        # Header color: green for check-in, indigo for check-out
        header_bg  = "#1b5e20" if is_checkin else "#1a237e"
        accent_clr = "#2e7d32" if is_checkin else "#283593"
        action_icon = "🟢" if is_checkin else "🔵"

        # Compliance badge
        compliance_html = ""
        if compliance:
            badge_map = {
                "compliant":     ("#e8f5e9", "#2e7d32", "✅ Compliant"),
                "non_compliant": ("#fff3e0", "#e65100", "⚠️ Far from Site"),
                "no_location":   ("#f3e5f5", "#6a1b9a", "📍 No GPS Data"),
                "no_site":       ("#eceff1", "#546e7a", "🏗️ No Site Assigned"),
            }
            bg, fg, label = badge_map.get(compliance, ("#f5f5f5", "#555", compliance))
            dist_text = f" &nbsp;·&nbsp; {distance_km} km from nearest site" if distance_km is not None else ""
            compliance_html = f"""
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                                <span style="font-size: 13px; color: #888;">Site Compliance</span>
                            </td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                                <span style="background:{bg}; color:{fg}; padding:3px 10px; border-radius:12px; font-size:13px; font-weight:600;">{label}</span>
                                <span style="font-size:12px; color:#999;">{dist_text}</span>
                            </td>
                        </tr>"""

        # GPS row
        gps_html = ""
        if latitude is not None and longitude is not None:
            maps_url = f"https://www.google.com/maps?q={latitude},{longitude}"
            gps_html = f"""
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                                <span style="font-size: 13px; color: #888;">Location</span>
                            </td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                                <a href="{maps_url}" style="color:{accent_clr}; font-size:13px; text-decoration:none;">
                                    📌 {latitude:.5f}, {longitude:.5f}
                                </a>
                            </td>
                        </tr>"""

        # Notes row
        notes_html = ""
        if notes:
            notes_html = f"""
                        <tr>
                            <td style="padding: 8px 0;">
                                <span style="font-size: 13px; color: #888;">Notes</span>
                            </td>
                            <td style="padding: 8px 0;">
                                <span style="font-size:13px; color:#444; font-style:italic;">"{notes}"</span>
                            </td>
                        </tr>"""

        subject = await self._translate_text(f"SeedSense: {action_type} Recorded — {date_str}", lang)

        content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background-color:#f0f2f5;color:#333;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600"
        style="border-collapse:collapse;background:#fff;margin:24px auto;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
            <td align="center" style="padding:36px 30px 28px;background:{header_bg};">
                <p style="margin:0 0 4px 0;color:rgba(255,255,255,0.7);font-size:12px;letter-spacing:2px;text-transform:uppercase;">SeedSense Field Operations</p>
                <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;letter-spacing:0.5px;">
                    {action_icon} {action_type} Confirmed
                </h1>
                <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">{date_str}</p>
            </td>
        </tr>

        <!-- Body -->
        <tr>
            <td style="padding:32px 36px 24px;">
                <p style="margin:0 0 24px;font-size:16px;color:#444;line-height:1.6;">
                    Hi <strong style="color:#222;">{name}</strong>,<br>
                    Your <strong>{action_type}</strong> has been recorded at <strong>{time_str}</strong>.
                </p>

                <!-- Details card -->
                <div style="background:#fafafa;border:1px solid #eee;border-radius:10px;padding:20px 24px;margin-bottom:24px;">
                    <p style="margin:0 0 14px;font-size:11px;font-weight:700;color:#999;letter-spacing:1.5px;text-transform:uppercase;">Attendance Details</p>
                    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                        <tr>
                            <td style="padding:8px 0;border-bottom:1px solid #f0f0f0;width:38%;">
                                <span style="font-size:13px;color:#888;">Date</span>
                            </td>
                            <td style="padding:8px 0;border-bottom:1px solid #f0f0f0;">
                                <span style="font-size:13px;font-weight:600;color:#222;">{date_str}</span>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:8px 0;border-bottom:1px solid #f0f0f0;">
                                <span style="font-size:13px;color:#888;">Time</span>
                            </td>
                            <td style="padding:8px 0;border-bottom:1px solid #f0f0f0;">
                                <span style="font-size:13px;font-weight:600;color:#222;">{time_str}</span>
                            </td>
                        </tr>
                        {compliance_html}
                        {gps_html}
                        {notes_html}
                    </table>
                </div>

                <p style="margin:0;font-size:13px;color:#aaa;text-align:center;">
                    This is an automated confirmation. No action is required.
                </p>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
            <td style="padding:18px 36px;background:#f7f7f7;border-top:1px solid #eee;text-align:center;">
                <p style="margin:0 0 4px;font-size:12px;color:#aaa;">&copy; 2026 SeedSense &nbsp;|&nbsp; Bengaluru, India</p>
                <p style="margin:0;font-size:11px;color:#ccc;">Attendance confirmation — {action_type} &nbsp;·&nbsp; {date_str}</p>
            </td>
        </tr>
    </table>
</body>
</html>"""

        message = EmailMessage()
        message.set_content(content, subtype='html')
        message['To'] = to
        message['From'] = self.smtp_username
        message['Subject'] = subject

        try:
            self._send_email_smtp(message)
            return "sent"
        except Exception as e:
            print(f"Error sending attendance email: {e}")
            return None

    async def send_site_assignment_email(self, sender, to, name, site_name, assigned_date, language="en"):
        lang = language.strip().lower()

        subject         = await self._translate_text("SeedSense: New Site Assignment Alert", lang)
        greeting        = await self._translate_text(f"You have been assigned to a new site: {site_name}.", lang)
        account_details = await self._translate_text("Assignment Details:", lang)
        label_name      = await self._translate_text("Name:", lang)
        label_site      = await self._translate_text("Site:", lang)
        label_date      = await self._translate_text("Assigned Date:", lang)
        footer1         = await self._translate_text("You received this email because you were assigned to a new site.", lang)
        welcome_heading = await self._translate_text("Site Assignment Notification", lang)

        content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333333;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; margin-top: 20px; margin-bottom: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0px 4px 10px rgba(0,0,0,0.05);">
        <tr>
            <td align="center" style="padding: 30px 0; background-color: #2e7d32;">
                <h1 style="margin: 0; color: #ffffff; font-size: 26px; letter-spacing: 1px;">SeedSense</h1>
            </td>
        </tr>
        <tr>
            <td style="padding: 30px;">
                <h2 style="margin: 0 0 15px 0; color: #2e7d32; font-size: 22px;">{welcome_heading}</h2>
                <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
                    Hi <strong>{name}</strong>, <br><br>
                    {greeting}
                </p>
                <div style="background-color: #e8f5e9; border-left: 4px solid #2e7d32; padding: 15px; margin-bottom: 25px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 16px; color: #2e7d32;">{account_details}</h3>
                    <table width="100%" style="font-size: 14px; line-height: 1.8;">
                        <tr>
                            <td width="30%"><strong>{label_name}</strong></td>
                            <td>{name}</td>
                        </tr>
                        <tr>
                            <td><strong>{label_site}</strong></td>
                            <td><strong>{site_name}</strong></td>
                        </tr>
                        <tr>
                            <td><strong>{label_date}</strong></td>
                            <td>{assigned_date}</td>
                        </tr>
                    </table>
                </div>
            </td>
        </tr>
        <tr>
            <td style="padding: 20px; background-color: #eeeeee; text-align: center; font-size: 12px; color: #777777;">
                <p style="margin: 0 0 5px 0;">&copy; 2026 SeedSense | Bengaluru, India</p>
                <p style="margin: 0;">{footer1}</p>
            </td>
        </tr>
    </table>
</body>
</html>"""

        message = EmailMessage()
        message.set_content(content, subtype='html')
        message['To'] = to
        message['From'] = self.smtp_username
        message['Subject'] = subject

        try:
            self._send_email_smtp(message)
            return "sent"
        except Exception as e:
            print(f"Error sending site assignment email: {e}")
            return None

if __name__ == '__main__':
    gmail_client = GmailSender()
    asyncio.run(gmail_client.send_email(
        sender="support@namanskshetty.in",
        to="test@example.com",
        name="Test User",
        role="Admin",
        hire_date="2026-03-10",
        language="en"
    ))