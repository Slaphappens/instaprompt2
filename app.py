# app.py

from flask import Flask, request, render_template_string
from flask import redirect
from utils import (
    generate_caption,
    send_email,
    check_quota,
    increment_caption_count,
    save_caption_to_supabase,
    upgrade_plan_to_pro,
    detect_categories_from_topic,
    detect_tone_from_topic,
    post_to_slack
)
import os
import stripe
from openai import OpenAI
import re
import uuid

app = Flask(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
            detection = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Detect language of the following:"},
                    {"role": "user", "content": tema}
                ]
            )
            sprak = detection.choices[0].message.content.strip().split()[0]
            print(f"🌍 GPT-detected language: {sprak}")
        except:
            sprak = "English"

    if not tone:
        tone = detect_tone_from_topic(tema, sprak)

    category = detect_categories_from_topic(tema)
    print("🧠 Detected category:", category)

    allowed, reason, plan = check_quota(email, plattform)
    if not allowed:
        return reason, 403

    caption_id = str(uuid.uuid4())

    caption = generate_caption(tema, plattform, sprak, tone, plan)
    post_to_slack(caption, email, tema, tone, plan, sprak)
    send_email(email, caption, sprak, topic=tema, platform=plattform)
    save_caption_to_supabase(email, caption, sprak, plattform, tone, category[0], caption_id)
    increment_caption_count(email, count=3)

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

        elif session.get("mode") == "payment":
            supabase.table("profiles").upsert({
                "email": customer_email,
                "plan": "trial",
                "used_captions": 0
            }).execute()
            print(f"🧪 Trial aktivert for {customer_email}")

    return "✅ OK", 200


@app.route("/stripe/customer-portal", methods=["GET"])
def stripe_customer_portal():
    try:
        email = request.args.get("email")
        customer_id = "cus_xxxxxx"  # TODO: hent riktig ID basert på epost

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=os.getenv("DOMAIN")
        )
        return redirect(session.url)
    except Exception as e:
        print("❌ Stripe-portal-feil:", e)
        return "❌ Klarte ikke å åpne portal", 400


@app.route("/test/email", methods=["GET"])
def test_email():
    try:
        test_address = request.args.get("to", "prpedersen@outlook.com")
        send_email(
            to_email=test_address,
            caption_text="🚀 Test fra InstaPrompt – dette er en e-posttest",
            language="português",
            topic="Teste de envio",
            platform="Instagram"
        )
        return f"✅ Test e-post sendt til {test_address}"
    except Exception as e:
        print("❌ Test e-post-feil:", e)
        return f"❌ Feil: {e}", 500


@app.route("/stripe/checkout", methods=["GET"])
def stripe_checkout():
    try:
        DOMAIN = os.getenv("DOMAIN")
        success_url = DOMAIN + "/sucesso"
        cancel_url = DOMAIN + "/cancelado"

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{
                "price": "price_1REnHoEIpiF3EYvU4B9H3SRq",
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return redirect(session.url, code=303)

    except Exception as e:
        print("❌ Stripe checkout error:", e)
        return f"❌ Stripe-feil: {e}", 500


@app.route("/stripe/trial-checkout", methods=["GET"])
def trial_checkout():
    try:
        DOMAIN = os.getenv("DOMAIN")  # ← FIX lagt til her
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{
                "price": "price_1REnGgEIpiF3EYvU2uadaWDS",
                "quantity": 1,
            }],
            success_url=f"{DOMAIN}/thanks?plan=trial",
            cancel_url=f"{DOMAIN}/cancelled",
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return f"Stripe-feil: {e}", 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)


@app.route("/rate", methods=["GET"])
def rate_caption():
    email = request.args.get("email")
    score = request.args.get("score")
    caption_id = request.args.get("id")

    if not all([email, score, caption_id]):
        return "❌ Mangler informasjon", 400

    try:
        supabase.table("ratings").insert({
            "email": email,
            "caption_id": caption_id,
            "score": int(score)
        }).execute()
        return f"⭐ Takk for din vurdering ({score} stjerner)!"
    except Exception as e:
        print("❌ Feil ved rating:", e)
        return "❌ Klarte ikke å registrere vurdering", 500
