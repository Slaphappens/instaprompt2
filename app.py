from flask import Flask, request, render_template_string
from utils import generate_caption, send_email
import os

app = Flask(__name__)

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
        fields = {f["label"]: f["value"] for f in data["fields"]}
        email = fields.get("Hva er e-postadressen din?")
        tema = fields.get("Hva handler innlegget om?")
        plattform = fields.get("Hvilken plattform gjelder innlegget?")
    except Exception as e:
        return f"❌ Malformed fields: {e}", 400

    if not all([email, tema, plattform]):
        return "❌ Missing required fields", 400

    if os.path.exists("used_emails.txt") and email in open("used_emails.txt").read():
        return "⚠️ Du har allerede brukt din gratis caption!", 403

    caption = generate_caption(tema, plattform)
    send_email(email, caption)

    with open("used_emails.txt", "a") as f:
        f.write(email + "\n")

    return render_template_string(f"<h2>Ditt resultat:</h2><p>{caption}</p>")

@app.route("/testmail", methods=["GET"])
def test_email():
    test_email_address = "din@epost.no"  # ← bytt til din testadresse
    test_caption = "Dette er en test-caption 🚀"
    send_email(test_email_address, test_caption)
    return "E-post sendt (hvis alt fungerer)", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
