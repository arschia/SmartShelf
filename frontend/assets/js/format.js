/**
 * SMARTSHELF Localization & Formatting Utilities
 * Standard Iranian Persian Formats: Numbers, Toman Currency, Jalali Dates & Digit Normalization.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.SmartShelfFormat = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Persian Number Formatter
  var faNumberFormatter = null;
  try {
    faNumberFormatter = new Intl.NumberFormat('fa-IR');
  } catch (e) {
    faNumberFormatter = null;
  }

  // Persian-Arabic digit mapping to Latin
  var PERSIAN_ARABIC_DIGIT_MAP = {
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
  };

  var LATIN_TO_PERSIAN_MAP = {
    '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
    '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
  };

  /**
   * Converts all Persian and Arabic digits in a string to standard Latin digits (0-9).
   * @param {string|number} input
   * @returns {string}
   */
  function normalizeDigits(input) {
    if (input === null || input === undefined) return '';
    var str = String(input);
    return str.replace(/[۰-۹٠-٩]/g, function (char) {
      return PERSIAN_ARABIC_DIGIT_MAP[char] || char;
    });
  }

  // Keyboard digits and invisible direction markers must not invalidate a code.
  // Keep other characters so malformed codes are rejected rather than coerced.
  function normalizePairingCode(input) {
    return normalizeDigits(input).replace(/[\s\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]/g, '');
  }

  /**
   * Converts Latin digits in a string or number to Persian digits.
   * @param {string|number} input
   * @returns {string}
   */
  function toPersianDigits(input) {
    if (input === null || input === undefined) return '';
    var str = String(input);
    return str.replace(/[0-9]/g, function (char) {
      return LATIN_TO_PERSIAN_MAP[char] || char;
    });
  }

  /**
   * Formats a number with Persian digits and thousands separator.
   * @param {number|string} value
   * @returns {string}
   */
  function formatNumber(value) {
    if (value === null || value === undefined || isNaN(Number(value))) {
      return toPersianDigits(value || '0');
    }
    var num = Number(value);
    if (faNumberFormatter) {
      return faNumberFormatter.format(num);
    }
    // Fallback if Intl is unavailable
    var parts = num.toString().split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '٬');
    return toPersianDigits(parts.join('٫'));
  }

  /**
   * Formats an amount into Iranian Toman with thousands separator.
   * Example: 12500 -> "۱۲٬۵۰۰ تومان"
   * @param {number|string} amount
   * @returns {string}
   */
  function formatToman(amount) {
    var formattedNum = formatNumber(amount || 0);
    return formattedNum + ' تومان';
  }

  /**
   * Formats a Date object, timestamp, or ISO string into Jalali (Shamsi) calendar.
   * @param {Date|string|number} dateInput
   * @param {Intl.DateTimeFormatOptions} [options]
   * @returns {string}
   */
  function formatJalali(dateInput, options) {
    if (!dateInput) return '';
    var d = dateInput instanceof Date ? dateInput : new Date(dateInput);
    if (isNaN(d.getTime())) return '';

    var defaultOptions = {
      calendar: 'persian',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    };

    var opts = Object.assign({}, defaultOptions, options || {});

    try {
      return new Intl.DateTimeFormat('fa-IR-u-ca-persian', opts).format(d);
    } catch (e) {
      // Fallback
      return d.toLocaleDateString('fa-IR');
    }
  }

  /**
   * GS1 GTIN Validation & Normalization
   * Lengths: 8, 12, 13, 14 digits.
   * Alternating weights 3 and 1 from right to left (excluding check digit).
   * @param {string} gtinInput
   * @returns {{valid: boolean, error: string|null, clean: string, gtin14: string, formatName: string}}
   */
  function validateGtin(gtinInput) {
    if (!gtinInput || typeof gtinInput !== 'string' || !gtinInput.trim()) {
      return { valid: false, error: 'کد GTIN الزامی است', clean: '', gtin14: '', formatName: '' };
    }
    var clean = normalizeDigits(gtinInput).trim();
    if (!/^\d+$/.test(clean)) {
      return { valid: false, error: 'کد GTIN فقط باید شامل ارقام عددی باشد', clean: clean, gtin14: '', formatName: '' };
    }
    var validLengths = [8, 12, 13, 14];
    if (validLengths.indexOf(clean.length) === -1) {
      return {
        valid: false,
        error: 'طول بارکد نامعتبر است (باید ۸، ۱۲، ۱۳ یا ۱۴ رقم باشد)',
        clean: clean,
        gtin14: '',
        formatName: ''
      };
    }
    var digits = clean.split('').map(Number);
    var providedCheck = digits[digits.length - 1];
    var core = digits.slice(0, digits.length - 1);

    var total = 0;
    var weight = 3;
    for (var i = core.length - 1; i >= 0; i--) {
      total += core[i] * weight;
      weight = (weight === 3) ? 1 : 3;
    }
    var expectedCheck = (10 - (total % 10)) % 10;
    if (providedCheck !== expectedCheck) {
      return {
        valid: false,
        error: 'رقم کنترلی GS1 اشتباه است (رقم کنترلی مورد انتظار: ' + expectedCheck + ')',
        clean: clean,
        gtin14: '',
        formatName: ''
      };
    }
    var gtin14 = clean.padStart(14, '0');
    var formatName = clean.length === 8 ? 'GTIN-8' : clean.length === 12 ? 'UPC-A' : clean.length === 13 ? 'EAN-13' : 'GTIN-14';
    return {
      valid: true,
      error: null,
      clean: clean,
      gtin14: gtin14,
      formatName: formatName
    };
  }

  return {
    normalizeDigits: normalizeDigits,
    normalizePairingCode: normalizePairingCode,
    toPersianDigits: toPersianDigits,
    formatNumber: formatNumber,
    formatToman: formatToman,
    formatJalali: formatJalali,
    validateGtin: validateGtin
  };
});
