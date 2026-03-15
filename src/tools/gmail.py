import os
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv
import asyncio
from googletrans import Translator, LANGUAGES

# Load environment variables from the .env file one level up (in agrinow/)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

class GmailSender:
    def __init__(self, token_file=None, client_secret_file=None, port=8080):
        # We use gmail.send to be able to send emails
        self.scopes = ['https://www.googleapis.com/auth/gmail.send']
        
        # Pull from environment variables if not explicitly passed
        self.token_data = token_file or os.getenv('GMAIL_TOKEN_FILE')
        self.client_secret_data = client_secret_file or os.getenv('GMAIL_CLIENT_SECRET_FILE')
        self.port = port
        self.service = self._get_gmail_service()

    def _get_gmail_service(self):
        creds = None
        import json
        
        # Helper to clean up env variables that might be wrapped in single/double quotes by the server/bash
        def _clean_json_str(s):
            if not s: return s
            s = s.strip()
            # If the entire JSON object is wrapped in single or double quotes, strip them
            if s.startswith("'") and s.endswith("'"): s = s[1:-1]
            if s.startswith('"') and s.endswith('"') and s.startswith('"{') and s.endswith('}"'): s = s[1:-1]
            # Unescape backslash quotes if they exist
            s = s.replace("\\'", "'")
            # If they used single quotes instead of double quotes for JSON keys (invalid JSON but common typo)
            return s
        
        # If we have token data in the environment, use it directly (no file reading)
        if self.token_data:
            clean_token = _clean_json_str(self.token_data)
            try:
                token_json = json.loads(clean_token)
                creds = Credentials.from_authorized_user_info(token_json, self.scopes)
            except json.JSONDecodeError as e:
                print(f"Failed to parse GMAIL_TOKEN_FILE JSON: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                clean_secret = _clean_json_str(self.client_secret_data)
                try:
                    client_config = json.loads(clean_secret)
                    flow = InstalledAppFlow.from_client_config(client_config, self.scopes)
                    creds = flow.run_local_server(port=self.port, access_type='offline', prompt='consent')
                except json.JSONDecodeError as e:
                    print(f"Failed to parse GMAIL_CLIENT_SECRET_FILE JSON: {e}")

        return build('gmail', 'v1', credentials=creds)

    async def _translate_text(self, text, language):
        """Asynchronously translates text to the target language. Falls back to English on error."""
        lang_code = language.strip().lower()
        if not lang_code or lang_code == "en":
            return text

        try:
            translator = Translator()
            result = await translator.translate(text, dest=lang_code)
            return result.text
        except Exception as e:
            print(f"Translation failed for '{lang_code}': {e}. Falling back to English.")
            return text
#     def send_email(self, sender, to, name, role, hire_date,language):
#         subject = "Welcome to the Revolution: You’re officially part of SeedSense!"
#         content = f"""<!DOCTYPE html>
# <html>
# <head>
#     <meta charset="UTF-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
# </head>
# <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333333;">
#     <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; margin-top: 20px; margin-bottom: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0px 4px 10px rgba(0,0,0,0.05);">
#         <tr>
#             <td align="center" style="padding: 40px 0 30px 0; background-color: #2e7d32;">
#                 <h1 style="margin: 0; color: #ffffff; font-size: 28px; letter-spacing: 1px;">SeedSense</h1>
#             </td>
#         </tr>

#         <tr>
#             <td style="padding: 40px 30px;">
#                 <h2 style="margin: 0 0 20px 0; color: #2e7d32; font-size: 24px;">Welcome to the Digital Revolution!</h2>
#                 <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
#                     Hi <strong>{name}</strong>, <br><br>
#                     Thank you for joining <strong>SeedSense</strong>. We are thrilled to have you as part of our mission to digitize and revolutionize the way we grow and connect.
#                 </p>

#                 <div style="background-color: #f9f9f9; border-left: 4px solid #2e7d32; padding: 20px; margin-bottom: 30px;">
#                     <h3 style="margin: 0 0 15px 0; font-size: 18px; color: #555;">Your Account Details:</h3>
#                     <table width="100%" style="font-size: 15px; line-height: 2;">
#                         <tr>
#                             <td width="30%"><strong>Name:</strong></td>
#                             <td>{name}</td>
#                         </tr>
#                         <tr>
#                             <td><strong>Email:</strong></td>
#                             <td>{to}</td>
#                         </tr>
#                         <tr>
#                             <td><strong>Role:</strong></td>
#                             <td><span style="background-color: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 4px; font-size: 13px; font-weight: bold;">{role}</span></td>
#                         </tr>
#                         <tr>
#                             <td><strong>Joined On:</strong></td>
#                             <td>{str(hire_date)}</td>
#                         </tr>
#                     </table>
#                 </div>

#                 <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
#                     What's next? You can now access your dashboard, explore, and collaborate with other visionaries.
#                 </p>

#                 <table border="0" cellpadding="0" cellspacing="0" width="100%">
#                     <tr>
#                         <td align="center">
#                             <a href="https://agrinow-ui.vercel.app/" style="background-color: #2e7d32; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Login to your account</a>
#                         </td>
#                     </tr>
#                 </table>

#                 <div style="margin-top: 30px; padding: 15px; background-color: #fff9c4; border-radius: 5px; text-align: center;">
#                     <p style="margin: 0; font-size: 14px; color: #f57f17;">
#                         <strong>🔒 Security Tip:</strong> For your protection, we recommend that you change your password immediately after your first login. You can do this easily using the <strong>"Forgot Password?"</strong> link on the login page.
#                     </p>
#                 </div>
#             </td>
#         </tr>

#         <tr>
#             <td style="padding: 30px; background-color: #eeeeee; text-align: center; font-size: 12px; color: #777777;">
#                 <p style="margin: 0 0 10px 0;">&copy; 2026 SeedSense | Bengaluru, India</p>
#                 <p style="margin: 0;">You received this email because you signed up for the digital revolution.</p>
#             </td>
#         </tr>
#     </table>
# </body>
# </html>"""

    async def send_email(self, sender, to, name, role, hire_date, language="en"):
        """Sends a translatable welcome email to new users."""

        # --- Translatable text strings ---
        # Note: We define a helper to reduce boilerplate, but we must await each call.
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

        # Create the email message
        message = EmailMessage()
        # Add subtype='html' to render the styling correctly
        message.set_content(content, subtype='html')
        message['To'] = to
        message['From'] = sender
        message['Subject'] = subject

        # Encode the message safely for the API
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {
            'raw': encoded_message
        }
        
        try:
            # UserID="me" refers to the authenticated user
            sent_message = self.service.users().messages().send(userId="me", body=create_message).execute()
            print(f"Success! Email sent. Message ID: {sent_message.get('id')}")
            return sent_message.get('id')
        except Exception as email_err:
            raise HTTPException(
                status_code=500,
                detail=f"Email failed: {str(email_err)}"  # ← show real error
            )

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

        create_message = {
            'raw': encoded_message
        }

        try:
            sent_message = self.service.users().messages().send(userId="me", body=create_message).execute()
            print(f"Password reset email sent. Message ID: {sent_message.get('id')}")
            return sent_message.get('id')
        except Exception as e:
            print(f"Error sending reset email: {e}")
            return None

if __name__ == '__main__':
    # You can still test it directly if you run this file!
    gmail_client = GmailSender()
    SENDER_EMAIL = "crypticmage00@gmail.com"
    RECIPIENT_EMAIL = "[EMAIL_ADDRESS]"
    
    # Using dummy data for testing the offline execution
    gmail_client.send_email(
        sender=SENDER_EMAIL, 
        to=RECIPIENT_EMAIL, 
        name="Test User", 
        role="Admin", 
        hire_date="2026-03-10"
    )
