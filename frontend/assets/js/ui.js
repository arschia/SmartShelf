/**
 * SMARTSHELF Interactive UI Component Controller
 * Manages Theme, Direction, Sheets, Modals, Toasts, Steppers, and Haptics.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define(['./format.js'], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./format.js'));
  } else {
    root.SmartShelfUI = factory(root.SmartShelfFormat);
  }
})(typeof self !== 'undefined' ? self : this, function (Format) {
  'use strict';

  /* ==========================================================================
     Theme Management (Light / Dark)
     ========================================================================== */
  var THEME_KEY = 'smartshelf_theme';

  function getPreferredTheme() {
    var stored = localStorage.getItem(THEME_KEY);
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  function setTheme(theme) {
    if (theme !== 'light' && theme !== 'dark') return;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || getPreferredTheme();
    var next = current === 'dark' ? 'light' : 'dark';
    setTheme(next);
    return next;
  }

  function initTheme() {
    var theme = getPreferredTheme();
    document.documentElement.setAttribute('data-theme', theme);

    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
        if (!localStorage.getItem(THEME_KEY)) {
          setTheme(e.matches ? 'dark' : 'light');
        }
      });
    }
  }

  /* ==========================================================================
     Direction Management (RTL / LTR)
     ========================================================================== */
  var DIR_KEY = 'smartshelf_dir';

  function setDirection(dir) {
    var d = dir === 'ltr' ? 'ltr' : 'rtl';
    document.documentElement.setAttribute('dir', d);
    localStorage.setItem(DIR_KEY, d);
    window.dispatchEvent(new CustomEvent('dirchange', { detail: { dir: d } }));
  }

  function toggleDirection() {
    var current = document.documentElement.getAttribute('dir') || 'rtl';
    var next = current === 'rtl' ? 'ltr' : 'rtl';
    setDirection(next);
    return next;
  }

  function initDirection() {
    var stored = localStorage.getItem(DIR_KEY) || 'rtl';
    setDirection(stored);
  }

  /* ==========================================================================
     Haptic Feedback (Mobile Vibration)
     ========================================================================== */
  function triggerHaptic(pattern) {
    try {
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        navigator.vibrate(pattern || 15);
      }
    } catch (e) {
      // Ignore vibration errors
    }
  }

  /* ==========================================================================
     Toast / Snackbar with Undo Action
     ========================================================================== */
  var toastContainer = null;

  function ensureToastContainer() {
    if (!toastContainer) {
      toastContainer = document.querySelector('.toast-container');
      if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
      }
    }
    return toastContainer;
  }

  /**
   * Shows a toast notification.
   * @param {Object} options
   * @param {string} options.message
   * @param {string} [options.type='neutral'] 'success' | 'warning' | 'danger' | 'info' | 'neutral'
   * @param {string} [options.undoText='بازگردانی']
   * @param {Function} [options.onUndo]
   * @param {number} [options.duration=4000]
   */
  function showToast(options) {
    var container = ensureToastContainer();
    var opts = Object.assign({
      message: '',
      type: 'neutral',
      undoText: 'بازگردانی',
      onUndo: null,
      duration: 4000
    }, options);

    var toastEl = document.createElement('div');
    toastEl.className = 'toast';
    toastEl.setAttribute('role', 'alert');

    var messageEl = document.createElement('div');
    messageEl.className = 'toast-message';
    messageEl.textContent = opts.message;
    toastEl.appendChild(messageEl);

    if (typeof opts.onUndo === 'function') {
      var undoBtn = document.createElement('button');
      undoBtn.className = 'toast-undo';
      undoBtn.type = 'button';
      undoBtn.textContent = opts.undoText;
      undoBtn.addEventListener('click', function () {
        opts.onUndo();
        dismiss();
      });
      toastEl.appendChild(undoBtn);
    }

    container.appendChild(toastEl);
    // Trigger reflow for slide/fade animation
    void toastEl.offsetHeight;
    toastEl.classList.add('show');
    triggerHaptic(10);

    var timer = setTimeout(dismiss, opts.duration);

    function dismiss() {
      clearTimeout(timer);
      toastEl.classList.remove('show');
      setTimeout(function () {
        if (toastEl.parentNode) {
          toastEl.parentNode.removeChild(toastEl);
        }
      }, 300);
    }

    return { dismiss: dismiss };
  }

  /* ==========================================================================
     Bottom Sheet (with Swipe & Drag to dismiss)
     ========================================================================== */
  function openBottomSheet(sheetEl, backdropEl) {
    if (typeof sheetEl === 'string') sheetEl = document.querySelector(sheetEl);
    if (!sheetEl) return;

    if (!backdropEl) {
      backdropEl = document.querySelector('.sheet-backdrop');
    }

    if (backdropEl) backdropEl.classList.add('active');
    sheetEl.classList.add('open');
    sheetEl.setAttribute('aria-hidden', 'false');

    // Attach touch drag listener
    attachSheetDrag(sheetEl, backdropEl);
  }

  function closeBottomSheet(sheetEl, backdropEl) {
    if (typeof sheetEl === 'string') sheetEl = document.querySelector(sheetEl);
    if (!sheetEl) return;

    if (!backdropEl) {
      backdropEl = document.querySelector('.sheet-backdrop');
    }

    sheetEl.style.transform = '';
    sheetEl.classList.remove('open');
    sheetEl.setAttribute('aria-hidden', 'true');
    if (backdropEl) backdropEl.classList.remove('active');
  }

  function attachSheetDrag(sheetEl, backdropEl) {
    var startY = 0;
    var currentY = 0;
    var isDragging = false;
    var handleBar = sheetEl.querySelector('.sheet-handle-bar') || sheetEl;

    function onTouchStart(e) {
      startY = e.touches[0].clientY;
      currentY = startY;
      isDragging = true;
      sheetEl.style.transition = 'none';
    }

    function onTouchMove(e) {
      if (!isDragging) return;
      currentY = e.touches[0].clientY;
      var deltaY = currentY - startY;
      if (deltaY > 0) {
        sheetEl.style.transform = 'translateY(' + deltaY + 'px)';
      }
    }

    function onTouchEnd() {
      if (!isDragging) return;
      isDragging = false;
      sheetEl.style.transition = '';
      var deltaY = currentY - startY;
      if (deltaY > 120) {
        closeBottomSheet(sheetEl, backdropEl);
      } else {
        sheetEl.style.transform = '';
      }
    }

    handleBar.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('touchend', onTouchEnd, { passive: true });
  }

  /* ==========================================================================
     Modal Controller
     ========================================================================== */
  function openModal(modalBackdropEl) {
    if (typeof modalBackdropEl === 'string') modalBackdropEl = document.querySelector(modalBackdropEl);
    if (!modalBackdropEl) return;
    modalBackdropEl.classList.add('active');
    modalBackdropEl.setAttribute('aria-hidden', 'false');

    // Trap escape key
    function onKeyDown(e) {
      if (e.key === 'Escape') {
        closeModal(modalBackdropEl);
        window.removeEventListener('keydown', onKeyDown);
      }
    }
    window.addEventListener('keydown', onKeyDown);
  }

  function closeModal(modalBackdropEl) {
    if (typeof modalBackdropEl === 'string') modalBackdropEl = document.querySelector(modalBackdropEl);
    if (!modalBackdropEl) return;
    modalBackdropEl.classList.remove('active');
    modalBackdropEl.setAttribute('aria-hidden', 'true');
  }

  /* ==========================================================================
     Quantity Stepper Helper
     ========================================================================== */
  function initStepper(containerEl, options) {
    if (typeof containerEl === 'string') containerEl = document.querySelector(containerEl);
    if (!containerEl) return;

    var opts = Object.assign({
      initial: 1,
      min: 0,
      max: 99,
      onChange: null
    }, options);

    var count = opts.initial;
    var plusBtn = containerEl.querySelector('[data-action="increase"]') || containerEl.querySelector('.stepper-btn:last-child');
    var minusBtn = containerEl.querySelector('[data-action="decrease"]') || containerEl.querySelector('.stepper-btn:first-child');
    var valEl = containerEl.querySelector('.stepper-value');

    function update() {
      if (valEl) {
        valEl.textContent = Format ? Format.toPersianDigits(count) : count;
        valEl.classList.remove('anim-count-bump');
        void valEl.offsetWidth;
        valEl.classList.add('anim-count-bump');
      }
      if (typeof opts.onChange === 'function') {
        opts.onChange(count);
      }
      triggerHaptic(10);
    }

    if (plusBtn) {
      plusBtn.addEventListener('click', function () {
        if (count < opts.max) {
          count++;
          update();
        }
      });
    }

    if (minusBtn) {
      minusBtn.addEventListener('click', function () {
        if (count > opts.min) {
          count--;
          update();
        }
      });
    }

    update();
    return {
      getValue: function () { return count; },
      setValue: function (v) { count = v; update(); }
    };
  }

  // Auto-init on DOMContentLoaded
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        initTheme();
        initDirection();
      });
    } else {
      initTheme();
      initDirection();
    }
  }

  return {
    getPreferredTheme: getPreferredTheme,
    setTheme: setTheme,
    toggleTheme: toggleTheme,
    setDirection: setDirection,
    toggleDirection: toggleDirection,
    triggerHaptic: triggerHaptic,
    showToast: showToast,
    openBottomSheet: openBottomSheet,
    closeBottomSheet: closeBottomSheet,
    openModal: openModal,
    closeModal: closeModal,
    initStepper: initStepper
  };
});
