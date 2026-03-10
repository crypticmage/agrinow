import os
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables from the .env file one level up (in agrinow/)
load_dotenv(os.path.join(os.path.dirname(__file__), "../../", ".env"))

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
        
        # If we have token data in the environment, use it directly (no file reading)
        if self.token_data:
            token_json = json.loads(self.token_data)
            creds = Credentials.from_authorized_user_info(token_json, self.scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                client_config = json.loads(self.client_secret_data)
                flow = InstalledAppFlow.from_client_config(
                    client_config, self.scopes)

                # Request offline access so we get a refresh token that doesn't expire quickly
                creds = flow.run_local_server(port=self.port, access_type='offline', prompt='consent')

        return build('gmail', 'v1', credentials=creds)

    def send_email(self, sender, to, name, role, hire_date):
        subject = "Welcome to the Revolution: You’re officially part of SeedSense!"
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
                <h2 style="margin: 0 0 20px 0; color: #2e7d32; font-size: 24px;">Welcome to the Digital Revolution!</h2>
                <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
                    Hi <strong>{name}</strong>, <br><br>
                    Thank you for joining <strong>SeedSense</strong>. We are thrilled to have you as part of our mission to digitize and revolutionize the way we grow and connect.
                </p>

                <div style="background-color: #f9f9f9; border-left: 4px solid #2e7d32; padding: 20px; margin-bottom: 30px;">
                    <h3 style="margin: 0 0 15px 0; font-size: 18px; color: #555;">Your Account Details:</h3>
                    <table width="100%" style="font-size: 15px; line-height: 2;">
                        <tr>
                            <td width="30%"><strong>Name:</strong></td>
                            <td>{name}</td>
                        </tr>
                        <tr>
                            <td><strong>Email:</strong></td>
                            <td>{to}</td>
                        </tr>
                        <tr>
                            <td><strong>Role:</strong></td>
                            <td><span style="background-color: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 4px; font-size: 13px; font-weight: bold;">{role}</span></td>
                        </tr>
                        <tr>
                            <td><strong>Joined On:</strong></td>
                            <td>{str(hire_date)}</td>
                        </tr>
                    </table>
                </div>

                <p style="margin: 0 0 20px 0; line-height: 1.6; font-size: 16px;">
                    What's next? You can now access your dashboard, explore, and collaborate with other visionaries.
                </p>

                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                        <td align="center">
                            <a href="https://agrinow-ui.vercel.app/" style="background-color: #2e7d32; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Login to your account</a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <tr>
            <td style="padding: 30px; background-color: #eeeeee; text-align: center; font-size: 12px; color: #777777;">
                <p style="margin: 0 0 10px 0;">&copy; 2026 SeedSense | Bengaluru, India</p>
                <p style="margin: 0;">You received this email because you signed up for the digital revolution.</p>
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
            print(f"✅ Success! Email sent. Message ID: {sent_message.get('id')}")
            return sent_message.get('id')
        except Exception as e:
            print(f"❌ Error: {e}")
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
