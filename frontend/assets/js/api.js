/**
 * SMARTSHELF Shared API & WebSocket Routing Module
 * Supports runtime backend discovery, Tailscale Funnel URL configuration, and Vercel separation.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.SmartShelfApi = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const STORAGE_KEY = 'smartshelf_api_base';

  // 1. Check for ?api= query parameter and persist to localStorage
  try {
    if (typeof window !== 'undefined' && window.location) {
      const urlParams = new URLSearchParams(window.location.search);
      const apiParam = urlParams.get('api');
      // Only one-time customer entry links may bootstrap a backend URL.
      // Never allow an arbitrary ?api= on /admin or /camera to redirect credentials.
      if (apiParam && /^\/enter\/?$/.test(window.location.pathname)) {
        const cleanParam = apiParam.trim().replace(/\/+$/, '');
        const candidate = new URL(cleanParam);
        if (candidate.protocol === 'https:' && !candidate.username && !candidate.password &&
            !candidate.search && !candidate.hash && candidate.pathname === '/') {
          const configured = window.SMARTSHELF_CONFIG && window.SMARTSHELF_CONFIG.apiBase;
          if (!configured || configured.replace(/\/+$/, '') === candidate.origin) {
            localStorage.setItem(STORAGE_KEY, candidate.origin);
          }
        }
      }
    }
  } catch (e) {
    console.warn('[SmartShelfApi] Could not access URL parameters or localStorage:', e);
  }

  /**
   * Determine the current backend base URL based on hierarchy:
   * 1. ?api= query param (saved in localStorage)
   * 2. localStorage ('smartshelf_api_base')
   * 3. window.SMARTSHELF_CONFIG.apiBase
   * 4. Current page origin (window.location.origin)
   */
  function getApiBase() {
    let base = '';
    try {
      base = localStorage.getItem(STORAGE_KEY) || '';
    } catch (e) {}

    if (!base && typeof window !== 'undefined') {
      if (window.SMARTSHELF_CONFIG && window.SMARTSHELF_CONFIG.apiBase) {
        base = window.SMARTSHELF_CONFIG.apiBase.trim();
      }
      if (!base && window.location && window.location.origin) {
        const host = (window.location.hostname || "").toLowerCase();
        // Vercel hosts only the static UI in this architecture. Never mistake
        // the public frontend origin for the FastAPI/WebSocket backend.
        if (!host.endsWith(".vercel.app") && host !== "vercel.app") {
          base = window.location.origin;
        }
      }
    }

    base = (base || '').replace(/\/+$/, '');

    // Enforce HTTPS if the page is currently loaded over HTTPS
    if (typeof window !== 'undefined' && window.location && window.location.protocol === 'https:') {
      if (base.startsWith('http://') && !base.includes('localhost') && !base.includes('127.0.0.1')) {
        base = 'https://' + base.slice(7);
      }
    }

    return base;
  }

  function setApiBase(newBase) {
    const clean = (newBase || '').trim().replace(/\/+$/, '');
    if (clean) {
      localStorage.setItem(STORAGE_KEY, clean);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    return getApiBase();
  }

  function resetApiBase() {
    localStorage.removeItem(STORAGE_KEY);
    return getApiBase();
  }

  /**
   * Build an absolute HTTP/HTTPS API URL for the given path.
   */
  function apiUrl(path) {
    const base = getApiBase();
    if (!base) {
      throw new Error('آدرس بک‌اند تنظیم نشده است؛ از تنظیمات سرور، آدرس HTTPS تونل FastAPI را وارد کنید.');
    }
    const cleanPath = (path || '').replace(/^\/+/, '');
    return `${base}/${cleanPath}`;
  }

  /**
   * Resolve uploaded media from the API host, not the static Vercel host.
   * Static /assets and other bundled files remain on the frontend origin.
   */
  function mediaUrl(path) {
    if (!path || typeof path !== 'string') return '/static/placeholder.png';
    if (/^https?:\/\//i.test(path)) return path;
    if (path.startsWith('/static/uploads/') || path.startsWith('/uploads/')) {
      try { return apiUrl(path); } catch (_) { return '/static/placeholder.png'; }
    }
    return path;
  }

  /**
   * Build an absolute WS/WSS WebSocket URL for the given path.
   */
  function wsUrl(path) {
    const base = getApiBase();
    if (!base) {
      throw new Error('آدرس بک‌اند تنظیم نشده است؛ اتصال WSS دوربین برقرار نمی‌شود.');
    }
    let wsBase = base;

    if (wsBase.startsWith('https://')) {
      wsBase = 'wss://' + wsBase.slice(8);
    } else if (wsBase.startsWith('http://')) {
      wsBase = 'ws://' + wsBase.slice(7);
    } else if (typeof window !== 'undefined' && window.location) {
      const isHttps = window.location.protocol === 'https:';
      wsBase = (isHttps ? 'wss://' : 'ws://') + window.location.host;
    }

    // Force wss if page is loaded on https
    if (typeof window !== 'undefined' && window.location && window.location.protocol === 'https:') {
      if (wsBase.startsWith('ws://')) {
        wsBase = 'wss://' + wsBase.slice(5);
      }
    }

    const cleanPath = (path || '').replace(/^\/+/, '');
    return `${wsBase}/${cleanPath}`;
  }

  /**
   * Check health of the currently configured server.
   */
  async function checkServerHealth() {
    let url = '';
    try {
      url = apiUrl('/api/health');
      const res = await fetch(url, { method: 'GET', cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        return { online: true, status: data.status || 'ok', url };
      }
      return { online: false, status: `HTTP ${res.status}`, url };
    } catch (err) {
      return { online: false, status: err.message || 'Offline', url };
    }
  }

  /**
   * Modal dialog to view and update the backend server URL.
   */
  function showServerConfigModal() {
    let modal = document.getElementById('smartShelfServerModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'smartShelfServerModal';
      modal.style.cssText = `
        position: fixed; inset: 0; z-index: 99999;
        background: rgba(11, 19, 43, 0.85); backdrop-filter: blur(4px);
        display: flex; align-items: center; justify-content: center; padding: 1rem;
        font-family: 'Dana', system-ui, sans-serif; direction: rtl;
      `;
      document.body.appendChild(modal);
    }

    const currentBase = getApiBase();
    modal.innerHTML = `
      <div style="background: #1c2541; border: 1px solid #3a506b; border-radius: 12px; width: 100%; max-width: 440px; padding: 1.5rem; color: #f0f4f8; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
          <h3 style="margin: 0; font-size: 1.1rem; display: flex; align-items: center; gap: 0.5rem;">
            ⚙️ تنظیم آدرس سرور بک‌اند
          </h3>
          <button id="closeServerModalBtn" style="background: none; border: none; color: #94a3b8; font-size: 1.3rem; cursor: pointer;">&times;</button>
        </div>
        <p style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem;">
          در صورت تغییر آدرس تونل یا اجرای بک‌اند روی سرور دیگر، آدرس سرور را در این قسمت تنظیم نمایید.
        </p>
        <div style="margin-bottom: 1rem;">
          <label style="display: block; font-size: 0.82rem; margin-bottom: 0.35rem; color: #cbd5e1;">آدرس سرور (API Base URL):</label>
          <input type="text" id="serverBaseInput" dir="ltr"
                 style="width: 100%; box-sizing: border-box; background: #111a36; border: 1px solid #3a506b; border-radius: 6px; padding: 0.55rem; color: #fff; font-family: monospace; font-size: 0.9rem;">
        </div>
        <div id="serverHealthResult" style="padding: 0.6rem; border-radius: 6px; font-size: 0.82rem; margin-bottom: 1rem; background: #111a36; border: 1px solid #232f52;">
          در حال بررسی وضعیت اتصال...
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
          <button id="resetServerBtn" style="background: #232f52; border: 1px solid #3a506b; color: #cbd5e1; border-radius: 6px; padding: 0.5rem 0.8rem; cursor: pointer; font-size: 0.85rem;">
            بازنشانی به پیش‌فرض
          </button>
          <button id="saveServerBtn" style="background: #00b4d8; border: none; color: #0b132b; font-weight: bold; border-radius: 6px; padding: 0.5rem 1rem; cursor: pointer; font-size: 0.85rem;">
            ذخیره و اتصال
          </button>
        </div>
      </div>
    `;

    modal.style.display = 'flex';

    const healthEl = modal.querySelector('#serverHealthResult');
    const inputEl = modal.querySelector('#serverBaseInput');

    inputEl.value = currentBase;
    const runHealthCheck = async () => {
      healthEl.textContent = 'در حال بررسی اتصال به ' + (inputEl.value || currentBase) + '...';
      healthEl.style.color = '#94a3b8';
      const res = await checkServerHealth();
      if (res.online) {
        healthEl.textContent = `🟢 سرور آنلاین است (وضعیت: ${res.status})`;
        healthEl.style.color = '#10b981';
      } else {
        healthEl.textContent = `🔴 عدم برقراری ارتباط با سرور (${res.status})`;
        healthEl.style.color = '#ef4444';
      }
    };
    runHealthCheck();

    modal.querySelector('#closeServerModalBtn').onclick = () => { modal.style.display = 'none'; };
    modal.querySelector('#resetServerBtn').onclick = () => {
      resetApiBase();
      inputEl.value = getApiBase();
      runHealthCheck();
    };
    modal.querySelector('#saveServerBtn').onclick = () => {
      setApiBase(inputEl.value);
      modal.style.display = 'none';
      window.location.reload();
    };
  }

  return {
    getApiBase,
    setApiBase,
    resetApiBase,
    apiUrl,
    mediaUrl,
    wsUrl,
    checkServerHealth,
    showServerConfigModal
  };
});
