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

ALLOWED_CATEGORIES = set(TRENDING_HASHTAGS.keys())


def detect_categories_from_topic(topic: str) -> list[str]:
    try:
        system_msg = (
            "Você é um classificador de tópicos. "
            "Retorne apenas 1 palavra da lista de categorias abaixo que melhor representa o tópico: "
            ", ".join(ALLOWED_CATEGORIES)
        )
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": topic}
            ]
        )
        category = response.choices[0].message.content.strip().lower()
        print(f"🧠 GPT-mapped category: {category}")
        if category not in ALLOWED_CATEGORIES:
            print("⚠️ Unknown category from GPT, falling back to 'vendas'")
            return ["vendas"]
        return [category]
    except Exception as e:
        print("❌ GPT category detection failed:", e)
        return ["vendas"]


def detect_tone_from_topic(topic: str, language: str = "Português") -> str:
    try:
        system_msg = (
            f"Com base no seguinte tema, responda com um único estilo de tom "
            f"como: divertido, inspirador, profissional, emocional, criativo, ou direto. "
            f"Apenas uma palavra como resposta. Escreva em {language}."
        )
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": topic}
            ]
        )
        tone = response.choices[0].message.content.strip().lower()
        print(f"🎭 GPT-suggested tone: {tone}")
        return tone
    except Exception as e:
        print("❌ Tone detection failed:", e)
        return "criativo"


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
            <p><strong>💡 Dica rápida:</strong> Copie a legenda acima e cole como descrição da sua próxima postagem.</p>
            <p>📌 Combine com uma imagem ou vídeo relevante.</p>
            <p>⏰ Publique nos horários de pico (12h ou 19h).</p>
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
            <p><strong>💡 Pro tip:</strong> Paste the caption in your next Instagram, TikTok, or LinkedIn post.</p>
            <p>📌 Match it with a relevant image or video.</p>
            <p>⏰ Post at peak hours (like 12PM or 7PM).</p>
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

def detect_tone_from_topic(topic: str, language: str = "português") -> str:
    system_msg = (
        "Você é um assistente de marketing. "
        "Dado um tema de postagem em rede social, responda apenas com o estilo de tom mais adequado: "
        "divertido, profissional, inspirador, informativo, casual, provocador, poético"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": topic}
            ]
        )
        tone = response.choices[0].message.content.strip().lower()
        print(f"🎯 GPT-suggested tone: {tone}")
        return tone
    except Exception as e:
        print("❌ Tone detection failed:", e)
        return "criativo"
