"""
SMARTSHELF GTIN (Global Trade Item Number) Validation and Normalization Service
Compliant with GS1 Specifications.
"""
from typing import Tuple, Optional


PERSIAN_ARABIC_DIGIT_MAP = {
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
}


def normalize_digits(input_str: Optional[str]) -> str:
    """Normalize Persian and Arabic digits to Latin 0-9 and strip whitespace."""
    if not input_str:
        return ""
    result = []
    for ch in str(input_str).strip():
        result.append(PERSIAN_ARABIC_DIGIT_MAP.get(ch, ch))
    return "".join(result)


def calculate_gs1_check_digit(digits_without_check: str) -> int:
    """
    Calculate GS1 Check Digit for standard GTINs (GTIN-8, GTIN-12, GTIN-13, GTIN-14).
    Alternating weights 3 and 1 from right to left:
    Sum = sum(digit * weight)
    Check digit = (10 - (Sum % 10)) % 10
    """
    weights = [3 if i % 2 == 0 else 1 for i in range(len(digits_without_check))]
    total = sum(int(d) * w for d, w in zip(reversed(digits_without_check), weights))
    return (10 - (total % 10)) % 10


def validate_and_normalize_gtin(raw_gtin: Optional[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Validates a GTIN string.
    Returns: (is_valid, normalized_gtin, gtin14, error_message)
    """
    if not raw_gtin:
        return False, None, None, "بارکد GTIN نمی‌تواند خالی باشد"

    cleaned = normalize_digits(raw_gtin)

    if not cleaned.isdigit():
        return False, None, None, "بارکد فقط باید شامل ارقام باشد"

    length = len(cleaned)
    if length not in (8, 12, 13, 14):
        return False, None, None, f"طول بارکد نامعتبر است ({length} رقم). طول استاندارد باید ۸، ۱۲، ۱۳ یا ۱۴ رقم باشد"

    payload = cleaned[:-1]
    provided_check = int(cleaned[-1])
    expected_check = calculate_gs1_check_digit(payload)

    if provided_check != expected_check:
        return False, None, None, f"رقم کنترلی GS1 بارکد نادرست است (رقم وارد شده: {provided_check}، رقم صحیح محاسبه‌شده: {expected_check})"

    # Normalize to 14 digits with leading zeros
    gtin14 = cleaned.zfill(14)

    return True, cleaned, gtin14, None
