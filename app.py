# app.py

from flask import Flask, request, render_template_string
from utils import (
    generate_caption,
    send_email,
    check_quota,
    increment_caption_count,
    save_caption_to_supabase,
    upgrade_plan_to_pro,
    detect_categories_from_topic,
    detect_tone_from_topic,
)
import os
import stripe
import openai
import re

app = Flask(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
openai.api_key = os.getenv("OPENAI_API_KEY")


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().lower())


def find_field(fields: dict, *candidates: str):
    normalized_fields = {normalize(k): v for k, v in fields.items()}
    for label in candidates:
        norm_label = normalize(label)
        if norm_label in normalized_fields:
            return normalized_fields[norm_label]
    return None


@app.route("/", methods=["GET"])
def health():
    return "InstaPrompt is live!"


@app.route("/webhook", methods=["POST"])
def webhook():
    print("📥 Webhook called")

    try:
        data = request.get_json(force=True)
        print("🔍 Payload:", data)
    except Exception as e:
        return f"❌ Invalid JSON: {e}", 400

    try:
        fields = {f["label"]: f["value"] for f in data["data"]["fields"]}
        email = find_field(fields, "Qual é o seu endereço de e-mail?", "Email")
        tema = find_field(fields, "Sobre o que é a sua postagem?", "Post topic")
        plattform = find_field(fields, "Para qual plataforma é essa legenda?", "Platform")
        sprak = find_field(fields, "Em qual idioma você quer a legenda?", "Language")
        tone = find_field(fields, "Escolha um estilo de tom", "Choose a tone/style")

        print("🧪 email:", email)
        print("🧪 tema:", tema)
        print("🧪 plattform:", plattform)
        print("🧪 sprak:", sprak)
        print("🧪 tone:", tone)
    except Exception as e:
        return f"❌ Malformed fields: {e}", 400

    if not all([email, tema, plattform]):
        return "❌ Missing required fields", 400

    if not sprak:
        try:
            detection = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Detect language of the following:"},
                    {"role": "user", "content": tema}
                ]
            )
            sprak = detection.choices[0].message.content.strip().split()[0]
            print(f"🌍 Detected language: {sprak}")
        except:
            sprak = "English"

    if not tone:
        tone = detect_tone_from_topic(tema, sprak)

    category = detect_categories_from_topic(tema)
    print("🧠 Detected category:", category)

    allowed, reason = check_quota(email, plattform)
    if not allowed:
        return f"❌ Quota limit: {reason}", 403

    caption = generate_caption(tema, plattform, sprak, tone)
    send_email(email, caption, sprak, topic=tema, platform=plattform)
    save_caption_to_supabase(email, caption, sprak, plattform, tone, category[0])
    increment_caption_count(email)

    return render_template_string(f"<h2>Your result:</h2><p>{caption}</p>")


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except stripe.error.SignatureVerificationError:
        return "❌ Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session["customer_details"]["email"]

        if session.get("mode") == "subscription":
            upgrade_plan_to_pro(customer_email)
            print(f"✅ Upgraded {customer_email} to PRO")

    return "✅ OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
