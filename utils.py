# utils.py

import os
import openai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_caption(topic: str, platform: str) -> str:
    prompt = f"""
Create 3 creative and engaging social media captions designed for maximum reach and exposure.

Platform: {platform}
Topic: {topic}

Guidelines:
- Respond in plain English text
- Each caption must start with a number (1., 2., 3.) and be on its own line with a <br><br> between
- Include emojis to increase engagement
- Include powerful, **popular and relevant hashtags** for maximum discoverability
- No introductions or explanations, just the 3 captions
- Adapt style and tone to platform and topic:
  • Fitness = motivational and energetic
  • Flowers = poetic and light
  • Sales = clear and persuasive
  • Mental health = calm and supportive

Example output:

1. 💪 Ready to crush Monday? No regrets, just gains.  
#MotivationMonday #FitGoals

2. 🌸 A new week, a fresh bloom of opportunity.  
#FlowerLover #SpringVibes

3. ✨ 20% OFF today only! Your favorites just got better.  
#DealOfTheDay #ShopSmart

Each caption must be useful as-is – short, catchy, and with hashtags that help users go viral.

You are a skilled social media content writer. Be creative, avoid clichés, and use high-performing tags.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def send_email(to_email: str, caption_text: str):
    try:
        message = Mail(
            from_email=os.getenv("EMAIL_FROM"),
            to_emails=to_email,
            subject="Your social media captions are ready!",
            html_content=f"""
                <div style="font-family:Arial;padding:20px;">
                    <h2>🚀 Your captions are ready!</h2>
                    <p>{caption_text}</p>
                    <hr>
                    <p>Thanks for using <strong>InstaPrompt</strong>!</p>
                </div>
            """
        )
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        print("📬 SendGrid status:", response.status_code)
    except Exception as e:
        print("❌ SendGrid-feil:", e)
