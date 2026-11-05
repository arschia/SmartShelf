"""Create a secure, local-only SmartShelf .env without overwriting existing secrets."""
from pathlib import Path
import secrets
import string

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
TEMPLATE = ROOT / ".env.example"


def parse(lines):
    result = {}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def set_value(lines, key, value):
    prefix = key + "="
    found = False
    out = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(prefix):
            if not found:
                out.append(prefix + value)
                found = True
            # drop duplicate definitions to avoid ambiguous dotenv behavior
        else:
            out.append(line)
    if not found:
        out.append(prefix + value)
    return out


def main():
    ROOT.joinpath("data", "uploads").mkdir(parents=True, exist_ok=True)
    ROOT.joinpath("logs").mkdir(exist_ok=True)
    ROOT.joinpath("backups").mkdir(exist_ok=True)

    if ENV.exists():
        lines = ENV.read_text(encoding="utf-8-sig").splitlines()
    else:
        lines = TEMPLATE.read_text(encoding="utf-8-sig").splitlines()

    values = parse(lines)
    generated_pin = None
    secret = values.get("SECRET_KEY", "")
    if not secret or secret.lower().startswith("change-me") or len(secret) < 32:
        secret = secrets.token_hex(32)
        lines = set_value(lines, "SECRET_KEY", secret)

    pin = values.get("ADMIN_PIN", "")
    explicit_test_pin = (pin == "1234"
                         and values.get("ALLOW_INSECURE_TEST_PIN", "false").lower() in ("true", "1", "yes")
                         and values.get("STORE_OPEN", "false").lower() not in ("true", "1", "yes"))
    if not explicit_test_pin and (not pin or pin == "1234" or pin.lower().startswith("change-me") or len(pin) < 8):
        alphabet = string.ascii_letters + string.digits
        pin = "".join(secrets.choice(alphabet) for _ in range(18))
        generated_pin = pin
        lines = set_value(lines, "ADMIN_PIN", pin)

    defaults = {
        "APP_ENV": "production",
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "FRONTEND_PUBLIC_URL": "https://shelf-ir.vercel.app",
        "ALLOWED_ORIGINS": "http://localhost:8000,http://127.0.0.1:8000,https://shelf-ir.vercel.app",
        "STORE_OPEN": "false",
        "TRUST_PROXY": "false",
        "DB_URL": "sqlite:///./data/smartshelf.db",
        "UPLOAD_DIR": "./data/uploads",
        "TOKEN_TTL_SECONDS": "28800",
        "ENTRY_TOKEN_TTL_SECONDS": "30",
        "STABLE_SECONDS": "1.5",
        "RECOGNITION_MODEL_PATH": "ai/models/identity-disabled-until-validated.onnx",
    }
    for key, value in defaults.items():
        lines = set_value(lines, key, value)

    # Keep a previously configured real HTTPS Funnel URL; otherwise use local HTTP until Funnel is enabled.
    public_url = values.get("PUBLIC_BASE_URL", "")
    if not public_url.startswith("https://") or ".ts.net" not in public_url:
        lines = set_value(lines, "PUBLIC_BASE_URL", "http://127.0.0.1:8000")

    ENV.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print("[OK] Private .env prepared. Secrets are stored only on this Windows computer.")
    print("[OK] Database: data\\smartshelf.db")
    print("[OK] Uploads:  data\\uploads")
    print("[OK] STORE_OPEN=false")
    if generated_pin:
        print("\nNEW SMARTSHELF ADMIN PIN (save it in a password manager; it will not be shown again):")
        print(generated_pin)
    else:
        print("[OK] Existing ADMIN_PIN preserved; it was not displayed or changed.")


if __name__ == "__main__":
    main()
