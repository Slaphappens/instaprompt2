import os
import smtplib
from email.message import EmailMessage
import openai
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

def send_email(to_email, body):
    msg = EmailMessage()
    msg["Subject"] = "Dine InstaPrompt captions"
    msg["From"] = os.getenv("EMAIL_FROM")
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP_SSL(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT"))) as smtp:
        smtp.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
        smtp.send_message(msg)
