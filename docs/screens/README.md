# SMARTSHELF Interface Architecture & Screens (Phase 5)

## 1. Landing Portal (`/`)
- Portal interface coordinating Admin, Customer, Camera, QR Entrance, Demo Simulator, and Styleguide.
- Implements theme switching (Light Ivory/Cream vs Dark Plum) and backend server auto-discovery.

## 2. Customer Shopping App (`/customer/`)
- Mobile-first interface with live WebSocket updates.
- Welcome card with delicate entry glide (`anim-cart-add`).
- Real-time product cards with Persian numbers, Toman pricing, and quantity counters.
- Sticky bottom action bar with grand total counter bump and checkout button.
- Bottom sheet with drag handle and swipe-to-close for reviewing itemized basket.
- Perforated ticket receipt (`ticket-receipt`) with zigzag serrated teeth, Jalali date, line items, and invoice number.
- Toast notifications on item pick/return with mobile vibration (`navigator.vibrate`).
- Network disconnect alert banner with auto-reconnect countdown.

## 3. Admin Dashboard (`/admin/`)
- Responsive desktop (collapsible sidebar) and mobile (bottom tab bar).
- KPI metric cards (today's sessions, active customer, invoices count, total revenue in Toman).
- Real-time 3-slot shelf presence monitoring and device statuses with live pulse dots.
- Dynamic entry QR generator with countdown validity progress.
- Customer session management with duration tracking and associated invoices.
- Invoice inspector opening the perforated ticket receipt.
- Product catalog with image upload, SKU, and slot assignment.
- Camera calibration & ROI sensitive zones.
- Real-time streaming log of shelf events with chip filters.

## 4. Camera Sensor Kiosk (`/camera/`)
- Tablet-optimized kiosk mode.
- Hardware camera preview and 5 FPS downsampled frame transmission.
- Live HUD displaying device ID, FPS counter, and frames sent counter.
- Screen Wake Lock API integration to prevent display timeout.
- Fullscreen mode toggle.
- Secure 6-digit pairing code authorization.

## 5. Standalone Demo Simulator (`/demo/`)
- 100% in-browser virtual shelf simulation without requiring physical camera or backend.
- 3 virtual slots with sample products from `demo-products.json`.
- Tap product to PICK (with simulated ~1.2s sensor stability delay); tap again to RETURN.
- Identical shopping cart, sticky action bar, and perforated ticket receipt.
- Fixed disclaimer: «شبیه‌ساز نمایشی — بدون دوربین واقعی».
- Live backend detection indicator: «فروشگاه زنده در دسترس است».

## 6. Design System Styleguide (`/styleguide/`)
- Interactive design token catalog, WCAG contrast verification, Dana typography, and 17+ UI components in both themes (Light/Dark) and both directions (RTL/LTR).
