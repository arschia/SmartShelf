"""Generate secure random SECRET_KEY and strong ADMIN_PIN for SMARTSHELF."""
import secrets
import string

def main():
    secret_key = secrets.token_hex(32)
    chars = string.ascii_letters + string.digits + "!@#$^*"
    pin = (
        "".join(secrets.choice(string.ascii_letters) for _ in range(4))
        + "".join(secrets.choice(string.digits) for _ in range(4))
        + "".join(secrets.choice("!@#$^*") for _ in range(2))
        + "".join(secrets.choice(chars) for _ in range(2))
    )
    pin_list = list(pin)
    secrets.SystemRandom().shuffle(pin_list)
    strong_pin = "".join(pin_list)

    print("========================================================")
    print("  SMARTSHELF Secret Key and Admin PIN Generator")
    print("========================================================")
    print()
    print("Generated SECRETS:")
    print("--------------------------------------------------------")
    print(f"SECRET_KEY={secret_key}")
    print(f"ADMIN_PIN={strong_pin}")
    print("--------------------------------------------------------")
    print("Copy the above values into your .env file.")
    print()

if __name__ == "__main__":
    main()
