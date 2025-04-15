# utils.py

import os
import openai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_caption(tema, plattform):
    prompt = f"Lag en engasjerende caption om {tema} for {plattform}."
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def send_email(to_email, caption_text):
    message = Mail(
        from_email=os.getenv("EMAIL_FROM"),
        to_emails=to_email,
        subject="Dine InstaPrompt captions",
        html_content=f"""
            <div style="font-family:Arial;padding:20px;">
                <h2>🚀 Dine captions er klare!</h2>
                <p>{caption_text}</p>
                <p>Hilsen,<br><strong>InstaPrompt</strong></p>
            </div>
        """
    )
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        print("📬 SendGrid status:", response.status_code)
    except Exception as e:
        print("❌ SendGrid-feil:", e)
