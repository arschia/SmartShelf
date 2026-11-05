// SMARTSHELF Customer Mobile App - Phase 5 Redesign

let socket = null;
let currentSessionSecret = null;
let latestCart = null;
let latestInvoice = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let customerAuthTimer = null;
let customerAuthConfirmed = false;

function updateWsBadge(status) {
  const badge = document.getElementById("wsBadge");
  const text = document.getElementById("wsStatusText");
  const dot = document.getElementById("wsPulseDot");
  const banner = document.getElementById("offlineBanner");

  if (!badge || !text) return;

  if (status === "online") {
    badge.className = "connection-pill online";
    dot.className = "pulse-dot pulse-dot-live";
    text.textContent = "متصل به سرور";
    if (banner) banner.style.display = "none";
    reconnectAttempts = 0;
  } else if (status === "offline") {
    badge.className = "connection-pill offline";
    dot.className = "pulse-dot";
    text.textContent = "قطع ارتباط";
    if (banner) banner.style.display = "flex";
  } else {
    badge.className = "connection-pill";
    dot.className = "pulse-dot";
    text.textContent = "در حال اتصال...";
    if (banner) banner.style.display = "none";
  }
}

function renderCart(cartData) {
  latestCart = cartData;

  const emptyNotice = document.getElementById("cartEmptyNotice");
  const itemsList = document.getElementById("cartItemsList");
  const sheetList = document.getElementById("sheetItemsList");
  const countBadge = document.getElementById("cartCountBadge");
  const grandTotalEl = document.getElementById("stickyGrandTotal");
  const checkoutBtn = document.getElementById("checkoutBtn");
  const actionBar = document.getElementById("customerActionBar");

  const isEmpty = !cartData || !cartData.items || cartData.items.length === 0;

  if (actionBar) actionBar.style.display = "flex";
  if (checkoutBtn) checkoutBtn.disabled = isEmpty;

  if (isEmpty) {
    if (emptyNotice) emptyNotice.style.display = "block";
    if (itemsList) {
      itemsList.style.display = "none";
      itemsList.innerHTML = "";
    }
    if (sheetList) sheetList.innerHTML = "<p style='color: var(--text-muted); font-size: var(--font-sm);'>سبد خرید شما خالی است.</p>";
    if (countBadge) countBadge.textContent = "۰ کالا";
    if (grandTotalEl) grandTotalEl.textContent = "۰ تومان";
    return;
  }

  if (emptyNotice) emptyNotice.style.display = "none";
  if (itemsList) itemsList.style.display = "flex";

  const totalQty = cartData.total_quantity || 0;
  if (countBadge) {
    countBadge.textContent = `${SmartShelfFormat.toPersianDigits(totalQty)} کالا`;
  }

  if (grandTotalEl) {
    const formattedTotal = SmartShelfFormat.formatToman(cartData.grand_total || 0);
    grandTotalEl.textContent = formattedTotal;
    grandTotalEl.classList.remove("anim-count-bump");
    void grandTotalEl.offsetWidth;
    grandTotalEl.classList.add("anim-count-bump");
  }

  // Render product cards
  if (itemsList) {
    itemsList.innerHTML = cartData.items.map(item => {
      const imgSrc = window.SmartShelfApi.mediaUrl(item.image_path || "/assets/img/placeholder.png");
      const unitPriceStr = SmartShelfFormat.formatToman(item.unit_price);
      const lineTotalStr = SmartShelfFormat.formatToman(item.line_total);
      const qtyStr = SmartShelfFormat.toPersianDigits(item.quantity);

      return `
        <article class="product-card anim-cart-add" id="cart-item-${item.product_id}">
          <img src="${imgSrc}" alt="${item.product_name}" class="product-card-img" onerror="this.src='/assets/img/placeholder.png'">
          <div class="product-card-body">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-2);">
              <h3 class="product-card-title">${item.product_name}</h3>
              <span class="badge badge-success">در سبد</span>
            </div>
            <div class="product-card-price">${unitPriceStr}</div>
            <div class="product-card-actions" style="margin-block-start: var(--space-1); justify-content: space-between;">
              <span style="font-size: var(--font-xs); color: var(--text-muted);">
                تعداد: <strong style="color: var(--text-primary); font-size: var(--font-sm);">${qtyStr}</strong>
              </span>
              <span style="font-size: var(--font-sm); font-weight: bold; color: var(--primary);">
                جمع: ${lineTotalStr}
              </span>
            </div>
          </div>
        </article>
      `;
    }).join("");
  }

  // Render sheet preview
  if (sheetList) {
    sheetList.innerHTML = cartData.items.map(item => `
      <div style="display: flex; justify-content: space-between; align-items: center; padding-block: var(--space-2); border-block-end: 1px solid var(--border-subtle);">
        <div>
          <div style="font-weight: bold; font-size: var(--font-sm);">${item.product_name}</div>
          <div style="font-size: var(--font-xs); color: var(--text-muted);">${SmartShelfFormat.formatToman(item.unit_price)} × ${SmartShelfFormat.toPersianDigits(item.quantity)}</div>
        </div>
        <div style="font-weight: bold; color: var(--primary); font-size: var(--font-sm);">${SmartShelfFormat.formatToman(item.line_total)}</div>
      </div>
    `).join("");
  }
}

function renderInvoice(inv) {
  latestInvoice = inv;

  document.getElementById("stateLoading").style.display = "none";
  document.getElementById("stateActive").style.display = "none";
  document.getElementById("customerActionBar").style.display = "none";
  document.getElementById("stateInvoice").style.display = "block";

  const numEl = document.getElementById("invoiceNumberDisplay");
  const dateEl = document.getElementById("invoiceDate");
  const linesEl = document.getElementById("invoiceLinesContainer");
  const totalEl = document.getElementById("invoiceTotalDisplay");

  if (numEl) numEl.textContent = `#INV-${inv.id}`;
  if (dateEl) dateEl.textContent = SmartShelfFormat.formatJalali(inv.created_at || new Date());
  if (totalEl) totalEl.textContent = SmartShelfFormat.formatToman(inv.total);

  if (linesEl && Array.isArray(inv.lines)) {
    linesEl.innerHTML = inv.lines.map(line => `
      <div class="ticket-line-item">
        <div>
          <span>${line.product_name}</span>
          <span style="font-size: var(--font-xs); color: var(--text-muted); margin-inline-start: var(--space-1);">
            (${SmartShelfFormat.toPersianDigits(line.quantity)} × ${SmartShelfFormat.formatNumber(line.unit_price)})
          </span>
        </div>
        <strong>${SmartShelfFormat.formatToman(line.line_total)}</strong>
      </div>
    `).join("");
  }

  SmartShelfUI.triggerHaptic([30, 80, 40]);
}

async function performCheckout() {
  if (!currentSessionSecret) return;
  const checkoutBtn = document.getElementById("checkoutBtn");
  if (checkoutBtn) checkoutBtn.disabled = true;
  try {
    const checkoutUrl = window.SmartShelfApi
      ? window.SmartShelfApi.apiUrl(`/api/customer/checkout?secret=${encodeURIComponent(currentSessionSecret)}`)
      : `/api/customer/checkout?secret=${encodeURIComponent(currentSessionSecret)}`;
    const res = await fetch(checkoutUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      SmartShelfUI.showToast({message:data.detail || `خطا در تسویه‌حساب (HTTP ${res.status})`,type:"danger"});
      if (checkoutBtn) checkoutBtn.disabled = false;
      return;
    }
    if (data.invoice) renderInvoice(data.invoice);
  } catch (err) {
    SmartShelfUI.showToast({message:"ارتباط با سرور برقرار نشد؛ فاکتور ثبت نشده است.",type:"danger"});
    if (checkoutBtn) checkoutBtn.disabled = false;
  }
}

async function performExitEmpty() {
  if (!currentSessionSecret) return;
  try {
    const exitUrl = window.SmartShelfApi
      ? window.SmartShelfApi.apiUrl(`/api/customer/exit-empty?secret=${encodeURIComponent(currentSessionSecret)}`)
      : `/api/customer/exit-empty?secret=${encodeURIComponent(currentSessionSecret)}`;
    const res = await fetch(exitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      SmartShelfUI.showToast({message:data.detail || `خطا در ثبت خروج (HTTP ${res.status})`,type:"danger"});
      return;
    }
    document.getElementById("stateActive").style.display = "none";
    document.getElementById("customerActionBar").style.display = "none";
    document.getElementById("stateClosed").style.display = "block";
    const reasonEl = document.getElementById("closedReasonText");
    if (reasonEl) reasonEl.textContent = data.message || "خروج بدون خرید ثبت شد. از مراجعه شما متشکریم.";
    SmartShelfUI.triggerHaptic(20);
  } catch (err) {
    SmartShelfUI.showToast({message:"ارتباط با سرور برقرار نشد؛ خروج ثبت نشده است.",type:"danger"});
  }
}

async function fetchLiveCart(secret) {
  if (!secret) return;
  try {
    const cartUrl = window.SmartShelfApi
      ? window.SmartShelfApi.apiUrl(`/api/customer/cart?secret=${encodeURIComponent(secret)}`)
      : `/api/customer/cart?secret=${encodeURIComponent(secret)}`;
    const res = await fetch(cartUrl);
    if (res.ok) {
      const cart = await res.json();
      renderCart(cart);
    }
  } catch (err) {
    console.error("Failed to fetch live cart:", err);
  }
}

async function initCustomerSession() {
  const urlParams = new URLSearchParams(window.location.search);
  const sessionSecret = urlParams.get("session") || sessionStorage.getItem("smartshelf_session_secret") || localStorage.getItem("smartshelf_session_secret");
  currentSessionSecret = sessionSecret;

  const stateLoading = document.getElementById("stateLoading");
  const stateActive = document.getElementById("stateActive");
  const stateClosed = document.getElementById("stateClosed");
  const stateError = document.getElementById("stateError");

  if (!sessionSecret) {
    stateLoading.style.display = "none";
    stateError.style.display = "block";
    updateWsBadge("offline");
    return;
  }

  try {
    const sessionUrl = window.SmartShelfApi
      ? window.SmartShelfApi.apiUrl(`/api/customer/session?secret=${encodeURIComponent(sessionSecret)}`)
      : `/api/customer/session?secret=${encodeURIComponent(sessionSecret)}`;
    const res = await fetch(sessionUrl, {cache:"no-store"});
    const data = await res.json().catch(() => ({}));
    stateLoading.style.display = "none";

    if (!res.ok) {
      stateError.style.display = "block";
      updateWsBadge("offline");
      const message = document.getElementById("stateErrorMessage");
      if (message) message.textContent = data.detail || "سرور فروشگاه در دسترس نیست؛ لطفاً دوباره تلاش کنید.";
      return;
    }
    if (!data.valid) {
      if (data.status === "CLOSED") {
        stateClosed.style.display = "block";
        const reasonEl = document.getElementById("closedReasonText");
        if (reasonEl && data.message) reasonEl.textContent = data.message;
      } else {
        stateError.style.display = "block";
      }
      updateWsBadge("offline");
      return;
    }

    stateActive.style.display = "block";
    document.getElementById("sessionIdDisplay").textContent = `#${SmartShelfFormat.toPersianDigits(data.session_id)}`;
    document.getElementById("sessionTimeDisplay").textContent = SmartShelfFormat.formatJalali(data.entered_at, {hour:"2-digit",minute:"2-digit"});
    await fetchLiveCart(sessionSecret);
    connectCustomerWs(sessionSecret);
  } catch (err) {
    stateLoading.style.display = "none";
    stateError.style.display = "block";
    updateWsBadge("offline");
    const message = document.getElementById("stateErrorMessage");
    if (message) message.textContent = "ارتباط با سرور برقرار نشد؛ هیچ سبد یا فاکتور آزمایشی ساخته نشده است.";
  }
}

function connectCustomerWs(sessionSecret) {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const wsUrl = window.SmartShelfApi
    ? window.SmartShelfApi.wsUrl("/ws/customer")
    : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/customer`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    customerAuthConfirmed = false;
    updateWsBadge("connecting");
    socket.send(JSON.stringify({ type: "AUTH", session_secret: sessionSecret }));
    if (customerAuthTimer) clearTimeout(customerAuthTimer);
    customerAuthTimer = setTimeout(() => {
      if (socket && socket.readyState === WebSocket.OPEN && !customerAuthConfirmed) {
        socket.close(1008, "customer auth acknowledgement timeout");
      }
    }, 6000);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);

      if (msg.type === "CART_SYNC" || msg.type === "CART_UPDATED") {
        if (msg.type === "CART_SYNC" && !customerAuthConfirmed) {
          customerAuthConfirmed = true;
          if (customerAuthTimer) clearTimeout(customerAuthTimer);
          customerAuthTimer = null;
          updateWsBadge("online");
          fetchLiveCart(sessionSecret);
        }
        const recEl = document.getElementById("recognizingProductAlert");
        if (recEl) recEl.style.display = "none";

        renderCart(msg.cart);

        if (msg.action === "PICKED") {
          SmartShelfUI.triggerHaptic([25, 40]);
          SmartShelfUI.showToast({
            message: `محصول برداشته شد: ${msg.product_name}`,
            type: "success",
            undoText: "بازگردانی",
            onUndo: () => {
              SmartShelfUI.showToast({ message: "لطفاً محصول را به جایگاه قفسه بازگردانید." });
            }
          });
        } else if (msg.action === "RETURNED") {
          SmartShelfUI.triggerHaptic(20);
          SmartShelfUI.showToast({
            message: `محصول بازگردانده شد: ${msg.product_name}`,
            type: "warning"
          });
        }
      } else if (msg.type === "RECOGNIZING") {
        const recEl = document.getElementById("recognizingProductAlert");
        if (recEl) {
          recEl.style.display = "flex";
          if (msg.message) {
            const txt = document.getElementById("recognizingProductText");
            if (txt) txt.textContent = msg.message;
          }
        }
      } else if (msg.type === "PRODUCT_UNCERTAIN" || msg.type === "PRODUCT_MISMATCH") {
        const recEl = document.getElementById("recognizingProductAlert");
        if (recEl) recEl.style.display = "none";

        const alertEl = document.getElementById("uncertainProductAlert");
        if (alertEl) {
          alertEl.style.display = "block";
          alertEl.classList.remove("anim-product-shake");
          void alertEl.offsetWidth;
          alertEl.classList.add("anim-product-shake");
          const msgSpan = alertEl.querySelector("span");
          if (msgSpan && msg.message) {
            msgSpan.textContent = `⚠ ${msg.message}`;
          }
          SmartShelfUI.triggerHaptic([40, 60, 40]);
          setTimeout(() => { alertEl.style.display = "none"; }, 6000);
        }
      } else if (msg.type === "SESSION_CLOSED") {
        if (msg.exit_reason === "CHECKOUT" && msg.invoice) {
          renderInvoice(msg.invoice);
        } else {
          document.getElementById("stateActive").style.display = "none";
          document.getElementById("customerActionBar").style.display = "none";
          document.getElementById("stateClosed").style.display = "block";
          const reasonEl = document.getElementById("closedReasonText");
          if (reasonEl && msg.exit_reason) {
            reasonEl.textContent = `دلیل خروج: ${msg.exit_reason}`;
          }
        }
      }
    } catch (e) {
      // Ignore ping/pong
    }
  };

  socket.onclose = () => {
    customerAuthConfirmed = false;
    if (customerAuthTimer) clearTimeout(customerAuthTimer);
    customerAuthTimer = null;
    updateWsBadge("offline");
    if (!reconnectTimer && currentSessionSecret) {
      reconnectAttempts++;
      const delay = Math.min(3000 * reconnectAttempts, 10000);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectCustomerWs(currentSessionSecret);
      }, delay);
    }
  };

  socket.onerror = () => {
    updateWsBadge("offline");
  };
}

document.addEventListener("DOMContentLoaded", () => {
  // Theme toggle
  document.getElementById("themeToggleBtn")?.addEventListener("click", () => {
    SmartShelfUI.toggleTheme();
  });

  // Language / Direction toggle
  document.getElementById("langToggleBtn")?.addEventListener("click", () => {
    SmartShelfUI.toggleDirection();
  });

  // Bottom Sheet bindings
  const sheet = document.getElementById("cartSheet");
  const sheetBackdrop = document.getElementById("cartSheetBackdrop");
  document.getElementById("openSheetBtn")?.addEventListener("click", () => {
    SmartShelfUI.openBottomSheet(sheet, sheetBackdrop);
  });
  document.getElementById("closeSheetBtn")?.addEventListener("click", () => {
    SmartShelfUI.closeBottomSheet(sheet, sheetBackdrop);
  });
  document.getElementById("closeSheetCrossBtn")?.addEventListener("click", () => {
    SmartShelfUI.closeBottomSheet(sheet, sheetBackdrop);
  });
  sheetBackdrop?.addEventListener("click", () => {
    SmartShelfUI.closeBottomSheet(sheet, sheetBackdrop);
  });

  // Exit Modal bindings
  const exitModal = document.getElementById("exitModal");
  document.getElementById("exitEmptyBtn")?.addEventListener("click", () => {
    SmartShelfUI.openModal(exitModal);
  });
  document.getElementById("closeModalCrossBtn")?.addEventListener("click", () => {
    SmartShelfUI.closeModal(exitModal);
  });
  document.getElementById("cancelModalBtn")?.addEventListener("click", () => {
    SmartShelfUI.closeModal(exitModal);
  });
  document.getElementById("confirmExitBtn")?.addEventListener("click", () => {
    SmartShelfUI.closeModal(exitModal);
    performExitEmpty();
  });

  // Checkout button
  document.getElementById("checkoutBtn")?.addEventListener("click", performCheckout);

  // Initialize session
  initCustomerSession();
});
