/**
 * SMARTSHELF Admin Dashboard Application Logic
 * Vanilla JavaScript (No build step, fully local)
 */

// Global state
let currentLang = localStorage.getItem("smartshelf_lang") || "fa";
let allProducts = [];
let allZones = [];
let allSessions = [];
let adminToken = sessionStorage.getItem("smartshelf_admin_token") || "";

// Localization dictionary
const i18nData = {
  fa: {
    login_title: "ورود به پنل مدیریت",
    login_subtitle: "رمز عبور ادمین (PIN) را وارد کنید",
    login_btn: "تأیید و ورود",
    status_online: "سرور فعال",
    logout: "خروج",
    tab_overview: "نمای کلی",
    tab_entry_qr: "ورود (QR)",
    tab_sessions: "جلسات",
    tab_invoices: "فاکتورها",
    tab_products: "محصولات",
    tab_recognition: "تشخیص حضور و شناسایی محصول",
    tab_devices: "دستگاه‌ها",
    tab_events: "رویدادها",
    overview_title: "📊 نمای کلی فروشگاه",
    placeholder_title: "این بخش در مرحله ۳ فعال خواهد شد",
    placeholder_desc: "مانیتورینگ وضعیت قفسه، وضعیت مشتری فعال، و آمار لحظه‌ای.",
    qr_title: "📱 کیوآر کد ورود مشتری (Entry QR)",
    refresh_qr: "تولید مجدد کد",
    store_occupied_title: "فروشگاه اشغال است",
    store_occupied_desc: "یک مشتری در حال حاضر داخل فروشگاه است. طبق محدودیت MVP تا زمان خروج مشتری فعلی، صدور کد ورود جدید متوقف است.",
    current_session: "جلسه فعال:",
    entry_time_label: "زمان ورود:",
    goto_sessions: "مشاهده و مدیریت جلسات",
    token_validity: "اعتبار کد:",
    seconds: "ثانیه",
    entry_url_label: "آدرس ورود مشتری (جهت تست یا کپی مستقیم):",
    copy_url: "کپی لینک",
    open_tab: "باز کردن در مرورگر",
    qr_hint: "مشتری با اسکن این کیوآر کد با دوربین گوشی، به صفحه سبد خرید متصل می‌شود. توکن هر ۳۰ ثانیه منقضی می‌گردد.",
    sessions_title: "👥 جلسات مشتریان (Customer Sessions)",
    refresh: "بروزرسانی",
    col_session_id: "شناسه",
    col_status: "وضعیت",
    col_entered_at: "زمان ورود",
    col_exited_at: "زمان خروج",
    col_duration: "مدت حضور",
    col_exit_reason: "دلیل خروج",
    col_actions: "عملیات",
    loading: "در حال بارگذاری...",
    no_sessions: "هیچ جلسه‌ای ثبت نشده است",
    btn_force_close: "بستن اجباری جلسه",
    force_close_confirm: "آیا از بستن اجباری این جلسه فعال اطمینان دارید؟",
    force_close_success: "جلسه با موفقیت بسته شد",
    copied_to_clipboard: "لینک در کلیپ‌بورد کپی شد",
    active_status: "فعال",
    closed_status: "بسته شده",
    customer_entered_toast: "مشتری جدید وارد شد (جلسه #{id})",
    session_closed_toast: "جلسه #{id} بسته شد ({reason})",
    invoices_title: "🧾 صورتحساب‌ها و فاکتورها",
    placeholder_invoices_title: "سوابق مالی و تسویه‌حساب‌ها",
    placeholder_invoices_desc: "مشاهده و چاپ فاکتورهای پرداخت‌شده مشتریان در مرحله ۵.",
    devices_title: "📟 دستگاه‌های متصل شبکه (Registered Devices)",
    placeholder_devices_title: "مانیتورینگ تبلت و موبایل",
    placeholder_devices_desc: "نمایش تبلت حسگر و گوشی مشتری در مرحله ۳ و ۴ فعال خواهد شد.",
    cam_feed_title: "پیش‌نمایش زنده حسگر دوربین تبلت (Tablet Camera Feed)",
    no_camera_connected: "تبلت دوربین هنوز متصل نشده است",
    open_camera_hint: "در تبلت آدرس /camera را باز کنید",
    telemetry_fps: "نرخ فریم ویدیوی زنده:",
    telemetry_res: "رزولوشن فریم:",
    telemetry_frames: "مجموع فریم‌ها:",
    privacy_note: "حفظ حریم خصوصی: تمام فریم‌ها صرفاً در حافظه RAM سرور پردازش شده و هیچ فایلی روی دیسک ذخیره نمی‌گردد.",
    col_device_id: "شناسه دستگاه",
    col_device_role: "نقش دستگاه",
    col_last_seen: "آخرین فعالیت",
    device_online_toast: "دستگاه {id} آنلاین شد",
    device_offline_toast: "دستگاه {id} آفلاین شد",
    role_camera: "حسگر دوربین (CAMERA)",
    role_customer: "مشتری (CUSTOMER)",
    role_admin: "ادمین (ADMIN)",
    btn_calibration: "کالیبراسیون و تنظیم ROI جایگاه‌ها",
    calib_modal_title: "📐 کالیبراسیون بینایی جایگاه‌های قفسه (ROI Calibration)",
    calib_instructions: "۱. جایگاه مورد نظر را انتخاب کرده و با کشیدن ماوس روی تصویر، مستطیل (ROI) را تنظیم کنید. ۲. دکمه «ذخیره ROI» را بزنید. ۳. برای ثبت مشخصات بصری، دکمه «ثبت مرجع پر» و «ثبت مرجع خالی» را فشار دهید.",
    select_slot_to_edit: "انتخاب جایگاه:",
    btn_save_roi: "💾 ذخیره مختصات ROI",
    btn_cap_full: "ثبت مرجع پر این جایگاه",
    btn_cap_empty: "ثبت مرجع خالی این جایگاه",
    btn_cap_all_full: "ثبت مرجع پر (همه ۳ جایگاه)",
    btn_close: "بستن",
    roi_saved_success: "مختصات ROI با موفقیت ذخیره شد",
    ref_captured_success: "مرجع بصری با موفقیت در رم ثبت شد",
    state_present: "موجود (پر)",
    state_absent: "برداشته‌شده (خالی)",
    state_transition: "در حال تغییر...",
    state_unknown: "نامشخص",
    events_title: "لاگ رویدادهای زنده سیستم",
    metric_today_sessions: "جلسات امروز",
    metric_active_customer: "مشتری در فروشگاه",
    metric_total_invoices: "تعداد فاکتورها",
    metric_total_revenue: "فروش شبیه‌سازی‌شده",
    overview_slots_title: "وضعیت زنده ۳ جایگاه قفسه",
    overview_devices_title: "وضعیت تجهیزات متصل",
    col_invoice: "فاکتور مرتبط",
    col_invoice_id: "شماره فاکتور",
    col_invoice_time: "زمان صدور",
    col_items_count: "تعداد اقلام",
    col_total: "مبلغ کل (تومان)",
    th_event_time: "زمان رویداد",
    th_event_type: "نوع رویداد",
    th_zone: "جایگاه",
    th_product: "کالا / جزئیات",
    th_confidence: "اطمینان",
    search_event_placeholder: "جست‌وجوی رویداد، کالا، جلسه...",
    shelf_slots_title: "وضعیت جایگاه‌های قفسه (۳ اسلات فیزیکی)",
    product_catalog_title: "کاتالوگ و انبار محصولات",
    btn_add_product: "محصول جدید",
    search_placeholder: "جست‌وجوی نام کالا یا SKU...",
    th_image: "تصویر",
    th_name: "نام محصول",
    th_sku: "کد SKU",
    th_price: "قیمت واحد (تومان)",
    th_slot: "جایگاه قفسه",
    th_status: "وضعیت",
    th_actions: "عملیات",
    modal_add_title: "افزودن محصول جدید",
    modal_edit_title: "ویرایش محصول",
    form_name: "نام محصول *",
    form_sku: "کد SKU *",
    form_price: "قیمت واحد (تومان) *",
    form_desc: "توضیحات",
    form_image: "تصویر محصول",
    form_active: "کالا فعال و قابل عرضه است",
    btn_cancel: "انصراف",
    btn_save: "ذخیره محصول",
    active: "فعال",
    inactive: "غیرفعال",
    unassigned: "تخصیص نیافته",
    slot_full: "پر (دارای کالا)",
    slot_empty: "خالی",
    assign_placeholder: "انتخاب کالا برای این جایگاه...",
    delete_confirm: "آیا از حذف این محصول مطمئن هستید؟",
    login_failed: "رمز عبور نادرست است",
    save_success: "محصول با موفقیت ذخیره شد",
    delete_success: "محصول حذف شد",
    assign_success: "جایگاه به‌روزرسانی شد"
  },
  en: {
    login_title: "Admin Panel Login",
    login_subtitle: "Enter the Admin PIN code",
    login_btn: "Verify & Login",
    status_online: "Server Online",
    logout: "Logout",
    tab_overview: "Overview",
    tab_entry_qr: "Entry (QR)",
    tab_sessions: "Sessions",
    tab_invoices: "Invoices",
    tab_products: "Products",
    tab_recognition: "Presence & Product Recognition",
    tab_devices: "Devices",
    tab_events: "Events",
    overview_title: "📊 Store Overview",
    placeholder_title: "This section will be activated in Phase 3",
    placeholder_desc: "Live shelf monitoring, active customer tracking, and real-time statistics.",
    qr_title: "📱 Customer Entry QR Code",
    refresh_qr: "Regenerate Code",
    store_occupied_title: "Store is Occupied",
    store_occupied_desc: "A customer is currently in the store. Per MVP single-customer limit, new entry tokens are suspended until they exit.",
    current_session: "Active Session:",
    entry_time_label: "Entry Time:",
    goto_sessions: "View & Manage Sessions",
    token_validity: "Valid For:",
    seconds: "seconds",
    entry_url_label: "Customer Entry URL (For direct testing / copying):",
    copy_url: "Copy Link",
    open_tab: "Open in Browser",
    qr_hint: "Customer scans this QR code with their default camera to enter. Token rotates every 30 seconds.",
    sessions_title: "👥 Customer Sessions",
    refresh: "Refresh",
    col_session_id: "ID",
    col_status: "Status",
    col_entered_at: "Entered At",
    col_exited_at: "Exited At",
    col_duration: "Duration",
    col_exit_reason: "Exit Reason",
    col_actions: "Actions",
    loading: "Loading...",
    no_sessions: "No sessions recorded yet",
    btn_force_close: "Force Close Session",
    force_close_confirm: "Are you sure you want to force close this active session?",
    force_close_success: "Session closed successfully",
    copied_to_clipboard: "Link copied to clipboard",
    active_status: "ACTIVE",
    closed_status: "CLOSED",
    customer_entered_toast: "Customer entered (Session #{id})",
    session_closed_toast: "Session #{id} closed ({reason})",
    invoices_title: "🧾 Invoices & Receipts",
    placeholder_invoices_title: "Session Invoices & Billing",
    placeholder_invoices_desc: "View and print customer receipts in Phase 5.",
    devices_title: "📟 Connected Devices (Registered Devices)",
    placeholder_devices_title: "Tablet and Mobile Monitoring",
    placeholder_devices_desc: "Camera tablet sensor & customer mobile live status in Phase 3 & 4.",
    cam_feed_title: "Live Tablet Camera Feed (Sensor Stream)",
    no_camera_connected: "Tablet camera is not connected yet",
    open_camera_hint: "Open /camera on the tablet to connect",
    telemetry_fps: "Live Video FPS:",
    telemetry_res: "Frame Resolution:",
    telemetry_frames: "Total Frames:",
    privacy_note: "Privacy Guarantee: Frames are processed strictly in RAM. Zero files or video recordings are written to disk.",
    col_device_id: "Device ID",
    col_device_role: "Role",
    col_last_seen: "Last Seen",
    device_online_toast: "Device {id} is now online",
    device_offline_toast: "Device {id} went offline",
    role_camera: "Camera Sensor (CAMERA)",
    role_customer: "Customer (CUSTOMER)",
    role_admin: "Admin (ADMIN)",
    btn_calibration: "ROI Calibration",
    calib_modal_title: "📐 Shelf Vision ROI Calibration",
    calib_instructions: "1. Select a slot and drag with mouse on the camera frame to adjust ROI box. 2. Click 'Save ROI'. 3. Place products and capture Full/Empty references.",
    select_slot_to_edit: "Select Slot:",
    btn_save_roi: "💾 Save ROI Coordinates",
    btn_cap_full: "Capture Full Reference",
    btn_cap_empty: "Capture Empty Reference",
    btn_cap_all_full: "Capture All Full References",
    btn_close: "Close",
    roi_saved_success: "ROI coordinates saved successfully",
    ref_captured_success: "Reference features captured into RAM",
    state_present: "PRESENT (Full)",
    state_absent: "ABSENT (Empty)",
    state_transition: "TRANSITION...",
    state_unknown: "UNKNOWN",
    events_title: "System Event Log",
    metric_today_sessions: "Today's Sessions",
    metric_active_customer: "Store Customer",
    metric_total_invoices: "Total Invoices",
    metric_total_revenue: "Simulated Revenue",
    overview_slots_title: "Live Shelf Slots Status",
    overview_devices_title: "Connected Hardware",
    col_invoice: "Linked Invoice",
    col_invoice_id: "Invoice #",
    col_invoice_time: "Issued At",
    col_items_count: "Items",
    col_total: "Total (Toman)",
    th_event_time: "Event Time",
    th_event_type: "Event Type",
    th_zone: "Slot",
    th_product: "Product / Details",
    th_confidence: "Confidence",
    search_event_placeholder: "Search events, products, sessions...",
    shelf_slots_title: "Shelf Slots Status (3 Physical Slots)",
    product_catalog_title: "Product Catalog & Inventory",
    btn_add_product: "New Product",
    search_placeholder: "Search product name or SKU...",
    th_image: "Image",
    th_name: "Product Name",
    th_sku: "SKU",
    th_price: "Unit Price (Toman)",
    th_slot: "Shelf Slot",
    th_status: "Status",
    th_actions: "Actions",
    modal_add_title: "Add New Product",
    modal_edit_title: "Edit Product",
    form_name: "Product Name *",
    form_sku: "SKU Code *",
    form_price: "Unit Price (Toman) *",
    form_desc: "Description",
    form_image: "Product Image",
    form_active: "Product is active and available",
    btn_cancel: "Cancel",
    btn_save: "Save Product",
    active: "Active",
    inactive: "Inactive",
    unassigned: "Unassigned",
    slot_full: "Full",
    slot_empty: "Empty",
    assign_placeholder: "Select product for this slot...",
    delete_confirm: "Are you sure you want to delete this product?",
    login_failed: "Invalid PIN code",
    save_success: "Product saved successfully",
    delete_success: "Product deleted",
    assign_success: "Slot updated successfully"
  }
};

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// Authenticated fetch wrapper
async function authFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (adminToken) {
    headers["Authorization"] = `Bearer ${adminToken}`;
    headers["X-Admin-Token"] = adminToken;
  }
  try {
    const fullUrl = window.SmartShelfApi ? window.SmartShelfApi.apiUrl(url) : url;
    const response = await fetch(fullUrl, { ...options, headers });
    if (response.status === 401) {
      adminToken = "";
      sessionStorage.removeItem("smartshelf_admin_token");
      showLoginScreen();
    }
    // A 404 or network failure is a real backend failure. Never replace it with mock data.
    return response;
  } catch (err) {
    console.error("[SmartShelf] Backend request failed:", err);
    return new Response(
      JSON.stringify({ detail: "ارتباط با بک‌اند برقرار نشد؛ تنظیمات آدرس سرور را بررسی کنید." }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

// Switch UI between Login Screen and Dashboard
function showLoginScreen() {
  stopCameraMonitor();
  const frame = document.getElementById("presenceAdminFrame");
  if (frame?.contentWindow) {
    frame.contentWindow.postMessage({ type: "SMARTSHELF_PRESENCE_STOP" }, window.location.origin);
  }
  if (frame) {
    frame.src = "about:blank";
    frame.dataset.loaded = "";
  }
  const login = document.getElementById("loginScreen");
  const app = document.getElementById("appContainer") || document.getElementById("appScreen");
  if (login) login.style.display = "flex";
  if (app) app.style.display = "none";
}

function showAppScreen() {
  const login = document.getElementById("loginScreen");
  const app = document.getElementById("appContainer") || document.getElementById("appScreen");
  if (login) login.style.display = "none";
  if (app) app.style.display = "flex";
  switchTab("entry_qr");
  loadOverview();
  loadData();
  loadEntryQr();
  initAdminWs();
}

// Update DOM texts based on current language
function updateLocalization() {
  const dict = i18nData[currentLang];
  document.documentElement.lang = currentLang;
  document.documentElement.dir = currentLang === "fa" ? "rtl" : "ltr";

  const btn = document.getElementById("langToggleBtn");
  if (btn) btn.textContent = currentLang === "fa" ? "English" : "فارسی";

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (dict[key]) {
      el.textContent = dict[key];
    }
  });

  const searchInput = document.getElementById("productSearchInput");
  if (searchInput && dict.search_placeholder) {
    searchInput.placeholder = dict.search_placeholder;
  }
}

// Check if currently authenticated
async function checkAuth() {
  if (!adminToken) {
    showLoginScreen();
    return;
  }
  try {
    const res = await authFetch("/api/admin/auth/check");
    if (res.ok) {
      showAppScreen();
    } else {
      adminToken = "";
      sessionStorage.removeItem("smartshelf_admin_token");
      showLoginScreen();
    }
  } catch (err) {
    adminToken = "";
    sessionStorage.removeItem("smartshelf_admin_token");
    showLoginScreen();
    const errEl = document.getElementById("loginError");
    if (errEl) {
      errEl.textContent = "ارتباط با بک‌اند برقرار نشد؛ آدرس سرور را در تنظیمات بررسی کنید.";
      errEl.style.display = "block";
    }
  }
}

// Handle PIN Login
document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const rawPin = document.getElementById("pinInput").value.trim();
  const pin = window.SmartShelfFormat ? window.SmartShelfFormat.normalizeDigits(rawPin) : rawPin;
  const errEl = document.getElementById("loginError");
  errEl.style.display = "none";
  try {
    const loginUrl = window.SmartShelfApi ? window.SmartShelfApi.apiUrl("/api/admin/login") : "/api/admin/login";
    const res = await fetch(loginUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin })
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      errEl.textContent = data.detail || (res.status === 429
        ? "تعداد تلاش‌ها بیش از حد مجاز است؛ بعداً دوباره تلاش کنید."
        : "رمز عبور نادرست است یا سرور درخواست را نپذیرفت.");
      errEl.style.display = "block";
      return;
    }
    const data = await res.json();
    if (!data.token) throw new Error("توکن ورود از سرور دریافت نشد.");
    adminToken = data.token;
    sessionStorage.setItem("smartshelf_admin_token", adminToken);
    localStorage.removeItem("smartshelf_admin_token");
    showAppScreen();
  } catch (err) {
    errEl.textContent = window.SmartShelfApi && !window.SmartShelfApi.getApiBase()
      ? "آدرس بک‌اند ثبت نشده است. دکمهٔ تنظیم آدرس سرور را بزنید و آدرس HTTPS بک‌اند را وارد کنید."
      : "ورود انجام نشد. از تنظیم آدرس سرور، اتصال به بک‌اند را بررسی کنید.";
    errEl.style.display = "block";
  }
});

// Logout handler
document.getElementById("logoutBtn").addEventListener("click", async () => {
  try {
    await authFetch("/api/admin/logout", { method: "POST" });
  } catch (e) {}
  adminToken = "";
  stopCameraMonitor();
  sessionStorage.removeItem("smartshelf_admin_token");
  localStorage.removeItem("smartshelf_admin_token");
  showLoginScreen();
});

// Theme Toggle Button handler
document.getElementById("themeToggleBtn")?.addEventListener("click", () => {
  if (window.SmartShelfUI) {
    window.SmartShelfUI.toggleTheme();
  }
});

// Server Config Button handler
for (const id of ["loginServerBtn", "configServerBtn"]) {
  document.getElementById(id)?.addEventListener("click", () => window.SmartShelfApi.showServerConfigModal());
}

// Language Toggle
document.getElementById("langToggleBtn").addEventListener("click", () => {
  currentLang = currentLang === "fa" ? "en" : "fa";
  localStorage.setItem("smartshelf_lang", currentLang);
  updateLocalization();
  renderProducts();
  renderSlots();
  renderSessions();
});

// Secure bridge to the integrated two-reference calibration page.
function loadPresenceFrame() {
  const frame = document.getElementById("presenceAdminFrame");
  if (!frame) return;
  const sendAuth = () => {
    if (frame.contentWindow && adminToken) {
      frame.contentWindow.postMessage({ type: "SMARTSHELF_ADMIN_AUTH", token: adminToken }, window.location.origin);
    }
  };
  if (!frame.dataset.loaded) {
    frame.onload = sendAuth;
    frame.src = "/presence?embed=admin";
    frame.dataset.loaded = "1";
  } else {
    sendAuth();
  }
}
function stopPresenceFrame() {
  const frame = document.getElementById("presenceAdminFrame");
  if (frame?.contentWindow) {
    frame.contentWindow.postMessage({ type: "SMARTSHELF_PRESENCE_STOP" }, window.location.origin);
  }
}
window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  const frame = document.getElementById("presenceAdminFrame");
  if (!frame || event.source !== frame.contentWindow) return;
  const data = event.data || {};
  if (data.type === "SMARTSHELF_PRESENCE_HEIGHT") {
    frame.style.height = Math.max(900, Math.min(2600, Number(data.height) || 1250)) + "px";
  }
  if (data.type === "SMARTSHELF_AUTH_EXPIRED") {
    adminToken = "";
    sessionStorage.removeItem("smartshelf_admin_token");
    showLoginScreen();
  }
});

// Tab Navigation
function switchTab(target) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));

  const targetBtn = document.querySelector(`.tab-btn[data-tab="${target}"]`);
  const panel = document.getElementById(`panel_${target}`);

  if (targetBtn) targetBtn.classList.add("active");
  if (panel) panel.classList.add("active");

  if (target === "overview") loadOverview();
  if (target === "products") loadData();
  if (target === "recognition") {
    loadRecognitionLab();
    loadPresenceFrame();
  } else {
    stopPresenceFrame();
  }
  if (target === "entry_qr") loadEntryQr();
  if (target === "sessions") loadSessions();
  if (target === "invoices") loadInvoices();
  if (target === "events") loadEvents();
  if (target === "devices") {
    loadDevices();
    startCameraMonitor();
    const card = document.getElementById("pairingCodeCard");
    const codeEl = document.getElementById("pairingCodeDisplay");
    const existingCode = localStorage.getItem("smartshelf_pairing_code");
    if (!existingCode) {
      generateCameraPairingCode();
    } else {
      if (card) card.style.display = "block";
      if (codeEl) codeEl.textContent = existingCode;
      const directInput = document.getElementById("cameraDirectUrlInput");
      if (directInput) directInput.value = `${window.location.origin}/camera/?code=${existingCode}`;
      const openLink = document.getElementById("openCameraUrlLink");
      if (openLink) openLink.href = `${window.location.origin}/camera/?code=${existingCode}`;
    }
  } else {
    stopCameraMonitor();
  }
  if (target !== "recognition") {
    stopRecCamera();
  }
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.getAttribute("data-tab");
    switchTab(target);
  });
});

// ---------------------------------------------------------------------------
// QR Code Generation & Entry Tab Logic (Phase 3)
// ---------------------------------------------------------------------------

let qrCodeInstance = null;
let qrCountdownInterval = null;
let currentRemainingSeconds = 30;

async function loadEntryQr() {
  clearInterval(qrCountdownInterval);
  const occupiedBanner = document.getElementById("store-occupied-banner");
  const qrWrapper = document.getElementById("qr-active-container");
  const qrcodeDisplay = document.getElementById("qrcode-display");
  const countdownEl = document.getElementById("qr-countdown");
  const entryUrlInput = document.getElementById("entryUrlInput");
  const openLink = document.getElementById("openEntryUrlLink");

  try {
    const res = await authFetch("/api/admin/token", { method: "POST" });
    if (!res.ok) {
      if (res.status === 401) return;
      if (res.status === 403) {
        if(qrWrapper)qrWrapper.style.display="none";
        if(occupiedBanner)occupiedBanner.style.display="none";
        const setup=document.getElementById("entrySetupNotice");if(setup)setup.style.display="block";
        return;
      }
      showToast("خطا در دریافت کد ورود", "danger");
      return;
    }
    const data = await res.json();
    const setup=document.getElementById("entrySetupNotice");if(setup)setup.style.display="none";

    if (data.active_session) {
      // Store is occupied!
      if (occupiedBanner) occupiedBanner.style.display = "block";
      if (qrWrapper) qrWrapper.style.display = "none";
      fetchActiveSessionSummary();
      return;
    }

    const shortCode=document.getElementById("entryShortCode");
    if(shortCode)shortCode.textContent=data.token;

    // Store is free, display QR
    if (occupiedBanner) occupiedBanner.style.display = "none";
    if (qrWrapper) qrWrapper.style.display = "flex";

    const localEntryUrl=new URL("/enter/",window.location.origin);
    localEntryUrl.searchParams.set("token",data.token);
    if (entryUrlInput) entryUrlInput.value = localEntryUrl.href;
    if (openLink) openLink.href = localEntryUrl.href;

    // Render QR Code using local qrcode.js
    if (qrcodeDisplay) {
      qrcodeDisplay.innerHTML = "";
      if (typeof QRCode !== "undefined") {
        qrCodeInstance = new QRCode(qrcodeDisplay, {
          text: localEntryUrl.href,
          width: 220,
          height: 220,
          colorDark: "#0B132B",
          colorLight: "#FFFFFF",
          correctLevel: QRCode.CorrectLevel.M
        });
      } else {
        qrcodeDisplay.textContent = "QRCode library loading...";
      }
    }

    currentRemainingSeconds = data.expires_in || 30;
    if (countdownEl) countdownEl.textContent = currentRemainingSeconds;

    qrCountdownInterval = setInterval(() => {
      currentRemainingSeconds -= 1;
      if (countdownEl) countdownEl.textContent = currentRemainingSeconds;
      if (currentRemainingSeconds <= 0) {
        clearInterval(qrCountdownInterval);
        const activeTab = document.querySelector(".tab-btn.active")?.dataset.tab;
        if (activeTab === "entry_qr") {
          loadEntryQr();
        }
      }
    }, 1000);

  } catch (err) {
    console.error("Failed to load QR code:", err);
  }
}

async function fetchActiveSessionSummary() {
  try {
    const res = await authFetch("/api/admin/sessions");
    if (!res.ok) return;
    const sessions = await res.json();
    const active = sessions.find((s) => s.status === "ACTIVE");
    if (active) {
      const idEl = document.getElementById("occupied-session-id");
      const timeEl = document.getElementById("occupied-session-time");
      if (idEl) idEl.textContent = `#${active.id}`;
      if (timeEl) timeEl.textContent = formatDateTime(active.entered_at);
    }
  } catch (e) {}
}

document.getElementById("refreshQrBtn")?.addEventListener("click", () => {
  loadEntryQr();
});

document.getElementById("viewActiveSessionBtn")?.addEventListener("click", () => {
  switchTab("sessions");
});

document.getElementById("copyEntryUrlBtn")?.addEventListener("click", () => {
  const input = document.getElementById("entryUrlInput");
  if (!input) return;
  input.select();
  navigator.clipboard.writeText(input.value);
  showToast(i18nData[currentLang].copied_to_clipboard || "کپی شد", "success");
});

// ---------------------------------------------------------------------------
// Customer Sessions Management (Phase 3)
// ---------------------------------------------------------------------------

async function loadSessions() {
  const tbody = document.getElementById("sessionsTableBody");
  if (!tbody) return;

  try {
    const res = await authFetch("/api/admin/sessions");
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">خطا در دریافت لیست جلسات</td></tr>`;
      return;
    }
    allSessions = await res.json();
    renderSessions();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">خطای شبکه در دریافت جلسات</td></tr>`;
  }
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return currentLang === "fa" ? "۰ ثانیه" : "0s";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) {
    return currentLang === "fa" ? `${secs} ثانیه` : `${secs}s`;
  }
  return currentLang === "fa" ? `${mins} دقیقه و ${secs} ثانیه` : `${mins}m ${secs}s`;
}

function formatDateTime(isoString) {
  if (!isoString) return "-";
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString(currentLang === "fa" ? "fa-IR" : "en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  } catch (e) {
    return isoString;
  }
}

function renderSessions() {
  const tbody = document.getElementById("sessionsTableBody");
  if (!tbody) return;

  const dict = i18nData[currentLang];

  if (allSessions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">${dict.no_sessions || "جلسه‌ای یافت نشد"}</td></tr>`;
    return;
  }

  tbody.innerHTML = allSessions
    .map((s) => {
      const isActive = s.status === "ACTIVE";
      const statusBadgeClass = isActive ? "active-session" : "closed-session";
      const statusText = isActive ? dict.active_status : dict.closed_status;
      const duration = formatDuration(s.duration_seconds);
      const exitReason = s.exit_reason || (isActive ? "-" : "NORMAL");

      const invHtml = s.invoice_id
        ? `<button class="btn btn-outline btn-sm" onclick="openInvoiceDetailsModal(${s.invoice_id})">🧾 #${s.invoice_id} (${formatPrice(s.invoice_total)} ${dict.toman || "تومان"})</button>`
        : `<span class="text-muted">—</span>`;

      const actionHtml = isActive
        ? `<button class="btn btn-danger btn-sm" onclick="forceCloseSession(${s.id})">🛑 ${dict.btn_force_close}</button>`
        : `<span class="text-muted">-</span>`;

      return `
      <tr>
        <td><strong>#${s.id}</strong></td>
        <td><span class="status-badge ${statusBadgeClass}">${statusText}</span></td>
        <td dir="ltr" class="text-center">${formatDateTime(s.entered_at)}</td>
        <td dir="ltr" class="text-center">${s.exited_at ? formatDateTime(s.exited_at) : "-"}</td>
        <td>${duration}</td>
        <td><span class="badge-role">${exitReason}</span></td>
        <td>${invHtml}</td>
        <td>${actionHtml}</td>
      </tr>
    `;
    })
    .join("");
}

async function forceCloseSession(id) {
  const dict = i18nData[currentLang];
  if (!confirm(dict.force_close_confirm)) return;

  try {
    const res = await authFetch(`/api/admin/sessions/${id}/close`, { method: "POST" });
    if (res.ok) {
      showToast(dict.force_close_success, "success");
      await loadSessions();
      loadEntryQr();
    } else {
      const err = await res.json();
      showToast(err.detail || "Error closing session", "danger");
    }
  } catch (e) {
    showToast("Network error closing session", "danger");
  }
}

window.forceCloseSession = forceCloseSession;

document.getElementById("refreshSessionsBtn")?.addEventListener("click", () => {
  loadSessions();
});

// ---------------------------------------------------------------------------
// Admin WebSocket Connection (Phase 3)
// ---------------------------------------------------------------------------

let adminWs = null;
let lastShopEnabled = null;

function initAdminWs() {
  if (adminWs && (adminWs.readyState === WebSocket.OPEN || adminWs.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const wsUrl = window.SmartShelfApi ? window.SmartShelfApi.wsUrl("/ws/admin") : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/admin`;

  try {
    adminWs = new WebSocket(wsUrl);

    adminWs.onopen = () => {
      console.log("Admin WebSocket connected. Sending AUTH token...");
      if (adminToken) {
        adminWs.send(JSON.stringify({ type: "AUTH", token: adminToken }));
      }
    };

    adminWs.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "AUTH_OK") {
          console.log("Admin WebSocket authenticated successfully.");
          loadData(); loadSessions(); loadOverview(); loadInvoices();
          return;
        }

        if (msg.type === "SHOP_STATE") {
          const product = allProducts.find(p => p.id === msg.shop.product_id);
          if (product && (product.stock_quantity !== msg.shop.stock_quantity || product.unit_price !== msg.shop.unit_price)) {
            product.stock_quantity = msg.shop.stock_quantity; product.unit_price = msg.shop.unit_price;
            if (msg.shop.enabled) product.is_active = true;
            renderProducts();
          }
          if (lastShopEnabled !== msg.shop.enabled) { lastShopEnabled = msg.shop.enabled; loadEntryQr(); }
        } else if (msg.type === "CUSTOMER_ENTERED") {
          const text = i18nData[currentLang].customer_entered_toast.replace("{id}", msg.session_id);
          showToast(text, "info");
          loadEntryQr();
          loadSessions();
          loadOverview();
        } else if (msg.type === "SESSION_CLOSED") {
          const text = i18nData[currentLang].session_closed_toast
            .replace("{id}", msg.session_id)
            .replace("{reason}", msg.exit_reason || "");
          showToast(text, "info");
          loadEntryQr();
          loadSessions();
          loadInvoices();
          loadOverview();
        } else if (msg.type === "DEVICE_STATUS") {
          const isOnline = msg.is_online;
          const toastKey = isOnline ? "device_online_toast" : "device_offline_toast";
          const text = (i18nData[currentLang][toastKey] || (isOnline ? "دستگاه آنلاین شد" : "دستگاه آفلاین شد")).replace("{id}", msg.device_id);
          showToast(text, isOnline ? "info" : "warning");
          loadDevices();
          updateCameraFeed();
          loadOverview();
        } else if (msg.type === "ZONES_STATUS") {
          if (Array.isArray(msg.zones)) {
            msg.zones.forEach((z) => {
              const existing = allZones.find((item) => item.id === z.id);
              if (existing) {
                existing.state = z.state;
                existing.confidence = z.confidence;
              }
            });
            renderSlots();
            renderOverviewSlots(msg.zones);
          }
        } else if (msg.type === "EVENT_CREATED") {
          if (msg.event) {
            allEvents.unshift(msg.event);
            renderEvents();
          }
        } else if (msg.type === "CART_UPDATED") {
          loadSessions();
          loadOverview();
        } else if (msg.type === "CAMERA_WARNING") {
          showToast("⚠️ " + (msg.message || "دوربین بیش از ۱۰ ثانیه قطع است"), "warning");
          loadOverview();
        }
      } catch (e) {}
    };

    adminWs.onclose = () => {
      if (adminToken) {
        setTimeout(initAdminWs, 5000);
      }
    };
    adminWs.onerror = () => {
      // Quietly handle on Vercel
    };
  } catch (e) {
    // Quietly handle on Vercel
  }
}

// Storage listener for refreshing the authenticated backend view across tabs
window.addEventListener("storage", (e) => {
  if (e.key === "smartshelf_invoices" || e.key === "smartshelf_sessions" || e.key === "smartshelf_products") {
    loadSessions();
    loadInvoices();
    loadOverview();
  }
});

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Devices & Camera Feed Telemetry (Phase 4 & Cross-Device Cloud Sync)
// ---------------------------------------------------------------------------

let allDevices = [];
let cameraPollInterval = null;
let tabletPairedOnline = false;
let tabletLastHeartbeat = 0;
let mainPairEventSource = null;
let mainFrameEventSource = null;
let tabletPairEventSource = null;
let tabletFrameEventSource = null;
let tabletPollInterval = null;
let activePairingCode = "";
let totalFramesReceived = 0;
let adminPeer = null;
window.activeCustomerPeers = [];

function broadcastCartItemEvent() {
  // Manual/localStorage/third-party relay events are disabled.
  // All cart changes must originate from authenticated backend vision transitions.
  return;
}
window.broadcastCartItemEvent = broadcastCartItemEvent;


let adminVisionEngine = null;

function initAdminVisionEngine() {
  // Product/shelf decisions are made only by the authenticated backend pipeline.
  return;
}

function updateAiVisionOverlay(type, prod) {
  const badge = document.getElementById("shelfOccupancyBadge");
  const notice = document.getElementById("shelfSyncNotice");
  const canvas = document.getElementById("aiVisionCanvas");

  if (type === "ITEM_PICKED") {
    if (badge) {
      badge.className = "status-badge status-inactive";
      badge.textContent = "قفسه ۱: خالی";
    }
    if (notice) {
      notice.innerHTML = `🛒 <strong style="color: var(--primary);">«${prod.name}»</strong> از قفسه برداشته شد و به سبد مشتری رفت.`;
    }
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  } else {
    if (badge) {
      badge.className = "status-badge status-active";
      badge.textContent = "قفسه ۱: پر";
    }
    if (notice) {
      notice.innerHTML = `↩️ <strong style="color: var(--text-primary);">«${prod.name}»</strong> در قفسه شناسایی شد.`;
    }
  }
}
window.updateAiVisionOverlay = updateAiVisionOverlay;

function initAdminWebRTC() { startCameraMonitor(); }

function startListeningForTabletPair() { return; }
function handleTabletCloudMessage() { return; }
function updateAdminCameraFrame() { return; }

async function loadDevices() {
  const tbody = document.getElementById("devicesTableBody");
  if (!tbody) return;
  try {
    const res = await authFetch("/api/admin/devices");
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">خطا در دریافت لیست دستگاه‌ها (HTTP ${res.status})</td></tr>`;
      return;
    }
    allDevices = await res.json();
    renderDevices();
  } catch (err) {
    allDevices = [];
    tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">بک‌اند در دسترس نیست؛ وضعیت دستگاه‌ها قابل تأیید نیست.</td></tr>`;
  }
}

function renderDevices() {
  const tbody = document.getElementById("devicesTableBody");
  if (!tbody) return;

  if (allDevices.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted" style="padding: 2rem;">هیچ دستگاهی ثبت نشده است</td></tr>`;
    return;
  }

  tbody.innerHTML = allDevices
    .map((d) => {
      const isOnline = d.is_online;
      const statusClass = isOnline ? "status-active" : "status-inactive";
      const statusText = isOnline
        ? currentLang === "fa"
          ? "آنلاین"
          : "Online"
        : currentLang === "fa"
        ? "آفلاین"
        : "Offline";

      const roleStr = d.role ? String(d.role).toLowerCase() : "camera";
      const roleKey = `role_${roleStr}`;
      const roleLabel = (i18nData[currentLang] && i18nData[currentLang][roleKey]) || d.name || d.role || (currentLang === "fa" ? "حسگر دوربین" : "Camera");

      return `
      <tr>
        <td><code>${d.device_id || "tab_sensor"}</code></td>
        <td><span class="badge-role">${roleLabel}</span></td>
        <td><span class="status-badge ${statusClass}">${statusText}</span></td>
        <td dir="ltr" class="text-center">${formatDateTime(d.last_seen || new Date())}</td>
      </tr>
    `;
    })
    .join("");
}

let adminRtcViewer = null;
function startCameraMonitor() {
  stopCameraMonitor();
  const video=document.getElementById('cameraStreamVideo');
  if(!video||!window.SmartShelfRTC)return;
  adminRtcViewer=new window.SmartShelfRTC.Viewer({video,getToken:()=>adminToken,
    onState:(state,text)=>{
      const live=state==='live'||state==='play';
      video.style.display=live?'block':'none';
      const img=document.getElementById('cameraStreamImg');if(img)img.style.display='none';
      const overlay=document.getElementById('noStreamOverlay');if(overlay)overlay.style.display=live?'none':'flex';
      const hint=document.getElementById('rtcMonitorHint');if(hint)hint.textContent=text;
      const detail=document.getElementById('rtcOverlayHint');if(detail)detail.textContent=text;
      const badge=document.getElementById('camFeedOnlineBadge');if(badge){badge.className='status-badge '+(live?'status-active':'status-inactive');badge.textContent=state==='live'?'WebRTC · زنده':state==='connecting'?'در حال اتصال':'ویدیو متوقف';}
    },
    onStats:stats=>{
      document.getElementById('camTelemetryFps').textContent=stats.fps.toFixed(1)+' FPS';
      document.getElementById('camTelemetryRes').textContent=stats.width?stats.width+'×'+stats.height:'--';
      document.getElementById('camTelemetryFrames').textContent=stats.frames.toLocaleString();
    }});
  adminRtcViewer.start();
}
function stopCameraMonitor() {adminRtcViewer?.stop();adminRtcViewer=null;}
function updateCameraFeed() {
  // Device telemetry must never replace WebRTC video with a JPEG snapshot.
  if(adminRtcViewer?.active)return;
}
window.addEventListener('pagehide',stopCameraMonitor);

document.getElementById("refreshDevicesBtn")?.addEventListener("click", () => {
  loadDevices();
});

document.getElementById("refreshCameraFeedBtn")?.addEventListener("click", () => {
  startCameraMonitor();
});

// ---------------------------------------------------------------------------
// Load Products and Zones from Backend
// ---------------------------------------------------------------------------

async function loadData() {
  await Promise.all([fetchProducts(), fetchZones()]);
}

async function fetchProducts() {
  try {
    const res = await authFetch("/api/admin/products");
    if (res.ok) {
      allProducts = await res.json();
      renderProducts();
      renderSlotDropdowns();
    }
  } catch (err) {
    console.error("Failed to load products:", err);
  }
}

async function fetchZones() {
  try {
    const res = await authFetch("/api/admin/zones");
    if (res.ok) {
      allZones = await res.json();
      renderSlots();
    }
  } catch (err) {
    console.error("Failed to load zones:", err);
  }
}

// Render 3 shelf slot cards (Phase 8: Enhanced with AI Recognition & Manual Correction)
function renderSlots() {
  const container = document.getElementById("slotsGrid") || document.getElementById("shelfSlotsContainer");
  if (!container) return;

  const dict = i18nData[currentLang];

  container.innerHTML = allZones
    .map((zone) => {
      const state = zone.state || "PRESENT";
      let stateBadgeClass = "state-empty";
      let stateLabel = dict.state_absent || "خالی";

      if (state === "PRESENT" || state === "FULL") {
        stateBadgeClass = "state-full";
        stateLabel = dict.state_present || "موجود (پر)";
      } else if (state === "TRANSITION") {
        stateBadgeClass = "status-badge status-warning";
        stateLabel = dict.state_transition || "در حال تغییر...";
      }

      const confText = zone.confidence ? ` (${Math.round(zone.confidence * 100)}%)` : "";
      const stateBadge = `<span class="slot-badge ${stateBadgeClass}">${stateLabel}${confText}</span>`;

      // Recognition metadata
      const recStatus = zone.recognition_status || "UNKNOWN";
      const recScore = zone.recognition_score ? Math.round(zone.recognition_score * 100) : 0;
      let recProdName = "تشخیص‌داده‌نشده";

      if (zone.recognized_product_id) {
        const found = allProducts.find((p) => p.id === zone.recognized_product_id);
        if (found) {
          recProdName = `${found.name} (${found.sku})`;
        } else if (zone.recognized_product_name) {
          recProdName = zone.recognized_product_name;
        }
      }

      const isMismatch = (
        zone.state === "PRESENT" &&
        zone.product_id &&
        zone.recognized_product_id &&
        zone.product_id !== zone.recognized_product_id &&
        recStatus === "RECOGNIZED"
      );

      const isUncertain = (
        zone.state === "PRESENT" &&
        (recStatus === "UNKNOWN" || recStatus === "NEEDS_REVIEW")
      );

      let alertBadge = "";
      if (isMismatch) {
        alertBadge = `<div class="badge badge-danger" style="margin-block-start: 6px; width: 100%; text-align: center;">⚠ عدم تطابق با قفسه (MISMATCH)</div>`;
      } else if (isUncertain) {
        alertBadge = `<div class="badge badge-warning" style="margin-block-start: 6px; width: 100%; text-align: center;">⚠ نیازمند بررسی دستی (UNCERTAIN)</div>`;
      }

      return `
      <div class="slot-card" data-zone-id="${zone.id}">
        <div class="slot-card-header">
          <span class="slot-number">${zone.name}</span>
          ${stateBadge}
        </div>

        <div class="slot-product-select" style="margin-block-start: var(--space-2);">
          <label class="form-label" style="font-size: var(--font-xs);">${dict.th_name} تعیین‌شده:</label>
          <select class="form-control slot-select" onchange="assignSlotProduct(${zone.id}, this.value)">
            <option value="">-- ${dict.unassigned} --</option>
            ${allProducts
              .map(
                (p) =>
                  `<option value="${p.id}" ${p.id === zone.product_id ? "selected" : ""}>
                    ${p.name} (${p.sku})
                  </option>`
              )
              .join("")}
          </select>
        </div>

        <!-- Phase 8 Recognition Status & Confidence Meter -->
        <div style="background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: var(--space-2); margin-block-start: var(--space-2);">
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: var(--font-xs);">
            <span style="color: var(--text-muted);">کالای شناسایی‌شده:</span>
            <strong style="color: ${recStatus === 'RECOGNIZED' ? 'var(--color-success, #22c55e)' : 'var(--text-muted)'};">${recProdName}</strong>
          </div>

          <div style="margin-block-start: 6px;">
            <div style="display: flex; justify-content: space-between; font-size: var(--font-xs); margin-block-end: 2px;">
              <span style="color: var(--text-muted);">شباهت کسینوسی:</span>
              <strong style="font-size: var(--font-xs);">${recScore}%</strong>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
              <div style="height: 100%; width: ${Math.min(100, recScore)}%; background: ${recStatus === 'RECOGNIZED' ? 'var(--color-success, #22c55e)' : 'var(--color-warning, #f59e0b)'}; transition: width 0.3s ease;"></div>
            </div>
          </div>

          ${alertBadge}

          <div style="margin-block-start: 8px; display: flex; justify-content: flex-end;">
            <button class="btn btn-outline btn-xs" type="button" onclick="openManualCorrectionModal(${zone.id})">
              ✏️ تصحیح دستی
            </button>
          </div>
        </div>
      </div>
    `;
    })
    .join("");
}

function renderSlotDropdowns() {
  renderSlots();
}

// Manual Correction Modal (Phase 8)
function openManualCorrectionModal(zoneId) {
  const zone = allZones.find((z) => z.id === zoneId);
  if (!zone) return;

  const modal = document.getElementById("manualCorrectionModal");
  const zoneInput = document.getElementById("manualCorrectionZoneId");
  const select = document.getElementById("manualCorrectionProductSelect");
  const title = document.getElementById("manualCorrectionTitle");

  if (title) title.textContent = `🏷️ تصحیح دستی شناسایی ${zone.name}`;
  if (zoneInput) zoneInput.value = zoneId;

  if (select) {
    select.innerHTML = allProducts
      .map(
        (p) =>
          `<option value="${p.id}" ${p.id === (zone.recognized_product_id || zone.product_id) ? "selected" : ""}>
            ${p.name} (${p.sku}) - ${SmartShelfFormat ? SmartShelfFormat.formatToman(p.unit_price) : p.unit_price}
          </option>`
      )
      .join("");
  }

  if (modal) modal.classList.add("active");
}
window.openManualCorrectionModal = openManualCorrectionModal;

function closeManualCorrectionModal() {
  const modal = document.getElementById("manualCorrectionModal");
  if (modal) modal.classList.remove("active");
}
window.closeManualCorrectionModal = closeManualCorrectionModal;

async function submitManualCorrection() {
  const zoneId = parseInt(document.getElementById("manualCorrectionZoneId").value);
  const select = document.getElementById("manualCorrectionProductSelect");
  const productId = parseInt(select.value);

  if (!zoneId || !productId) return;

  try {
    const res = await authFetch(`/api/admin/zones/${zoneId}/manual-correction`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId }),
    });

    if (res.ok) {
      showToast("تصحیح دستی با موفقیت اعمال و فریم به تصاویر مرجع افزوده شد.", "success");
      closeManualCorrectionModal();
      await loadData();
    } else {
      const err = await res.json();
      showToast(err.detail || "خطا در ثبت تصحیح دستی", "danger");
    }
  } catch (err) {
    showToast("خطای ارتباط با سرور", "danger");
  }
}
window.submitManualCorrection = submitManualCorrection;

// Handle slot assignment
async function assignSlotProduct(zoneId, productId) {
  const prodId = productId ? parseInt(productId) : null;
  try {
    const res = await authFetch(`/api/admin/zones/${zoneId}/assign`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: prodId }),
    });

    if (res.ok) {
      showToast(i18nData[currentLang].assign_success, "success");
      await loadData();
    } else {
      const err = await res.json();
      showToast(err.detail || "Error assigning slot", "danger");
    }
  } catch (err) {
    showToast("Network error assigning slot", "danger");
  }
}
window.assignSlotProduct = assignSlotProduct;

// ---------------------------------------------------------------------------
// Product Catalog & Multi-Step Wizard (Phase 6)
// ---------------------------------------------------------------------------

let currentProductView = "table"; // "table" or "cards"
let currentProductCategoryFilter = "";
let currentModalStep = 1;
let currentEditingProduct = null;
let currentProductImages = []; // [{id, file_path, is_primary, width, height}]
let pendingImageFiles = []; // Files buffered before product creation
let barcodeScannerStream = null;
let barcodeDetectorInstance = null;
let barcodeScanLoopActive = false;
let tabletCameraStream = null;

// Category filter population
function updateProductCategories() {
  const catSelect = document.getElementById("productCategoryFilter");
  if (!catSelect) return;
  const categories = Array.from(new Set(allProducts.map((p) => p.category).filter(Boolean))).sort();
  const currentVal = catSelect.value;
  catSelect.innerHTML = `<option value="">همه دسته‌بندی‌ها</option>` +
    categories.map(c => `<option value="${c}">${c}</option>`).join("");
  catSelect.value = currentVal;
}

// Render products catalog (Table and Cards)
function renderProducts() {
  updateProductCategories();
  const tbody = document.getElementById("productsTableBody");
  const cardsGrid = document.getElementById("productsCardsView");
  const tableView = document.getElementById("productsTableView");
  if (!tbody || !cardsGrid) return;

  const query = (document.getElementById("productSearchInput")?.value || "").toLowerCase().trim();
  const categoryFilter = document.getElementById("productCategoryFilter")?.value || "";
  const dict = i18nData[currentLang];

  const filtered = allProducts.filter((p) => {
    const matchesQuery = !query ||
      (p.name && p.name.toLowerCase().includes(query)) ||
      (p.sku && p.sku.toLowerCase().includes(query)) ||
      (p.brand && p.brand.toLowerCase().includes(query)) ||
      (p.gtin && p.gtin.toLowerCase().includes(query)) ||
      (p.category && p.category.toLowerCase().includes(query));
    const matchesCategory = !categoryFilter || p.category === categoryFilter;
    return matchesQuery && matchesCategory;
  });

  // Toggle Table / Cards visibility
  if (currentProductView === "cards") {
    if (tableView) tableView.style.display = "none";
    cardsGrid.style.display = "grid";
  } else {
    if (tableView) tableView.style.display = "block";
    cardsGrid.style.display = "none";
  }

  // Empty state
  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding: 2rem;">موردی یافت نشد</td></tr>`;
    cardsGrid.innerHTML = `<div class="text-center text-muted" style="grid-column: 1 / -1; padding: 2.5rem; border: 1px dashed var(--border-default); border-radius: var(--radius-lg);">موردی با مشخصات جست‌وجو شده یافت نشد</div>`;
    return;
  }

  // 1. Render Table Rows
  tbody.innerHTML = filtered.map((p) => {
    const primaryImg = (p.images && p.images.find(img => img.is_primary)) || (p.images && p.images[0]);
    const imgSrc = window.SmartShelfApi.mediaUrl((primaryImg && primaryImg.file_path) || p.image_path || "/static/placeholder.png");
    const statusBadge = p.is_active
      ? `<span class="status-badge status-active">${dict.active}</span>`
      : `<span class="status-badge status-inactive">${dict.inactive}</span>`;

    const slotsAssigned = (p.assigned_zones && p.assigned_zones.length > 0)
      ? p.assigned_zones.map((z) => `<span class="badge-role">${z}</span>`).join(" ")
      : `<span class="text-muted" style="font-size: 0.8rem;">${dict.unassigned}</span>`;

    const gtinDisplay = p.gtin
      ? `<code class="sku-code" dir="ltr" title="GTIN-14: ${p.gtin14 || ''}">${p.gtin}</code>`
      : `<span class="text-muted" style="font-size: 0.75rem;">—</span>`;

    const brandDisplay = p.brand ? `<span style="font-size: 0.8rem; color: var(--text-muted); display: block;">برند: ${p.brand}</span>` : "";
    const categoryDisplay = p.category ? `<span class="badge-role" style="font-size: 0.75rem;">${p.category}</span>` : `<span class="text-muted" style="font-size: 0.75rem;">—</span>`;

    return `
      <tr>
        <td>
          <img src="${imgSrc}" class="product-thumb" alt="${p.name}" onerror="this.src='/static/placeholder.png'">
        </td>
        <td>
          <strong>${p.name}</strong>
          ${brandDisplay}
          ${p.description ? `<div style="font-size: 0.78rem; color: var(--text-muted);">${p.description}</div>` : ""}
        </td>
        <td><code class="sku-code">${p.sku}</code></td>
        <td>${gtinDisplay}</td>
        <td>${categoryDisplay}</td>
        <td><strong>${(window.SmartShelfFormat ? window.SmartShelfFormat.formatToman(p.unit_price) : p.unit_price.toLocaleString() + ' تومان')}</strong></td>
        <td>${Number(p.stock_quantity || 0).toLocaleString("fa-IR")}</td>
        <td>${slotsAssigned}</td>
        <td>${statusBadge}</td>
        <td>
          <div style="display: flex; gap: 0.4rem; justify-content: center;">
            <button class="btn btn-secondary btn-sm" onclick="openEditModal(${p.id})" title="ویرایش">✏️</button>
            <button class="btn btn-danger btn-sm" onclick="deleteProduct(${p.id})" title="حذف">🗑️</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  // 2. Render Cards View
  cardsGrid.innerHTML = filtered.map((p) => {
    const primaryImg = (p.images && p.images.find(img => img.is_primary)) || (p.images && p.images[0]);
    const imgSrc = window.SmartShelfApi.mediaUrl((primaryImg && primaryImg.file_path) || p.image_path || "/static/placeholder.png");
    const imgCount = (p.images && p.images.length) || (p.image_path ? 1 : 0);

    const statusBadge = p.is_active
      ? `<span class="status-badge status-active">${dict.active}</span>`
      : `<span class="status-badge status-inactive">${dict.inactive}</span>`;

    const slotsAssigned = (p.assigned_zones && p.assigned_zones.length > 0)
      ? p.assigned_zones.map((z) => `<span class="badge-role">${z}</span>`).join(" ")
      : `<span class="text-muted" style="font-size: 0.8rem;">${dict.unassigned}</span>`;

    return `
      <div class="product-catalog-card">
        <div class="product-card-media">
          <img src="${imgSrc}" alt="${p.name}" onerror="this.src='/static/placeholder.png'">
          <div class="product-card-badge">${statusBadge}</div>
          <div class="product-card-images-count">📷 ${window.SmartShelfFormat ? window.SmartShelfFormat.toPersianDigits(imgCount) : imgCount} تصویر</div>
        </div>
        <div class="product-card-body">
          <h4 class="product-card-title">${p.name}</h4>
          <div class="product-card-meta">
            ${p.brand ? `<span>🏷️ ${p.brand}</span>` : ""}
            ${p.category ? `<span>📁 ${p.category}</span>` : ""}
            <span>SKU: <code class="sku-code">${p.sku}</code></span>
            <span>موجودی: ${Number(p.stock_quantity || 0).toLocaleString("fa-IR")}</span>
            ${p.gtin ? `<span>بارکد: <code class="sku-code" dir="ltr">${p.gtin}</code></span>` : ""}
          </div>
          <div style="font-size: 0.8rem; margin-top: 0.25rem;">
            <span style="color: var(--text-muted);">جایگاه:</span> ${slotsAssigned}
          </div>
          <div class="product-card-price">
            ${window.SmartShelfFormat ? window.SmartShelfFormat.formatToman(p.unit_price) : p.unit_price.toLocaleString() + ' تومان'}
          </div>
        </div>
        <div class="product-card-footer">
          <button class="btn btn-secondary btn-sm" onclick="openEditModal(${p.id})">✏️ ویرایش</button>
          <button class="btn btn-danger btn-sm" onclick="deleteProduct(${p.id})">🗑️ حذف</button>
        </div>
      </div>
    `;
  }).join("");
}

// View toggle listeners
document.getElementById("viewTableBtn")?.addEventListener("click", () => {
  currentProductView = "table";
  document.getElementById("viewTableBtn").className = "btn btn-primary btn-sm";
  document.getElementById("viewCardsBtn").className = "btn btn-secondary btn-sm";
  renderProducts();
});
document.getElementById("viewCardsBtn")?.addEventListener("click", () => {
  currentProductView = "cards";
  document.getElementById("viewTableBtn").className = "btn btn-secondary btn-sm";
  document.getElementById("viewCardsBtn").className = "btn btn-primary btn-sm";
  renderProducts();
});

// Search & category filter listeners
document.getElementById("productSearchInput")?.addEventListener("input", renderProducts);
document.getElementById("productCategoryFilter")?.addEventListener("change", renderProducts);

// Step Navigation Manager
function setModalStep(step) {
  currentModalStep = Math.max(1, Math.min(4, step));

  document.querySelectorAll("#productStepNav .step-indicator-item").forEach((btn) => {
    const s = parseInt(btn.dataset.step);
    btn.classList.toggle("active", s === currentModalStep);
    btn.classList.toggle("completed", s < currentModalStep);
  });

  for (let i = 1; i <= 4; i++) {
    const p = document.getElementById(`stepPanel${i}`);
    if (p) p.classList.toggle("active", i === currentModalStep);
  }

  const prevBtn = document.getElementById("prevStepBtn");
  const nextBtn = document.getElementById("nextStepBtn");
  const saveBtn = document.getElementById("saveProductBtn");

  if (prevBtn) prevBtn.style.visibility = currentModalStep === 1 ? "hidden" : "visible";
  if (nextBtn) nextBtn.style.display = currentModalStep === 4 ? "none" : "inline-flex";
  if (saveBtn) saveBtn.style.display = currentModalStep === 4 ? "inline-flex" : "none";

  if (currentModalStep === 4) {
    updateProductSummaryReview();
  }
}

// Live GS1 GTIN validation UI
function checkGtinValidationLive() {
  const gtinInput = document.getElementById("prodGtin");
  const statusEl = document.getElementById("gtinValidationStatus");
  if (!gtinInput || !statusEl) return true;

  const rawVal = gtinInput.value.trim();
  if (!rawVal) {
    statusEl.innerHTML = "";
    gtinInput.classList.remove("is-invalid");
    return true;
  }

  const res = window.SmartShelfFormat ? window.SmartShelfFormat.validateGtin(rawVal) : { valid: true, clean: rawVal };
  if (!res.valid) {
    statusEl.innerHTML = `<span style="color: var(--color-danger); font-weight: 600;">⚠️ ${res.error}</span>`;
    gtinInput.classList.add("is-invalid");
    return false;
  } else {
    gtinInput.value = res.clean;
    statusEl.innerHTML = `<span style="color: var(--color-success); font-weight: 600;">✓ معتبر (${res.formatName}) — کد ۱۴ رقمی: <code>${res.gtin14}</code></span>`;
    gtinInput.classList.remove("is-invalid");
    return true;
  }
}

document.getElementById("prodGtin")?.addEventListener("input", checkGtinValidationLive);

// Modal open/close logic
const modal = document.getElementById("productModal");

function openAddModal() {
  currentEditingProduct = null;
  currentProductImages = [];
  pendingImageFiles = [];
  document.getElementById("productModalTitle").textContent = i18nData[currentLang].modal_add_title;
  document.getElementById("editProductId").value = "";
  document.getElementById("productForm").reset();
  document.getElementById("prodSku").disabled = false;
  document.getElementById("prodIsActive").checked = true;
  document.getElementById("gtinValidationStatus").innerHTML = "";
  document.getElementById("prodSlotSelect").value = "";
  renderProductImagesGallery();
  setModalStep(1);
  modal.classList.add("active");
}

function openEditModal(productId) {
  const p = allProducts.find((item) => item.id === productId);
  if (!p) return;

  currentEditingProduct = p;
  currentProductImages = (p.images && p.images.slice()) || [];
  if (currentProductImages.length === 0 && p.image_path) {
    currentProductImages.push({
      id: 0,
      file_path: p.image_path,
      is_primary: true
    });
  }
  pendingImageFiles = [];

  document.getElementById("productModalTitle").textContent = i18nData[currentLang].modal_edit_title;
  document.getElementById("editProductId").value = p.id;
  document.getElementById("prodName").value = p.name || "";
  document.getElementById("prodBrand").value = p.brand || "";
  document.getElementById("prodCategory").value = p.category || "";
  document.getElementById("prodSku").value = p.sku || "";
  document.getElementById("prodSku").disabled = true;
  document.getElementById("prodPrice").value = p.unit_price || "";
  document.getElementById("prodDesc").value = p.description || "";
  document.getElementById("prodGtin").value = p.gtin || "";
  document.getElementById("prodIsActive").checked = p.is_active;

  let assignedSlot = "";
  if (p.assigned_zones && p.assigned_zones.length > 0) {
    const match = p.assigned_zones[0].match(/\d+/);
    if (match) assignedSlot = match[0];
  }
  document.getElementById("prodSlotSelect").value = assignedSlot;

  checkGtinValidationLive();
  renderProductImagesGallery();
  setModalStep(1);
  modal.classList.add("active");
}
window.openEditModal = openEditModal;

function closeModal() {
  stopBarcodeScanner();
  stopTabletCamera();
  modal.classList.remove("active");
}

document.getElementById("addProductBtn")?.addEventListener("click", openAddModal);
document.getElementById("closeModalBtn")?.addEventListener("click", closeModal);
document.getElementById("cancelModalBtn")?.addEventListener("click", closeModal);

// Manual Correction Modal Listeners (Phase 8)
document.getElementById("closeManualCorrectionBtn")?.addEventListener("click", closeManualCorrectionModal);
document.getElementById("cancelManualCorrectionBtn")?.addEventListener("click", closeManualCorrectionModal);
document.getElementById("confirmManualCorrectionBtn")?.addEventListener("click", submitManualCorrection);

// Step Indicators click
document.querySelectorAll("#productStepNav .step-indicator-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetStep = parseInt(btn.dataset.step);
    if (targetStep > currentModalStep && !validateCurrentStep()) return;
    setModalStep(targetStep);
  });
});

// Step Validation
function validateCurrentStep() {
  if (currentModalStep === 1) {
    const name = document.getElementById("prodName").value.trim();
    const sku = document.getElementById("prodSku").value.trim();
    const price = parseInt(document.getElementById("prodPrice").value);
    if (!name) {
      showToast("لطفاً نام محصول را وارد کنید", "danger");
      return false;
    }
    if (!sku) {
      showToast("لطفاً کد SKU را وارد کنید", "danger");
      return false;
    }
    if (isNaN(price) || price < 100) {
      showToast("قیمت واحد باید حداقل ۱۰۰ تومان باشد", "danger");
      return false;
    }
    return true;
  } else if (currentModalStep === 2) {
    const gtin = document.getElementById("prodGtin").value.trim();
    if (gtin && !checkGtinValidationLive()) {
      showToast("بارکد وارد شده طبق استاندارد GS1 معتبر نیست", "danger");
      return false;
    }
    return true;
  }
  return true;
}

// Next / Prev buttons
document.getElementById("nextStepBtn")?.addEventListener("click", () => {
  if (!validateCurrentStep()) return;
  setModalStep(currentModalStep + 1);
});

document.getElementById("prevStepBtn")?.addEventListener("click", () => {
  setModalStep(currentModalStep - 1);
});

// Summary review in Step 4
function updateProductSummaryReview() {
  const container = document.getElementById("prodSummaryDetails");
  if (!container) return;
  const name = document.getElementById("prodName").value.trim();
  const brand = document.getElementById("prodBrand").value.trim() || "—";
  const cat = document.getElementById("prodCategory").value.trim() || "—";
  const sku = document.getElementById("prodSku").value.trim();
  const price = parseInt(document.getElementById("prodPrice").value) || 0;
  const gtin = document.getElementById("prodGtin").value.trim() || "—";
  const slot = document.getElementById("prodSlotSelect").value;
  const slotText = slot ? `جایگاه شماره ${slot}` : "بدون جایگاه (انبار)";
  const totalImgs = currentProductImages.length + pendingImageFiles.length;

  container.innerHTML = `
    <div><strong>نام کالا:</strong> ${name}</div>
    <div><strong>برند / گروه:</strong> ${brand} | <strong>دسته‌بندی:</strong> ${cat}</div>
    <div><strong>کد کالا (SKU):</strong> <code>${sku}</code></div>
    <div><strong>بارکد GTIN:</strong> <code>${gtin}</code></div>
    <div><strong>قیمت واحد:</strong> ${window.SmartShelfFormat ? window.SmartShelfFormat.formatToman(price) : price.toLocaleString() + ' تومان'}</div>
    <div><strong>تعداد تصاویر:</strong> ${totalImgs} تصویر (زاویه‌های مختلف)</div>
    <div><strong>جایگاه تخصیص یافته:</strong> <span class="badge-role">${slotText}</span></div>
  `;
}

// ---------------------------------------------------------------------------
// Step 3: Images Management & Tablet Camera Snapshot
// ---------------------------------------------------------------------------

function renderProductImagesGallery() {
  const gallery = document.getElementById("productImagesGallery");
  const badge = document.getElementById("productImagesCountBadge");
  const noImgs = document.getElementById("noImagesNotice");
  if (!gallery) return;

  const totalCount = currentProductImages.length + pendingImageFiles.length;
  if (badge) {
    badge.textContent = `${totalCount} تصویر ثبت شده (پیشنهاد: ۵ تا ۱۰)`;
    badge.className = totalCount >= 5 ? "status-badge status-active" : "status-badge status-inactive";
  }

  if (totalCount === 0) {
    gallery.innerHTML = "";
    if (noImgs) noImgs.style.display = "block";
    return;
  }
  if (noImgs) noImgs.style.display = "none";

  let html = "";

  // 1. Existing Saved Images
  currentProductImages.forEach((img, idx) => {
    const isPrimary = img.is_primary || (idx === 0 && !currentProductImages.some(i => i.is_primary));
    html += `
      <div class="image-card-preview ${isPrimary ? 'is-primary' : ''}">
        <img src="${window.SmartShelfApi.mediaUrl(img.file_path)}" alt="Product Image">
        ${isPrimary ? '<div class="image-card-badge-primary">اصلی ⭐</div>' : ''}
        <div class="image-card-actions">
          ${!isPrimary && img.id ? `<button type="button" title="انتخاب به عنوان تصویر اصلی" onclick="setPrimaryImage(${img.id})">⭐</button>` : ''}
          <button type="button" title="حذف تصویر" onclick="deleteProductImageItem(${img.id}, ${idx})">🗑️</button>
        </div>
      </div>
    `;
  });

  // 2. Pending Files (For new product before saving)
  pendingImageFiles.forEach((fileObj, idx) => {
    html += `
      <div class="image-card-preview ${idx === 0 && currentProductImages.length === 0 ? 'is-primary' : ''}">
        <img src="${fileObj.url}" alt="Pending Image">
        ${idx === 0 && currentProductImages.length === 0 ? '<div class="image-card-badge-primary">اصلی ⭐</div>' : ''}
        <div class="image-card-actions">
          <button type="button" title="حذف تصویر" onclick="removePendingImage(${idx})">🗑️</button>
        </div>
      </div>
    `;
  });

  gallery.innerHTML = html;
}

// Upload multiple images from file input
document.getElementById("prodMultipleImagesInput")?.addEventListener("change", async (e) => {
  const files = Array.from(e.target.files);
  if (!files || files.length === 0) return;

  if (currentEditingProduct && currentEditingProduct.id) {
    // Direct upload to backend
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));

    try {
      const res = await authFetch(`/api/admin/products/${currentEditingProduct.id}/images`, {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const addedImages = await res.json();
        currentProductImages.push(...addedImages);
        renderProductImagesGallery();
        showToast("تصاویر با موفقیت بارگذاری شدند", "success");
      } else {
        const err = await res.json();
        showToast(err.detail || "خطا در آپلود تصاویر", "danger");
      }
    } catch (err) {
      showToast("خطای شبکه در ارسال تصاویر", "danger");
    }
  } else {
    // Stage locally
    files.forEach(file => {
      pendingImageFiles.push({
        file: file,
        url: URL.createObjectURL(file)
      });
    });
    renderProductImagesGallery();
  }
  e.target.value = "";
});

// Set Primary Image
async function setPrimaryImage(imageId) {
  if (!currentEditingProduct || !imageId) return;
  try {
    const res = await authFetch(`/api/admin/products/${currentEditingProduct.id}/images/${imageId}/set-primary`, {
      method: "POST",
    });
    if (res.ok) {
      currentProductImages.forEach(img => {
        img.is_primary = (img.id === imageId);
      });
      renderProductImagesGallery();
      showToast("تصویر اصلی تغییر کرد", "success");
    } else {
      const err = await res.json();
      showToast(err.detail || "خطا در تنظیم تصویر اصلی", "danger");
    }
  } catch (err) {
    showToast("خطای شبکه در تنظیم تصویر اصلی", "danger");
  }
}
window.setPrimaryImage = setPrimaryImage;

// Delete an image
async function deleteProductImageItem(imageId, index) {
  if (currentEditingProduct && imageId) {
    try {
      const res = await authFetch(`/api/admin/products/${currentEditingProduct.id}/images/${imageId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        currentProductImages.splice(index, 1);
        renderProductImagesGallery();
        showToast("تصویر حذف شد", "success");
      } else {
        const err = await res.json();
        showToast(err.detail || "خطا در حذف تصویر", "danger");
      }
    } catch (err) {
      showToast("خطای شبکه در حذف تصویر", "danger");
    }
  } else {
    currentProductImages.splice(index, 1);
    renderProductImagesGallery();
  }
}
window.deleteProductImageItem = deleteProductImageItem;

function removePendingImage(index) {
  pendingImageFiles.splice(index, 1);
  renderProductImagesGallery();
}
window.removePendingImage = removePendingImage;

// Tablet Camera Snapshot
async function openTabletCamera() {
  const box = document.getElementById("tabletCameraBox");
  const video = document.getElementById("tabletCameraVideo");
  if (!box || !video) return;

  try {
    tabletCameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    video.srcObject = tabletCameraStream;
    box.style.display = "block";
  } catch (err) {
    showToast("دسترسی به دوربین تبلت امکان‌پذیر نشد (از فعال بودن HTTPS و مجوز دوربین مطمئن شوید)", "danger");
  }
}

function stopTabletCamera() {
  if (tabletCameraStream) {
    tabletCameraStream.getTracks().forEach(t => t.stop());
    tabletCameraStream = null;
  }
  const box = document.getElementById("tabletCameraBox");
  if (box) box.style.display = "none";
}

document.getElementById("openTabletCameraBtn")?.addEventListener("click", openTabletCamera);
document.getElementById("closeTabletCameraBtn")?.addEventListener("click", stopTabletCamera);

// Snap Photo & upload/stage
document.getElementById("snapPhotoBtn")?.addEventListener("click", () => {
  const video = document.getElementById("tabletCameraVideo");
  const canvas = document.getElementById("tabletCameraCanvas");
  if (!video || !canvas || !tabletCameraStream) return;

  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(async (blob) => {
    if (!blob) return;
    const file = new File([blob], `snap_${Date.now()}.jpg`, { type: "image/jpeg" });

    if (currentEditingProduct && currentEditingProduct.id) {
      const formData = new FormData();
      formData.append("files", file);
      try {
        const res = await authFetch(`/api/admin/products/${currentEditingProduct.id}/images`, {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          const added = await res.json();
          currentProductImages.push(...added);
          renderProductImagesGallery();
          showToast("عکس با موفقیت به محصول افزوده شد", "success");
        } else {
          showToast("خطا در بارگذاری عکس", "danger");
        }
      } catch (err) {
        showToast("خطای شبکه در ارسال عکس", "danger");
      }
    } else {
      pendingImageFiles.push({
        file: file,
        url: URL.createObjectURL(file)
      });
      renderProductImagesGallery();
      showToast("عکس ثبت شد", "success");
    }
  }, "image/jpeg", 0.9);
});

// ---------------------------------------------------------------------------
// Step 2: Barcode Scanner (BarcodeDetector or zxing-cpp backend fallback)
// ---------------------------------------------------------------------------

async function startBarcodeScanner() {
  const box = document.getElementById("barcodeScannerBox");
  const video = document.getElementById("barcodeVideo");
  const feedback = document.getElementById("barcodeScanFeedback");
  if (!box || !video) return;

  feedback.textContent = "در حال راه‌اندازی دوربین...";
  box.style.display = "block";

  try {
    barcodeScannerStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" }
    });
    video.srcObject = barcodeScannerStream;

    // Check if BarcodeDetector is supported in browser
    if ("BarcodeDetector" in window) {
      try {
        barcodeDetectorInstance = new window.BarcodeDetector({
          formats: ["ean_13", "ean_8", "upc_a", "upc_e", "itf", "code_128"]
        });
        feedback.textContent = "اسکنر هوشمند مرورگر فعال است. بارکد را مقابل کادر نگه دارید.";
        barcodeScanLoopActive = true;
        scanBarcodeLoop();
        return;
      } catch (e) {
        console.warn("BarcodeDetector formats unsupported:", e);
      }
    }

    feedback.textContent = "بارکد را در کادر قرار داده و دکمه «ثبت فریم بارکد» را بزنید.";
  } catch (err) {
    feedback.textContent = "دسترسی به دوربین برای اسکن بارکد میسر نشد.";
    showToast("عدم دسترسی به دوربین برای اسکن بارکد", "danger");
  }
}

async function scanBarcodeLoop() {
  if (!barcodeScanLoopActive || !barcodeDetectorInstance) return;
  const video = document.getElementById("barcodeVideo");
  if (video && video.readyState === video.HAVE_ENOUGH_DATA) {
    try {
      const barcodes = await barcodeDetectorInstance.detect(video);
      if (barcodes.length > 0) {
        const rawCode = barcodes[0].rawValue;
        handleDetectedBarcode(rawCode, barcodes[0].format || "BarcodeDetector");
        return;
      }
    } catch (e) {
      console.warn("Barcode detect error:", e);
    }
  }
  if (barcodeScanLoopActive) {
    requestAnimationFrame(scanBarcodeLoop);
  }
}

function stopBarcodeScanner() {
  barcodeScanLoopActive = false;
  barcodeDetectorInstance = null;
  if (barcodeScannerStream) {
    barcodeScannerStream.getTracks().forEach(t => t.stop());
    barcodeScannerStream = null;
  }
  const box = document.getElementById("barcodeScannerBox");
  if (box) box.style.display = "none";
}

document.getElementById("startBarcodeScanBtn")?.addEventListener("click", startBarcodeScanner);
document.getElementById("stopBarcodeScanBtn")?.addEventListener("click", stopBarcodeScanner);

// Capture video frame and send to backend zxing-cpp
document.getElementById("captureBarcodeFrameBtn")?.addEventListener("click", () => {
  const video = document.getElementById("barcodeVideo");
  const feedback = document.getElementById("barcodeScanFeedback");
  if (!video || !barcodeScannerStream) return;

  feedback.textContent = "در حال پردازش فریم با موتور zxing-cpp...";
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(async (blob) => {
    if (!blob) return;
    await sendBarcodeBlobToBackend(blob);
  }, "image/jpeg", 0.92);
});

// Barcode file upload fallback
document.getElementById("barcodeImageUploadInput")?.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  await sendBarcodeBlobToBackend(file);
  e.target.value = "";
});

async function sendBarcodeBlobToBackend(blob) {
  const feedback = document.getElementById("barcodeScanFeedback");
  const formData = new FormData();
  formData.append("file", blob, "barcode.jpg");

  try {
    const res = await authFetch("/api/admin/barcode/scan", {
      method: "POST",
      body: formData,
    });

    if (res.ok) {
      const data = await res.json();
      handleDetectedBarcode(data.gtin, data.format || "zxing-cpp");
    } else {
      const err = await res.json();
      feedback.textContent = `❌ ${err.detail || "بارکدی در تصویر شناسایی نشد"}`;
      showToast(err.detail || "بارکدی در تصویر شناسایی نشد", "warning");
    }
  } catch (err) {
    feedback.textContent = "❌ خطای شبکه در خواندن بارکد";
    showToast("خطای شبکه در خواندن بارکد", "danger");
  }
}

function handleDetectedBarcode(code, source) {
  const gtinInput = document.getElementById("prodGtin");
  if (gtinInput) {
    gtinInput.value = code;
    checkGtinValidationLive();
  }
  showToast(`بارکد شناسایی شد: ${code} (${source})`, "success");
  stopBarcodeScanner();
}

// ---------------------------------------------------------------------------
// Save Product (Create or Update with Staged Images & Slot Assignment)
// ---------------------------------------------------------------------------

document.getElementById("productForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("editProductId").value;
  const isEdit = Boolean(id);

  if (!validateCurrentStep()) return;

  const payload = {
    name: document.getElementById("prodName").value.trim(),
    brand: document.getElementById("prodBrand").value.trim() || null,
    category: document.getElementById("prodCategory").value.trim() || null,
    unit_price: parseInt(document.getElementById("prodPrice").value),
    description: document.getElementById("prodDesc").value.trim() || null,
    gtin: document.getElementById("prodGtin").value.trim() || null,
    is_active: document.getElementById("prodIsActive").checked,
  };

  if (!isEdit) {
    payload.sku = document.getElementById("prodSku").value.trim();
  }

  const url = isEdit ? `/api/admin/products/${id}` : "/api/admin/products";
  const method = isEdit ? "PUT" : "POST";

  try {
    const res = await authFetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const savedProd = await res.json();
      const targetProdId = isEdit ? id : savedProd.id;

      // Upload any pending staged images for newly created product
      if (pendingImageFiles.length > 0) {
        const formData = new FormData();
        pendingImageFiles.forEach(item => formData.append("files", item.file));
        try {
          await authFetch(`/api/admin/products/${targetProdId}/images`, {
            method: "POST",
            body: formData,
          });
        } catch (imgErr) {
          console.warn("Failed to upload pending images:", imgErr);
        }
      }

      // Slot assignment update
      const selectedSlot = document.getElementById("prodSlotSelect").value;
      if (selectedSlot) {
        try {
          await authFetch(`/api/admin/zones/${selectedSlot}/assign`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ product_id: parseInt(targetProdId) }),
          });
        } catch (slotErr) {
          console.warn("Failed to assign slot:", slotErr);
        }
      }

      showToast(i18nData[currentLang].save_success, "success");
      closeModal();
      await loadData();
    } else {
      const err = await res.json();
      showToast(err.detail || "Error saving product", "danger");
    }
  } catch (err) {
    showToast("Network error saving product", "danger");
  }
});

// Delete Product
async function deleteProduct(id) {
  const dict = i18nData[currentLang];
  if (!confirm(dict.delete_confirm)) return;

  try {
    const res = await authFetch(`/api/admin/products/${id}`, {
      method: "DELETE",
    });

    if (res.ok) {
      showToast(dict.delete_success, "success");
      await loadData();
    } else {
      const err = await res.json();
      showToast(err.detail || "Error deleting product", "danger");
    }
  } catch (err) {
    showToast("Network error deleting product", "danger");
  }
}
window.deleteProduct = deleteProduct;

// ---------------------------------------------------------------------------
// Shelf ROI Calibration & Reference Capture (Phase 5)
// ---------------------------------------------------------------------------

let selectedCalibZoneId = 1;
let isCalibModalOpen = false;
let calibFeedInterval = null;
let isDrawingRoi = false;
let drawStartX = 0, drawStartY = 0;
let tempRoi = null;

function openCalibrationModal() {
  const modal = document.getElementById("calibrationModal");
  if (!modal) return;

  isCalibModalOpen = true;
  modal.classList.add("active");
  selectCalibZone(1);

  updateCalibStream();
  if (calibFeedInterval) clearInterval(calibFeedInterval);
  calibFeedInterval = setInterval(updateCalibStream, 750);

  const img = document.getElementById("calibStreamImg");
  img.onload = () => {
    resizeCalibCanvas();
    drawCalibCanvas();
  };
  resizeCalibCanvas();
  drawCalibCanvas();
}

function closeCalibrationModal() {
  const modal = document.getElementById("calibrationModal");
  if (!modal) return;

  isCalibModalOpen = false;
  modal.classList.remove("active");
  if (calibFeedInterval) {
    clearInterval(calibFeedInterval);
    calibFeedInterval = null;
  }
}

function selectCalibZone(zoneId) {
  selectedCalibZoneId = zoneId;
  document.querySelectorAll("#calibZonePills button").forEach((btn) => {
    const zid = parseInt(btn.dataset.zoneId);
    if (zid === zoneId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  const zone = allZones.find((z) => z.id === zoneId);
  if (zone) {
    updateRoiInputs(zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h);
  }
  drawCalibCanvas();
}

function updateRoiInputs(x, y, w, h) {
  const xEl = document.getElementById("calibRoiX");
  const yEl = document.getElementById("calibRoiY");
  const wEl = document.getElementById("calibRoiW");
  const hEl = document.getElementById("calibRoiH");
  if (xEl) xEl.textContent = (x || 0).toFixed(3);
  if (yEl) yEl.textContent = (y || 0).toFixed(3);
  if (wEl) wEl.textContent = (w || 0).toFixed(3);
  if (hEl) hEl.textContent = (h || 0).toFixed(3);
}

function resizeCalibCanvas() {
  const img = document.getElementById("calibStreamImg");
  const canvas = document.getElementById("calibCanvas");
  if (!img || !canvas) return;

  const rect = img.getBoundingClientRect();
  canvas.width = rect.width || 640;
  canvas.height = rect.height || 480;
}

let calibFrameObjectUrl = null;
async function updateCalibStream() {
  if (!isCalibModalOpen) return;
  const img = document.getElementById("calibStreamImg");
  if (!img) return;
  try {
    const res = await authFetch("/api/admin/camera/latest-frame?raw=true");
    if (res.status === 204) return;
    if (!res.ok) return;
    const blob = await res.blob();
    const nextUrl = URL.createObjectURL(blob);
    const oldUrl = calibFrameObjectUrl;
    img.onload = () => { if (oldUrl) URL.revokeObjectURL(oldUrl); };
    img.src = nextUrl;
    calibFrameObjectUrl = nextUrl;
  } catch (err) {
    console.warn("Calibration camera frame unavailable:", err);
  }
}

function drawCalibCanvas() {
  const canvas = document.getElementById("calibCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const W = canvas.width;
  const H = canvas.height;

  allZones.forEach((z) => {
    const isSelected = z.id === selectedCalibZoneId;
    let rx = (z.roi_x !== null && z.roi_x !== undefined) ? z.roi_x : 0.1;
    let ry = (z.roi_y !== null && z.roi_y !== undefined) ? z.roi_y : 0.1;
    let rw = (z.roi_w !== null && z.roi_w !== undefined) ? z.roi_w : 0.2;
    let rh = (z.roi_h !== null && z.roi_h !== undefined) ? z.roi_h : 0.5;

    if (isSelected && tempRoi) {
      rx = tempRoi.x;
      ry = tempRoi.y;
      rw = tempRoi.w;
      rh = tempRoi.h;
    }

    const px = rx * W;
    const py = ry * H;
    const pw = rw * W;
    const ph = rh * H;

    if (isSelected) {
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#00B4D8";
      ctx.fillStyle = "rgba(0, 180, 216, 0.25)";
      ctx.fillRect(px, py, pw, ph);
      ctx.strokeRect(px, py, pw, ph);
    } else {
      ctx.lineWidth = 2;
      ctx.strokeStyle = "rgba(72, 202, 228, 0.6)";
      ctx.strokeRect(px, py, pw, ph);
    }

    ctx.font = "bold 13px system-ui";
    ctx.fillStyle = isSelected ? "#00B4D8" : "#48CAE4";
    ctx.fillText(`${z.name.split('(')[0].trim()}`, px + 4, py + 16);
  });
}

// Canvas Mouse Drag Events for ROI selection
const calibCanvas = document.getElementById("calibCanvas");
if (calibCanvas) {
  calibCanvas.addEventListener("mousedown", (e) => {
    const rect = calibCanvas.getBoundingClientRect();
    isDrawingRoi = true;
    drawStartX = (e.clientX - rect.left) / rect.width;
    drawStartY = (e.clientY - rect.top) / rect.height;
    tempRoi = { x: drawStartX, y: drawStartY, w: 0.01, h: 0.01 };
  });

  calibCanvas.addEventListener("mousemove", (e) => {
    if (!isDrawingRoi) return;
    const rect = calibCanvas.getBoundingClientRect();
    const currX = (e.clientX - rect.left) / rect.width;
    const currY = (e.clientY - rect.top) / rect.height;

    const x = Math.max(0, Math.min(drawStartX, currX));
    const y = Math.max(0, Math.min(drawStartY, currY));
    const w = Math.min(1.0 - x, Math.abs(currX - drawStartX));
    const h = Math.min(1.0 - y, Math.abs(currY - drawStartY));

    tempRoi = { x, y, w, h };
    updateRoiInputs(x, y, w, h);
    drawCalibCanvas();
  });

  const finishDrawing = () => {
    if (!isDrawingRoi) return;
    isDrawingRoi = false;
    if (tempRoi && tempRoi.w > 0.02 && tempRoi.h > 0.02) {
      const zone = allZones.find((z) => z.id === selectedCalibZoneId);
      if (zone) {
        zone.roi_x = tempRoi.x;
        zone.roi_y = tempRoi.y;
        zone.roi_w = tempRoi.w;
        zone.roi_h = tempRoi.h;
      }
    }
    tempRoi = null;
    drawCalibCanvas();
  };

  calibCanvas.addEventListener("mouseup", finishDrawing);
  calibCanvas.addEventListener("mouseleave", finishDrawing);
}

// Save ROI Button
document.getElementById("saveRoiBtn")?.addEventListener("click", async () => {
  const zone = allZones.find((z) => z.id === selectedCalibZoneId);
  if (!zone) return;

  try {
    const res = await authFetch(`/api/admin/zones/${selectedCalibZoneId}/roi`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        roi_x: zone.roi_x,
        roi_y: zone.roi_y,
        roi_w: zone.roi_w,
        roi_h: zone.roi_h,
      }),
    });

    if (res.ok) {
      showToast(i18nData[currentLang].roi_saved_success, "success");
      await fetchZones();
    } else {
      showToast("خطا در ذخیره مختصات ROI", "danger");
    }
  } catch (err) {
    showToast("خطای شبکه در ذخیره ROI", "danger");
  }
});

// Capture Reference Buttons
document.getElementById("captureFullZoneBtn")?.addEventListener("click", async () => {
  try {
    const res = await authFetch(`/api/admin/zones/${selectedCalibZoneId}/capture-reference`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference_type: "FULL" }),
    });

    if (res.ok) {
      showToast("مرجع پر با موفقیت در رم ثبت شد", "success");
      await fetchZones();
    } else {
      const err = await res.json();
      showToast(err.detail || "خطا در ثبت مرجع", "danger");
    }
  } catch (e) {
    showToast("خطا در ارتباط با سرور", "danger");
  }
});

document.getElementById("captureEmptyZoneBtn")?.addEventListener("click", async () => {
  try {
    const res = await authFetch(`/api/admin/zones/${selectedCalibZoneId}/capture-reference`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference_type: "EMPTY" }),
    });

    if (res.ok) {
      showToast("مرجع خالی با موفقیت در رم ثبت شد", "success");
      await fetchZones();
    } else {
      const err = await res.json();
      showToast(err.detail || "خطا در ثبت مرجع", "danger");
    }
  } catch (e) {
    showToast("خطا در ارتباط با سرور", "danger");
  }
});

document.getElementById("captureAllFullBtn")?.addEventListener("click", async () => {
  try {
    const res = await authFetch("/api/admin/zones/capture-all-full", {
      method: "POST",
    });

    if (res.ok) {
      showToast("مرجع پر برای هر ۳ جایگاه ثبت شد", "success");
      await fetchZones();
    } else {
      const err = await res.json();
      showToast(err.detail || "خطا در ثبت مراجع", "danger");
    }
  } catch (e) {
    showToast("خطا در ارتباط با سرور", "danger");
  }
});

// Modal Open / Close Triggers
document.getElementById("openCalibrationBtn")?.addEventListener("click", () => switchTab("recognition"));
document.getElementById("closeCalibModalBtn")?.addEventListener("click", closeCalibrationModal);
document.getElementById("closeCalibBtn")?.addEventListener("click", closeCalibrationModal);

document.querySelectorAll("#calibZonePills button").forEach((btn) => {
  btn.addEventListener("click", () => {
    const zid = parseInt(btn.dataset.zoneId);
    selectCalibZone(zid);
  });
});

// ---------------------------------------------------------------------------
// Events Log (Phase 6)
// ---------------------------------------------------------------------------

let allEvents = [];

async function loadEvents() {
  const tbody = document.getElementById("eventsTableBody");
  if (!tbody) return;

  try {
    const res = await authFetch("/api/admin/events?limit=100");
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">خطا در دریافت رویدادها</td></tr>`;
      return;
    }
    allEvents = await res.json();
    renderEvents();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">خطای شبکه در دریافت رویدادها</td></tr>`;
  }
}

function renderEvents() {
  const tbody = document.getElementById("eventsTableBody");
  const countBadge = document.getElementById("eventsCountBadge");
  if (!tbody) return;

  const searchVal = (document.getElementById("eventSearchInput")?.value || "").toLowerCase().trim();
  const typeFilter = document.getElementById("eventTypeFilter")?.value || "";

  const filtered = allEvents.filter((e) => {
    if (typeFilter && e.type !== typeFilter) return false;
    if (searchVal) {
      const targetStr = `${e.type} ${e.zone_name || ""} ${e.product_name || ""} ${e.session_id || ""} ${e.status || ""}`.toLowerCase();
      if (!targetStr.includes(searchVal)) return false;
    }
    return true;
  });

  if (countBadge) {
    countBadge.textContent = `${filtered.length} رویداد`;
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">رویدادی یافت نشد</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((e) => {
      let typeBadgeClass = "status-badge status-inactive";
      let typeLabel = e.type;

      if (e.type === "PRODUCT_PICKED") {
        typeBadgeClass = "status-badge status-active";
        typeLabel = "🛒 برداشت کالا (PICKED)";
      } else if (e.type === "PRODUCT_RETURNED") {
        typeBadgeClass = "status-badge status-warning";
        typeLabel = "↩️ بازگشت کالا (RETURNED)";
      } else if (e.type === "CUSTOMER_ENTERED") {
        typeBadgeClass = "status-badge status-info";
        typeLabel = "👤 ورود مشتری";
      } else if (e.type === "SESSION_CLOSED") {
        typeBadgeClass = "status-badge status-inactive";
        typeLabel = "🔒 خروج مشتری";
      } else if (e.type === "DEVICE_CONNECTED") {
        typeBadgeClass = "status-badge status-active";
        typeLabel = "📡 اتصال دوربین";
      } else if (e.type === "DEVICE_DISCONNECTED") {
        typeBadgeClass = "status-badge status-danger";
        typeLabel = "🔌 قطع دوربین";
      }

      let statusBadgeClass = "status-badge status-active";
      let statusLabel = e.status;
      if (e.status === "PROCESSED") {
        statusBadgeClass = "status-badge status-active";
        statusLabel = "تأیید و اعمال‌شده";
      } else if (e.status === "IGNORED_NO_SESSION") {
        statusBadgeClass = "status-badge status-warning";
        statusLabel = "بدون جلسه فعال (نادیده)";
      } else if (e.status === "IGNORED_NOT_IN_CART") {
        statusBadgeClass = "status-badge status-warning";
        statusLabel = "عدم وجود در سبد (نادیده)";
      } else if (e.status === "IGNORED_NO_PRODUCT") {
        statusBadgeClass = "status-badge status-inactive";
        statusLabel = "فاقد کالا";
      }

      const timeFormatted = e.created_at ? formatTime(e.created_at) : "--:--";
      const zoneText = e.zone_name || (e.zone_id ? `جایگاه ${e.zone_id}` : "--");
      const productText = e.product_name || (e.product_id ? `کد ${e.product_id}` : (e.device_id ? `دستگاه ${e.device_id}` : "--"));
      const confText = e.confidence ? `${Math.round(e.confidence * 100)}%` : "--";
      const sessionText = e.session_id ? `#${e.session_id}` : "--";

      return `
        <tr>
          <td style="font-size: 0.85rem; font-family: monospace;">${timeFormatted}</td>
          <td><span class="${typeBadgeClass}">${typeLabel}</span></td>
          <td><strong>${sessionText}</strong></td>
          <td>${zoneText}</td>
          <td>${productText}</td>
          <td><code>${confText}</code></td>
          <td><span class="${statusBadgeClass}">${statusLabel}</span></td>
        </tr>
      `;
    })
    .join("");
}

document.getElementById("refreshEventsBtn")?.addEventListener("click", loadEvents);
document.getElementById("eventSearchInput")?.addEventListener("input", renderEvents);
document.getElementById("eventTypeFilter")?.addEventListener("change", renderEvents);

// ---------------------------------------------------------------------------
// Store Overview & Invoices (Phase 7)
// ---------------------------------------------------------------------------

let allInvoices = [];

async function loadOverview() {
  const panel = document.getElementById("panel_overview");
  if (!panel) return;

  try {
    const res = await authFetch("/api/admin/overview");
    if (!res.ok) return;
    const data = await res.json();
    const dict = i18nData[currentLang];

    // 1. Metric cards
    const todaySessionsEl = document.getElementById("metricTodaySessions");
    const activeCustEl = document.getElementById("metricActiveCustomer");
    const totalInvoicesEl = document.getElementById("metricTotalInvoices");
    const totalRevenueEl = document.getElementById("metricTotalRevenue");

    if (todaySessionsEl) todaySessionsEl.textContent = data.today_sessions_count;
    if (activeCustEl) {
      if (data.active_session) {
        activeCustEl.innerHTML = `<span style="color: var(--accent); font-size: 1.1rem;">جلسه #${data.active_session.id} (${data.active_session.items_count} کالا)</span>`;
      } else {
        activeCustEl.innerHTML = `<span style="color: var(--success); font-size: 1.1rem;">فروشگاه آزاد است</span>`;
      }
    }
    if (totalInvoicesEl) totalInvoicesEl.textContent = data.total_invoices_count;
    if (totalRevenueEl) totalRevenueEl.textContent = `${formatPrice(data.total_revenue)} ${dict.toman || "تومان"}`;

    // 2. Slots list
    renderOverviewSlots(data.zones);

    // 3. Devices status
    const devBox = document.getElementById("overviewDevicesBox");
    if (devBox && data.devices) {
      const isOnline = data.devices.camera_online;
      const isStale = data.devices.camera_stale;
      let statusBadge = `<span class="status-badge status-inactive">⚪ آفلاین</span>`;
      let warningHtml = "";

      if (isStale) {
        statusBadge = `<span class="status-badge status-danger">⚠️ دوربین بیش از ۱۰ ثانیه قطع است</span>`;
        warningHtml = `<div style="margin-top: 0.5rem; font-size: 0.8rem; color: #ff6b6b;">⚠️ بیش از ۱۰ ثانیه است که هیچ فریمی ارسال نشده؛ پردازش قفسه متوقف است.</div>`;
      } else if (isOnline) {
        statusBadge = `<span class="status-badge status-active">🟢 آنلاین</span>`;
      }

      devBox.innerHTML = `
        <div class="overview-device-row">
          <div>
            <strong>📷 حسگر دوربین قفسه (Tablet Sensor)</strong>
            <div style="font-size: 0.8rem; color: var(--text-muted);">${data.devices.camera_device_id || "شناسه: camera_tablet"}</div>
            ${warningHtml}
          </div>
          <div>${statusBadge}</div>
        </div>
      `;
    }
  } catch (err) {
    console.error("Failed to load overview:", err);
  }
}

function renderOverviewSlots(zonesList) {
  const container = document.getElementById("overviewSlotsList");
  if (!container || !Array.isArray(zonesList)) return;

  const dict = i18nData[currentLang];

  container.innerHTML = zonesList.map(z => {
    let stateBadge = `<span class="status-badge status-inactive">نامشخص</span>`;
    if (z.state === "PRESENT" || z.state === "FULL") {
      stateBadge = `<span class="status-badge status-active">🟢 ${dict.state_present || "موجود"}</span>`;
    } else if (z.state === "ABSENT" || z.state === "EMPTY") {
      stateBadge = `<span class="status-badge status-danger">🔴 ${dict.state_absent || "خالی"}</span>`;
    } else if (z.state === "TRANSITION") {
      stateBadge = `<span class="status-badge status-warning">🟡 ${dict.state_transition || "در حال تغییر"}</span>`;
    }

    const confText = z.confidence ? `(${Math.round(z.confidence * 100)}%)` : "";
    return `
      <div class="overview-slot-row">
        <div>
          <strong>${z.name}</strong>
          <div style="font-size: 0.8rem; color: var(--text-muted);">${z.product_name || "تخصیص نیافته"}</div>
        </div>
        <div style="display: flex; gap: 0.4rem; align-items: center;">
          ${stateBadge}
          <small style="color: var(--text-muted);">${confText}</small>
        </div>
      </div>
    `;
  }).join("");
}

async function loadInvoices() {
  const tbody = document.getElementById("invoicesTableBody");
  const badge = document.getElementById("invoicesCountBadge");
  if (!tbody) return;

  try {
    const res = await authFetch("/api/admin/invoices?limit=50");
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">خطا در دریافت فاکتورها</td></tr>`;
      return;
    }
    allInvoices = await res.json();
    const dict = i18nData[currentLang];

    if (badge) badge.textContent = `${allInvoices.length} فاکتور`;

    if (allInvoices.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">هنوز فاکتوری صادر نشده است</td></tr>`;
      return;
    }

    tbody.innerHTML = allInvoices.map(inv => {
      const itemsCount = inv.lines ? inv.lines.reduce((acc, l) => acc + l.quantity, 0) : 0;
      return `
        <tr>
          <td><strong>#INV-${inv.id}</strong></td>
          <td><strong>#${inv.session_id}</strong></td>
          <td dir="ltr" class="text-center">${formatDateTime(inv.created_at)}</td>
          <td>${itemsCount} کالا</td>
          <td><strong>${formatPrice(inv.total)} ${dict.toman || "تومان"}</strong></td>
          <td style="text-align: center;">
            <button class="btn btn-secondary btn-sm" onclick="openInvoiceDetailsModal(${inv.id})">
              🔍 مشاهده
            </button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">خطای شبکه در دریافت فاکتورها</td></tr>`;
  }
}

async function openInvoiceDetailsModal(invId) {
  const modal = document.getElementById("invoiceModal");
  const modalBody = document.getElementById("invModalBody");
  const title = document.getElementById("invModalTitle");
  if (!modal || !modalBody) return;

  try {
    const res = await authFetch(`/api/admin/invoices/${invId}`);
    if (!res.ok) {
      showToast("فاکتور مورد نظر یافت نشد", "danger");
      return;
    }
    const inv = await res.json();
    const dict = i18nData[currentLang];

    if (title) title.textContent = `🧾 جزئیات فاکتور #INV-${inv.id} (جلسه #${inv.session_id})`;

    modalBody.innerHTML = `
      <div style="margin-bottom: 1rem; font-size: 0.85rem; color: var(--text-muted); display: flex; justify-content: space-between;">
        <span>زمان صدور: ${formatDateTime(inv.created_at)}</span>
        <span>شناسه جلسه: #${inv.session_id}</span>
      </div>
      <table class="data-table" style="margin-bottom: 1rem;">
        <thead>
          <tr>
            <th>نام محصول</th>
            <th>قیمت واحد</th>
            <th>تعداد</th>
            <th>مجموع ردیف</th>
          </tr>
        </thead>
        <tbody>
          ${(inv.lines || []).map(line => `
            <tr>
              <td><strong>${line.product_name}</strong></td>
              <td>${formatPrice(line.unit_price)}</td>
              <td>× ${line.quantity}</td>
              <td><strong>${formatPrice(line.line_total)}</strong></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      <div style="text-align: left; font-size: 1.1rem; font-weight: 800; color: var(--accent); padding-top: 0.5rem; border-top: 1px dashed var(--border-color);">
        <span>مبلغ کل پرداختی: ${formatPrice(inv.total)} ${dict.toman || "تومان"}</span>
      </div>
    `;

    modal.classList.add("active");
  } catch (err) {
    showToast("خطا در باز کردن فاکتور", "danger");
  }
}

function closeInvoiceModal() {
  const modal = document.getElementById("invoiceModal");
  if (modal) modal.classList.remove("active");
}

document.getElementById("closeInvModalBtn")?.addEventListener("click", closeInvoiceModal);
document.getElementById("closeInvModalFooterBtn")?.addEventListener("click", closeInvoiceModal);
document.getElementById("refreshInvoicesBtn")?.addEventListener("click", loadInvoices);
document.getElementById("genPairingCodeBtn")?.addEventListener("click", generateCameraPairingCode);

// Camera Pairing Code Generation
let pairingTimerInterval = null;

async function generateCameraPairingCode() {
  tabletPairedOnline = false;
  const card = document.getElementById("pairingCodeCard");
  const pendingBox = document.getElementById("pairingCodePendingBox");
  const successBox = document.getElementById("pairingCodeSuccessBox");
  const codeEl = document.getElementById("pairingCodeDisplay");
  const timerEl = document.getElementById("pairingTimerDisplay");
  const directInput = document.getElementById("cameraDirectUrlInput");
  const openLink = document.getElementById("openCameraUrlLink");
  if (!card || !codeEl) return;

  try {
    const res = await authFetch("/api/admin/camera/pairing-code", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `دریافت کد از سرور ناموفق بود (HTTP ${res.status})`);
    const code = window.SmartShelfFormat.normalizePairingCode(data.code || data.pairing_code || "");
    if (!/^[0-9]{6}$/.test(code)) throw new Error("سرور کد شش‌رقمی معتبر ارسال نکرد.");
    try { localStorage.setItem("smartshelf_pairing_code", code); } catch (e) {}

    codeEl.textContent = code;
    card.style.display = "block";
    card.style.background = "rgba(0, 180, 216, 0.08)";
    card.style.borderColor = "rgba(0, 180, 216, 0.4)";
    if (pendingBox) pendingBox.style.display = "block";
    if (successBox) successBox.style.display = "none";

    const cameraUrl = `${window.location.origin}/camera/?code=${code}`;
    if (directInput) directInput.value = cameraUrl;
    if (openLink) openLink.href = cameraUrl;

    showToast(`کد جفت‌سازی ۵ دقیقه‌ای تولید شد: ${code}`, "success");

    // Device state arrives on the authenticated admin WebSocket.
    startListeningForTabletPair(code);

    let remaining = (data && data.expires_in) || 300;
    if (pairingTimerInterval) clearInterval(pairingTimerInterval);
    const updateTimer = () => {
      const mins = String(Math.floor(remaining / 60)).padStart(2, "0");
      const secs = String(remaining % 60).padStart(2, "0");
      if (timerEl) timerEl.textContent = `⏱️ ${mins}:${secs}`;
      if (remaining <= 0) {
        clearInterval(pairingTimerInterval);
        if (!tabletPairedOnline) {
          card.style.display = "none";
        }
      }
      remaining--;
    };
    updateTimer();
    pairingTimerInterval = setInterval(updateTimer, 1000);
  } catch (err) {
    if (pairingTimerInterval) clearInterval(pairingTimerInterval);
    try { localStorage.removeItem("smartshelf_pairing_code"); } catch (e) {}
    codeEl.textContent = "";
    card.style.display = "none";
    if (directInput) directInput.value = "";
    if (openLink) openLink.removeAttribute("href");
    showToast(err.message || "کد جفت‌سازی از سرور دریافت نشد؛ اتصال را بررسی کنید.", "error");
  }
}

document.getElementById("reGenCodeBtn")?.addEventListener("click", generateCameraPairingCode);

document.getElementById("copyCameraUrlBtn")?.addEventListener("click", () => {
  const input = document.getElementById("cameraDirectUrlInput");
  if (input && input.value) {
    input.select();
    navigator.clipboard.writeText(input.value);
    showToast("لینک اتصال مستقیم تبلت کپی شد", "success");
  }
});

// ---------------------------------------------------------------------------
// Recognition Lab Studio (Phase 7)
// ---------------------------------------------------------------------------

let recSelectedImageBlob = null;
let recCameraStream = null;

async function loadRecognitionLab() {
  await Promise.all([fetchRecognitionStatus(), loadLatestEvaluationReport()]);
  populateRecFeedbackProducts();
}

async function fetchRecognitionStatus() {
  try {
    const res = await authFetch("/api/admin/recognition/status");
    if (!res.ok) return;
    const data = await res.json();

    const vectorsEl = document.getElementById("recVectorsCount");
    const productsEl = document.getElementById("recProductsCount");
    const acceptEl = document.getElementById("recAcceptThreshold");
    const marginEl = document.getElementById("recMarginThreshold");
    const badgeEl = document.getElementById("recEngineBadge");

    if (vectorsEl) vectorsEl.textContent = data.indexed_vectors_count || 0;
    if (productsEl) productsEl.textContent = data.unique_products_indexed || 0;
    if (acceptEl) acceptEl.textContent = data.t_accept || 0.65;
    if (marginEl) marginEl.textContent = data.t_margin || 0.08;
    if (badgeEl) badgeEl.textContent = `${data.model_version || "MobileNetV2-7"} • ${data.device || "CPU"}`;
  } catch (err) {
    console.warn("Failed to fetch recognition status:", err);
  }
}

function populateRecFeedbackProducts() {
  const sel = document.getElementById("recCorrectProductSelect");
  if (!sel) return;
  sel.innerHTML = `<option value="">انتخاب محصول صحیح کاتالوگ...</option>` +
    allProducts.map(p => `<option value="${p.id}">${p.name} (${p.sku})</option>`).join("");
}

// Rebuild Recognition Vector Index
document.getElementById("rebuildRecIndexBtn")?.addEventListener("click", async () => {
  try {
    const res = await authFetch("/api/admin/recognition/rebuild-index", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      showToast(`شاخص بازسازی شد (${data.indexed_vectors_count} بردار)`, "success");
      await fetchRecognitionStatus();
    } else {
      showToast("خطا در بازسازی شاخص", "danger");
    }
  } catch (err) {
    showToast("خطای ارتباط با سرور", "danger");
  }
});

// File input selection
document.getElementById("recFileInput")?.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;

  recSelectedImageBlob = file;
  const preview = document.getElementById("recPreviewImg");
  const placeholder = document.getElementById("recNoImagePlaceholder");
  const runBtn = document.getElementById("runRecognitionBtn");

  if (preview) {
    preview.src = URL.createObjectURL(file);
    preview.style.display = "block";
  }
  if (placeholder) placeholder.style.display = "none";
  if (runBtn) runBtn.disabled = false;
});

// Camera controls in Recognition Lab
async function toggleRecCamera() {
  const container = document.getElementById("recCameraContainer");
  const video = document.getElementById("recCameraVideo");
  if (!container || !video) return;

  if (recCameraStream) {
    stopRecCamera();
    return;
  }

  try {
    recCameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 640 }, height: { ideal: 480 } }
    });
    video.srcObject = recCameraStream;
    container.style.display = "block";
  } catch (err) {
    showToast("عدم دسترسی به دوربین (مجوز وب‌کم یا HTTPS بررسی شود)", "danger");
  }
}

function stopRecCamera() {
  if (recCameraStream) {
    recCameraStream.getTracks().forEach(t => t.stop());
    recCameraStream = null;
  }
  const container = document.getElementById("recCameraContainer");
  if (container) container.style.display = "none";
}

document.getElementById("recToggleCameraBtn")?.addEventListener("click", toggleRecCamera);
document.getElementById("recCloseCameraBtn")?.addEventListener("click", stopRecCamera);

// Snap frame from camera
document.getElementById("recSnapCameraBtn")?.addEventListener("click", () => {
  const video = document.getElementById("recCameraVideo");
  const canvas = document.getElementById("recCameraCanvas");
  if (!video || !canvas || !recCameraStream) return;

  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob((blob) => {
    if (!blob) return;
    recSelectedImageBlob = blob;

    const preview = document.getElementById("recPreviewImg");
    const placeholder = document.getElementById("recNoImagePlaceholder");
    const runBtn = document.getElementById("runRecognitionBtn");

    if (preview) {
      preview.src = URL.createObjectURL(blob);
      preview.style.display = "block";
    }
    if (placeholder) placeholder.style.display = "none";
    if (runBtn) runBtn.disabled = false;

    stopRecCamera();
    showToast("فریم دوربین ضبط شد", "success");
  }, "image/jpeg", 0.92);
});

// Run Recognition Inference
document.getElementById("runRecognitionBtn")?.addEventListener("click", async () => {
  if (!recSelectedImageBlob) {
    showToast("لطفاً ابتدا تصویری انتخاب یا با دوربین ضبط نمایید", "warning");
    return;
  }

  const runBtn = document.getElementById("runRecognitionBtn");
  const resultContainer = document.getElementById("recResultDetails");
  const feedbackBox = document.getElementById("recFeedbackBox");
  if (!resultContainer) return;

  runBtn.disabled = true;
  runBtn.textContent = "⏳ در حال استخراج بردار و پردازش...";

  const formData = new FormData();
  formData.append("file", recSelectedImageBlob, "query.jpg");

  try {
    const res = await authFetch("/api/admin/recognition/identify", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      resultContainer.innerHTML = `<div class="text-danger" style="padding: 1.5rem;">خطا: ${err.detail || "خطا در پردازش"}</div>`;
      return;
    }

    const data = await res.json();
    renderRecognitionResult(data);

    if (feedbackBox) {
      feedbackBox.style.display = "block";
      const sel = document.getElementById("recCorrectProductSelect");
      if (sel && data.product_id) {
        sel.value = data.product_id;
      }
    }
  } catch (err) {
    resultContainer.innerHTML = `<div class="text-danger" style="padding: 1.5rem;">خطای ارتباط با سرور در زمان استنتاج</div>`;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "🚀 اجرای شناسایی کالا (Inference)";
  }
});

function renderRecognitionResult(data) {
  const container = document.getElementById("recResultDetails");
  if (!container) return;

  let statusBadge = "";
  if (data.status === "RECOGNIZED") {
    statusBadge = `<span class="status-badge status-active" style="font-size: 0.95rem; padding: 4px 10px;">✓ شناسایی شد (RECOGNIZED)</span>`;
  } else if (data.status === "NEEDS_REVIEW") {
    statusBadge = `<span class="status-badge" style="background: var(--color-warning-bg); color: var(--color-warning); font-size: 0.95rem; padding: 4px 10px;">⚠️ نیازمند بازبینی (NEEDS_REVIEW - تناقض بارکد و تصویر)</span>`;
  } else {
    statusBadge = `<span class="status-badge status-inactive" style="font-size: 0.95rem; padding: 4px 10px;">❓ نامشخص (UNKNOWN)</span>`;
  }

  let barcodeSection = "";
  if (data.barcode) {
    const bcStatus = data.barcode_match
      ? `<span style="color: var(--color-success); font-weight: 600;">✓ بارکد در کاتالوگ موجود است</span>`
      : `<span style="color: var(--color-warning); font-weight: 600;">⚠️ بارکد در کاتالوگ ثبت نشده</span>`;
    barcodeSection = `
      <div style="background: var(--bg-surface); padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--border-default); margin-top: 0.5rem; font-size: 0.85rem;">
        📟 بارکد خوانده شده با zxing: <code dir="ltr">${data.barcode}</code> — ${bcStatus}
      </div>
    `;
  } else {
    barcodeSection = `<div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.4rem;">📷 بارکدی در کادر شناسایی نشد (استنتاج صرفاً بصری)</div>`;
  }

  const blurInfo = data.quality
    ? `<span style="font-size: 0.8rem; color: var(--text-muted);">کیفیت تصویر: واریانس لاپلاسین ${data.quality.blur_score} ${data.quality.is_blurry ? '(⚠️ تصویر تار است)' : '(مطلوب)'}</span>`
    : "";

  let top3Html = "";
  if (data.top3 && data.top3.length > 0) {
    top3Html = `
      <div style="margin-top: 1rem;">
        <label style="font-size: 0.85rem; font-weight: 700; color: var(--text-muted); display: block; margin-bottom: 0.5rem;">
          سه گزینه با بالاترین شباهت کسینوسی (Top-3 Matches):
        </label>
        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
    `;

    data.top3.forEach((item, idx) => {
      const pct = Math.max(0, Math.min(100, Math.round(item.similarity * 100)));
      const barColor = idx === 0 ? "var(--accent-primary)" : "var(--border-strong)";
      top3Html += `
        <div style="background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: 6px; padding: 0.5rem 0.75rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
            <strong>${idx + 1}. ${item.name} <code class="sku-code">${item.sku}</code></strong>
            <span style="font-family: monospace; font-weight: 700;">${pct}% (${item.similarity})</span>
          </div>
          <div style="background: var(--bg-muted); height: 8px; border-radius: 4px; overflow: hidden;">
            <div style="width: ${pct}%; height: 100%; background: ${barColor}; border-radius: 4px; transition: width 0.3s ease;"></div>
          </div>
        </div>
      `;
    });

    top3Html += `</div></div>`;
  }

  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem;">
      <div>${statusBadge}</div>
      <div style="font-size: 0.82rem; color: var(--text-muted); font-family: monospace;">⏱️ تأخیر استنتاج: <strong>${data.processing_time_ms} ms</strong></div>
    </div>

    ${data.name ? `
      <div style="background: var(--accent-subtle); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--border-strong); margin-bottom: 0.75rem;">
        <div style="font-size: 1.1rem; font-weight: 800; color: var(--text-primary);">${data.name}</div>
        <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 0.25rem;">
          کد کالا: <code class="sku-code">${data.sku}</code> | بارکد: <code dir="ltr">${data.gtin || '—'}</code>
        </div>
        <div style="font-size: 0.85rem; margin-top: 0.35rem; display: flex; gap: 1rem;">
          <span>امتیاز شباهت اول: <strong>${data.similarity}</strong></span>
          <span>حاشیه نسبت به دوم: <strong>${data.margin}</strong></span>
        </div>
      </div>
    ` : ''}

    ${barcodeSection}
    <div style="margin-top: 0.4rem;">${blurInfo}</div>
    ${top3Html}
  `;
}

// Feedback submission
document.getElementById("recSubmitFeedbackBtn")?.addEventListener("click", async () => {
  const sel = document.getElementById("recCorrectProductSelect");
  const prodId = sel ? parseInt(sel.value) : null;
  if (!prodId) {
    showToast("لطفاً محصول صحیح را از لیست انتخاب کنید", "warning");
    return;
  }
  if (!recSelectedImageBlob) {
    showToast("تصویری موجود نیست", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("file", recSelectedImageBlob, "feedback.jpg");

  try {
    const res = await authFetch(`/api/admin/recognition/feedback?product_id=${prodId}`, {
      method: "POST",
      body: formData,
    });
    if (res.ok) {
      showToast("بازخورد ثبت و ویژگی‌های تصویر به کالا متصل شد", "success");
      await fetchRecognitionStatus();
    } else {
      showToast("خطا در ثبت بازخورد", "danger");
    }
  } catch (err) {
    showToast("خطای شبکه", "danger");
  }
});

// Load Latest Evaluation Report
async function loadLatestEvaluationReport() {
  const container = document.getElementById("recEvalReportContainer");
  if (!container) return;

  try {
    const res = await authFetch("/api/admin/recognition/latest-eval");
    if (!res.ok) return;
    const data = await res.json();

    if (!data.available) {
      container.innerHTML = `<div class="text-center text-muted" style="padding: 1.5rem;">هنوز گزارش ارزیابی ثبت نشده است. اسکریپت <code>ai/evaluation/evaluate.py</code> را اجرا کنید.</div>`;
      return;
    }

    let classRows = "";
    if (data.per_class) {
      classRows = Object.entries(data.per_class).map(([cls, m]) => `
        <tr>
          <td><code>${cls}</code></td>
          <td>${m.total}</td>
          <td>${(m.precision * 100).toFixed(1)}%</td>
          <td>${(m.recall * 100).toFixed(1)}%</td>
          <td><strong>${(m.f1 * 100).toFixed(1)}%</strong></td>
        </tr>
      `).join("");
    }

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.25rem;">
        <div class="telemetry-card">
          <span class="telemetry-label">دقت کل (Top-1 Accuracy):</span>
          <strong class="telemetry-val" style="color: var(--color-success);">${(data.top1_accuracy * 100).toFixed(1)}%</strong>
        </div>
        <div class="telemetry-card">
          <span class="telemetry-label">تشخیص ناشناخته (UDR):</span>
          <strong class="telemetry-val">${(data.unknown_detection_rate * 100).toFixed(1)}%</strong>
        </div>
        <div class="telemetry-card">
          <span class="telemetry-label">خطای کاذب (FRR):</span>
          <strong class="telemetry-val" style="color: ${(data.false_recognition_rate > 0.05 ? 'var(--color-danger)' : 'var(--text-primary)')};">${(data.false_recognition_rate * 100).toFixed(2)}%</strong>
        </div>
        <div class="telemetry-card">
          <span class="telemetry-label">تأخیر p50 / p95 (CPU):</span>
          <strong class="telemetry-val">${data.latency_ms?.p50 || 0} / ${data.latency_ms?.p95 || 0} ms</strong>
        </div>
      </div>

      <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.75rem;">
        <span>📅 تاریخ ارزیابی: ${data.timestamp}</span> |
        <span>مدل: <code>${data.model_version}</code></span> |
        <span>هش دیتاست: <code>${data.dataset_hash}</code></span> |
        <span>تعداد نمونه‌ها: ${data.total_samples} (${data.known_samples} آشنا، ${data.unknown_samples} متفرقه)</span>
      </div>

      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>کلاس کالا (SKU)</th>
              <th>تعداد نمونه</th>
              <th>دقت (Precision)</th>
              <th>بازخوانی (Recall)</th>
              <th>امتیاز F1</th>
            </tr>
          </thead>
          <tbody>
            ${classRows || '<tr><td colspan="5" class="text-center text-muted">موردی موجود نیست</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="text-center text-muted" style="padding: 1.5rem;">خطا در دریافت گزارش ارزیابی</div>`;
  }
}

document.getElementById("refreshEvalReportBtn")?.addEventListener("click", loadLatestEvaluationReport);

// Initial boot
updateLocalization();
checkAuth();
startListeningForTabletPair(localStorage.getItem("smartshelf_pairing_code") || "");
