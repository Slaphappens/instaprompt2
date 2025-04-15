import os
from openai import OpenAI
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

load_dotenv()

# ✅ Bruk default OpenAI-klient med .api_key
client = OpenAI()
client.api_key = os.getenv("OPENAI_API_KEY")

def generate_caption(tema, plattform):
    prompt = f"Lag en engasjerende caption om {tema} for {plattform}."
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def send_email(to_email, caption_text):
    try:
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
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        print("📬 SendGrid status:", response.status_code)
    except Exception as e:
        print("❌ SendGrid-feil:", e)
