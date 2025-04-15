import os
import openai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

TRENDING_HASHTAGS = {
    "fitness": ["#fitnessbr", "#academia", "#vidasaudavel", "#nopainnogain", "#fyp"],
    "café": ["#cafedamanha", "#amocafé", "#baristabrasil", "#coffeetime", "#fyp"],
    "flores": ["#flores", "#buquês", "#diadasmaes", "#presenteperfeito", "#fyp"],
    "vendas": ["#promoção", "#descontos", "#ofertaespecial", "#comprejá", "#fyp"],
    "marketing": ["#negociosonline", "#copywriting", "#socialmedia", "#empreendedorismo", "#fyp"],
    "moda": ["#ootdbr", "#modafeminina", "#tendencias", "#lookdodia", "#fyp"],
    "comida": ["#comidacaseira", "#gastronomiabrasileira", "#receitafácil", "#delicias", "#fyp"],
    "pet": ["#vidadepet", "#cachorrofofo", "#gatobr", "#amomeupet", "#fyp"],
    "beleza": ["#maquiagem", "#dicasdebeleza", "#skincareroutine", "#autocuidado", "#fyp"],
    "psicologia": ["#saudemental", "#terapiabr", "#bemestar", "#autoconhecimento", "#fyp"],
    "relacionamento": ["#amor", "#casal", "#relacionamentos", "#vidadois", "#fyp"],
    "viagem": ["#viajarépreciso", "#destinosnacionais", "#mochilao", "#turismobr", "#fyp"],
}


def detect_categories_from_topic(topic: str) -> list[str]:
    system_msg = (
        "Dado o tópico abaixo, responda com todas as categorias que se aplicam da lista, separadas por vírgula: "
        "fitness, café, flores, vendas, marketing, moda, comida, pet, beleza, psicologia, relacionamento, viagem"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": topic}
            ]
        )
        categories = [c.strip().lower() for c in response.choices[0].message.content.strip().split(",")]
        print(f"🧠 GPT-mapped categories: {categories}")
        return categories
    except Exception as e:
        print("❌ GPT category detection failed:", e)
        return ["vendas"]


def collect_hashtags(categories: list[str]) -> str:
    tags = []
    seen = set()
    for c in categories:
        for tag in TRENDING_HASHTAGS.get(c, []):
            if tag not in seen:
                tags.append(tag)
                seen.add(tag)
    return " ".join(tags[:7]) or "#fyp"


def check_quota(email: str, platform: str) -> tuple[bool, str]:
    try:
        response = supabase.table("profiles").select("plan,used_captions").eq("email", email).execute()
        data = response.data or []

        if len(data) == 0:
            supabase.table("profiles").insert({
                "email": email,
                "plan": "trial",
                "used_captions": 0
            }).execute()
            return True, "created trial user"

        profile = data[0]
        plan = profile["plan"]
        used = profile["used_captions"]

        if plan == "pro":
            return True, "pro user"

        if plan == "free":
            if platform.lower() != "instagram":
                return False, "Free plan supports Instagram only"
            if used < 3:
                return True, "free OK"
            return False, "Free plan limit reached"

        if plan == "trial":
            if used < 10:
                return True, "trial OK"
            return False, "Trial credits used"

        return False, "Unknown plan"
    except Exception as e:
        print("❌ Quota check error:", e)
        return False, "quota error"


def increment_caption_count(email: str) -> bool:
    try:
        supabase.rpc("increment_captions", {"user_email": email}).execute()
        return True
    except Exception as e:
        print("❌ Increment caption error:", e)
        return False


def save_caption_to_supabase(email: str, caption: str, language: str, platform: str, tone: str, category: str) -> bool:
    try:
        supabase.table("captions").insert({
            "email": email,
            "caption_text": caption,
            "language": language,
            "platform": platform,
            "tone": tone,
            "category": category
        }).execute()
        return True
    except Exception as e:
        print("❌ Save caption error:", e)
        return False


def generate_caption(topic: str, platform: str, language: str, tone: str = "creative") -> str:
    categories = detect_categories_from_topic(topic)
    hashtag_str = collect_hashtags(categories)

    prompt = f"""
Create 3 scroll-stopping, creative, and highly engaging social media captions.

Platform: {platform}
Topic: {topic}
Tone/style: {tone}
Language: {language}

Instructions:
- Write in {language}
- Use tone: {tone}
- Each caption must be unique, with a creative hook in the first 3 words
- Add emojis that match the message
- Each caption must be numbered (1., 2., 3.) and separated by <br><br>
- End each caption with: "{hashtag_str}"
- Do not explain anything — just return the captions only
- Follow platform-specific tone and formatting:
  • Instagram = polished, aesthetic
  • TikTok = casual, quick, authentic
  • Twitter = short & witty
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


def get_translated_email_content(caption: str, language: str, topic: str = "", platform: str = "") -> tuple[str, str]:
    language = language.lower()
    intro = f"<p>Com base no seu tema <strong>“{topic}”</strong> para <strong>{platform}</strong>, aqui estão suas legendas:</p><br>" if language.startswith("port") else \
            f"<p>Based on your topic <strong>“{topic}”</strong> for <strong>{platform}</strong>, here are your captions:</p><br>"

    rating_html = """
        <p style="margin-top:20px;"><strong>⭐ Avalie sua legenda:</strong><br>
        <a href='https://instaprompt.ai/rate?score=1'>1⭐</a> |
        <a href='https://instaprompt.ai/rate?score=2'>2⭐</a> |
        <a href='https://instaprompt.ai/rate?score=3'>3⭐</a> |
        <a href='https://instaprompt.ai/rate?score=4'>4⭐</a> |
        <a href='https://instaprompt.ai/rate?score=5'>5⭐</a>
        </p>
    """

    if language.startswith("port"):
        subject = "Suas legendas estão prontas! 🚀"
        body = f"""
        <div style="font-family:Arial;padding:20px;">
            <h2>🚀 Suas legendas estão prontas!</h2>
            {intro}
            <p>{caption}</p>
            <hr>
            <p><strong>💡 Dica rápida:</strong> Copie a legenda acima e cole como descrição da sua próxima postagem no Instagram, TikTok ou LinkedIn.</p>
            <p>📌 Use-a com uma imagem ou vídeo relacionado ao tema.</p>
            <p>⏰ Publique nos horários de pico (como 12h ou 19h) para alcançar mais pessoas.</p>
            {rating_html}
            <hr>
            <p>Obrigado por usar <strong>InstaPrompt</strong>!</p>
        </div>
        """
    else:
        subject = "Your social media captions are ready! 🚀"
        body = f"""
        <div style="font-family:Arial;padding:20px;">
            <h2>🚀 Your captions are ready!</h2>
            {intro}
            <p>{caption}</p>
            <hr>
            <p><strong>💡 Pro tip:</strong> Copy the caption above and paste it directly in your next Instagram, TikTok, or LinkedIn post.</p>
            <p>📌 Use it with a matching image or video to boost engagement.</p>
            <p>⏰ Best to post during peak hours (like noon or 7PM) for max reach.</p>
            {rating_html}
            <hr>
            <p>Thanks for using <strong>InstaPrompt</strong>!</p>
        </div>
        """
    return subject, body


def send_email(to_email: str, caption_text: str, language: str = "engelsk", topic: str = "", platform: str = ""):
    try:
        subject, html = get_translated_email_content(caption_text, language, topic, platform)
        message = Mail(
            from_email=os.getenv("EMAIL_FROM"),
            to_emails=to_email,
            subject=subject,
            html_content=html,
        )
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print("❌ Email send error:", e)


def upgrade_plan_to_pro(email: str) -> bool:
    try:
        supabase.table("profiles").update({"plan": "pro"}).eq("email", email).execute()
        return True
    except Exception as e:
        print("❌ Stripe upgrade error:", e)
        return False
