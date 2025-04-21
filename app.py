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
                "price": os.getenv("STRIPE_PRICE_PRO"),
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
                "price": os.getenv("STRIPE_PRICE_TRIAL"),
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

@app.route("/thanks", methods=["GET"])
def thanks():
    plan = request.args.get("plan", "ukjent")
    return render_template_string(f"""
        <html>
            <head><title>InstaPrompt - Betaling fullført</title></head>
            <body style="font-family: sans-serif; padding: 3rem; text-align: center;">
                <h1>🎉 Takk for kjøpet!</h1>
                <p>Du har aktivert <strong>{plan.upper()}</strong>-planen din på InstaPrompt.</p>
                <p>Gå tilbake til skjemaet og begynn å generere captions med en gang 💡</p>
                <a href="https://tally.so/r/waljyy" style="margin-top: 2rem; display: inline-block; background: #7B61FF; color: white; padding: 1rem 2rem; border-radius: 8px; text-decoration: none;">
                    Start å generere nå
                </a>
            </body>
        </html>
    """)


@app.route("/cancelled", methods=["GET"])
def cancelled():
    return render_template_string("""
        <html>
            <head><title>InstaPrompt - Betaling avbrutt</title></head>
            <body style="font-family: sans-serif; padding: 3rem; text-align: center;">
                <h1>⛔️ Betaling avbrutt</h1>
                <p>Ingen penger ble trukket, og kontoen din er uendret.</p>
                <p>Du kan prøve på nytt når du er klar.</p>
                <a href="https://instaprompt2-production.up.railway.app/stripe/checkout" style="margin-top: 2rem; display: inline-block; background: #E63946; color: white; padding: 1rem 2rem; border-radius: 8px; text-decoration: none;">
                    Prøv igjen
                </a>
            </body>
        </html>
    """)

@app.route("/thanks", methods=["GET"])
def thanks():
    plan = request.args.get("plan", "desconhecido")
    return render_template_string(f"""
        <html>
            <head><title>InstaPrompt – Obrigado</title></head>
            <body style="font-family: sans-serif; padding: 3rem; text-align: center;">
                <h1>🎉 Pagamento confirmado!</h1>
                <p>Você ativou o plano <strong>{plan.upper()}</strong> no InstaPrompt.</p>
                <p>Comece a criar legendas agora mesmo:</p>
                <a href="https://tally.so/r/waljyy" style="margin-top: 2rem; display: inline-block; background: #7B61FF; color: white; padding: 1rem 2rem; border-radius: 8px; text-decoration: none;">
                    Abrir formulário
                </a>
            </body>
        </html>
    """)

@app.route("/cancelled", methods=["GET"])
def cancelled():
    return render_template_string("""
        <html>
            <head><title>InstaPrompt – Pagamento cancelado</title></head>
            <body style="font-family: sans-serif; padding: 3rem; text-align: center;">
                <h1>🛑 Pagamento cancelado</h1>
                <p>Não se preocupe – nenhum valor foi cobrado 😉</p>
                <p>Se você quiser tentar novamente, clique no botão abaixo:</p>
                <a href="https://instaprompt2-production.up.railway.app/stripe/checkout" style="margin-top: 2rem; display: inline-block; background: #E63946; color: white; padding: 1rem 2rem; border-radius: 8px; text-decoration: none;">
                    Tentar novamente
                </a>
            </body>
        </html>
    """)
