import os
import base64
import json
import ast
import re
from email.message import EmailMessage
from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv
import asyncio
from googletrans import Translator, LANGUAGES

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

class GmailSender:
    def __init__(self, token_file=None, client_secret_file=None, port=8080):
        self.scopes = ['https://www.googleapis.com/auth/gmail.send']
        self.token_data = token_file or os.getenv('GMAIL_TOKEN_FILE')
        self.client_secret_data = client_secret_file or os.getenv('GMAIL_CLIENT_SECRET_FILE')
        self.port = port
        self.service = self._get_gmail_service()

    def _clean_json_str(self, s):
        """Normalize JSON string — handles single quotes, bare keys, outer wrapping."""
        if not s: return s
        s = s.strip()

        # Strip outer single quotes if wrapped
        if s.startswith("'") and s.endswith("'"):
            s = s[1:-1]

        # Try json.loads first — already valid JSON
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError:
            pass

        # Try ast.literal_eval — handles Python dict with single-quoted keys
        try:
            parsed = ast.literal_eval(s)
            return json.dumps(parsed)
        except Exception:
            pass

        # Fix bare unquoted keys: {token: abc} → {"token": "abc"}
        try:
            fixed = s
            # Add quotes around unquoted keys
            fixed = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed)
            # Add quotes around unquoted string values
            fixed = re.sub(r':\s*([^",\{\}\[\]\d][^,\}\]]*?)(\s*[,\}])', r':"\1"\2', fixed)
            parsed = json.loads(fixed)
            return json.dumps(parsed)
        except Exception:
            pass

        return s  # fallback — return as-is

    def _get_gmail_service(self):
        creds = None

        if self.token_data:
            clean_token = self._clean_json_str(self.token_data)
            try:
                token_json = json.loads(clean_token)
                creds = Credentials.from_authorized_user_info(token_json, self.scopes)
            except json.JSONDecodeError as e:
                print(f"Failed to parse GMAIL_TOKEN_FILE JSON: {e}")
                print(f"Raw value first 100 chars: {self.token_data[:100]}")

        if not creds:
            raise RuntimeError("Gmail credentials could not be loaded. Check GMAIL_TOKEN_FILE in .env")

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                clean_secret = self._clean_json_str(self.client_secret_data)
                try:
                    client_config = json.loads(clean_secret)
                    flow = InstalledAppFlow.from_client_config(client_config, self.scopes)
                    creds = flow.run_local_server(port=self.port, access_type='offline', prompt='consent')
                except json.JSONDecodeError as e:
                    print(f"Failed to parse GMAIL_CLIENT_SECRET_FILE JSON: {e}")
                    raise RuntimeError("Gmail client secret could not be loaded. Check GMAIL_CLIENT_SECRET_FILE in .env")

        return build('gmail', 'v1', credentials=creds)

    async def _translate_text(self, text, language):
        """Translate text to target language. Falls back to English on any error."""
        lang_code = language.strip().lower()

        # Skip translation for English
        if not lang_code or lang_code == "en" or lang_code == "english":
            return text

        # Convert language name to code if needed (e.g. "kannada" → "kn")
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
        """Sends a translatable welcome email to new users."""
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
        message['From'] = sender
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            sent_message = self.service.users().messages().send(
                userId="me",
                body={'raw': encoded_message}
            ).execute()
            print(f"Success! Email sent. Message ID: {sent_message.get('id')}")
            return sent_message.get('id')
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Email failed: {str(e)}")

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
        message['From'] = sender
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            sent_message = self.service.users().messages().send(
                userId="me",
                body={'raw': encoded_message}
            ).execute()
            print(f"Password reset email sent. Message ID: {sent_message.get('id')}")
            return sent_message.get('id')
        except Exception as e:
            print(f"Error sending reset email: {e}")
            return None

if __name__ == '__main__':
    gmail_client = GmailSender()
    asyncio.run(gmail_client.send_email(
        sender="crypticmage00@gmail.com",
        to="test@example.com",
        name="Test User",
        role="Admin",
        hire_date="2026-03-10",
        language="en"
    ))