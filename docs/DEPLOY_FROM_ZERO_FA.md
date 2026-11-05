> **توجه — مسیر انتخاب‌شده برای این بسته:** Windows محلی + Tailscale Funnel است. راهنمای اصلی را در [WINDOWS_LOCAL_DEPLOY_FA.md](WINDOWS_LOCAL_DEPLOY_FA.md) دنبال کنید. بخش Railway زیر فقط مستند مسیر جایگزین قبلی است و برای نصب فعلی اجرا نشود.

# راه‌اندازی SmartShelf از صفر — ۱۴۰۵/۰۸/۱۲

## معماری پیشنهادی برای استفاده عمومی

- **Vercel:** فقط رابط وب `https://shelf-ir.vercel.app`، بدون نگهداری فریم دوربین.
- **Railway:** سرویس دائمی FastAPI با آدرس HTTPS اختصاصی Railway و WebSocket امن WSS. در این معماری به Cloudflare Tunnel نیاز نیست.
- **Volume دائمی Railway:** یک Volume در مسیر `/data` برای SQLite و تصاویر آپلودشده. بدون Volume داده‌ها ممکن است پس از دیپلوی از بین بروند.
- **تبلت:** مرورگر Chrome و اتصال WSS به سرور؛ مرورگر باید باز بماند و دسترسی دوربین داشته باشد.

**هشدار:** تا پیش از آزمایش واقعی و ارزیابی دقت شناسایی محصول، `STORE_OPEN=false` باقی بماند. موتور دو مرجعی حضور را تشخیص می‌دهد؛ شناسایی هویت محصول مستقل و هنوز نیازمند اعتبارسنجی است.

## مسیر A — Railway (بدون نیاز به رایانه همیشه‌روشن)

1. در ChatGPT، اپ Railway را متصل کنید تا ساخت سرویس از داخل گفتگو قابل پیگیری باشد؛ یا پروژه را در Railway دستی بسازید.
2. پروژه جدید Railway و یک Service از سورس همین بسته بسازید. **Root Directory** باید ریشه بسته (محل `Dockerfile`) باشد. Builder باید Dockerfile باشد.
3. به سرویس یک **Volume** متصل کنید و **Mount Path** را دقیقاً `/data` قرار دهید. برای جلوگیری از چند نویسنده SQLite، فقط **یک replica و یک worker** اجرا شود.
4. متغیرهای زیر را در بخش Variables سرویس Railway وارد کنید. برای `SECRET_KEY` و `ADMIN_PIN` مقادیر تصادفی جداگانه بسازید و فقط در Secrets/Variables سرویس نگه دارید:

   ```env
   APP_ENV=production
   STORE_OPEN=false
   SECRET_KEY=<unique-strong-random-secret-at-least-32-characters>
   ADMIN_PIN=<unique-admin-passcode-at-least-8-characters>
   TOKEN_TTL_SECONDS=28800
   ENTRY_TOKEN_TTL_SECONDS=30
   DB_URL=sqlite:////data/smartshelf.db
   UPLOAD_DIR=/data/uploads
   FRONTEND_PUBLIC_URL=https://shelf-ir.vercel.app
   ALLOWED_ORIGINS=https://shelf-ir.vercel.app
   TRUST_PROXY=false
   ```

5. در Railway یک **Public Domain** HTTPS برای سرویس فعال کنید. این آدرس معمولاً از نوع `https://<name>.up.railway.app` است. **آن را حدس نزنید**؛ از داشبورد Railway کپی کنید.
6. همان URL واقعی را در متغیر `PUBLIC_BASE_URL` سرویس قرار دهید و Redeploy کنید. Railway با این URL به‌طور معمول WSS را نیز پشتیبانی می‌کند.
7. روی رایانه توسعه، از ریشه بسته اجرا کنید:

   ```bash
   python scripts/set_frontend_backend.py https://YOUR-REAL-BACKEND.up.railway.app
   python scripts/verify_public_backend.py https://YOUR-REAL-BACKEND.up.railway.app
   ```

8. **فقط پوشه `frontend/`** را ابتدا به Preview پروژه Vercel `shelf` بفرستید. پس از تأیید `/admin/`, `/camera/`, `/presence` و اتصال API/WSS، Preview را به Production ارتقا دهید. آدرس نهایی فرانت‌اند `https://shelf-ir.vercel.app` می‌ماند.
9. در پنل مدیریت با PIN واقعی وارد شوید، کد جفت‌سازی بسازید و تبلت را به `/camera/` متصل کنید. در تب تشخیص، برای هر Zone تصاویر «پُر» و «خالی» را از **زاویه ثابت** کالیبره کنید.
10. در حالت بسته، نتیجه PRESENT/ABSENT/UNKNOWN و رویدادهای ثبت‌شده را آزمایش کنید. هیچ رویدادی نباید فاکتور یا سبد واقعی ایجاد کند. سپس با داده‌های واقعی و تأیید انسانی درباره فعال‌سازی فروش تصمیم بگیرید.

### نکات امنیت و نگهداری Railway

- **Railway و Vercel سرویس‌های جدا هستند.** روی Vercel نمی‌توان WebSocket دائمی پردازش تصویر اجرا کرد.
- دیتابیس SQLite فقط روی Volume دائمی و فقط با یک نمونه برنامه استفاده شود. قبل از هر تغییر بزرگ بکاپ Volume/SQLite تهیه کنید.
- تصاویر آپلودشده باید در `/data/uploads` بمانند؛ API آنها را از `/static/uploads/...` سرو می‌کند.
- **PIN و SECRET_KEY را در کد، فایل ZIP یا `frontend/config.js` قرار ندهید.** `config.js` فقط آدرس عمومی بک‌اند را دارد.
- تنظیمات `TRUST_PROXY=false` پیش‌فرض محافظه‌کارانه است؛ قبل از فعال‌کردن اعتماد به IP هدرهای پروکسی، شبکه و زنجیره پروکسی باید بررسی شود.
- استقرار اولیه را روی یک سرویس جدا/Preview انجام دهید. هرگز داده‌های فروشگاه فعال را با دیتابیس آزمایشی جایگزین نکنید.

## مسیر B — رایانه Windows + Tailscale Funnel

اگر بک‌اند باید حتماً روی رایانه فروشگاه اجرا شود، نیاز به یک رایانه **همیشه‌روشن** با دسترسی اینترنت پایدار دارید. برای این مسیر:

1. در Windows و در ریشه بسته، PowerShell را باز کنید:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_backend.ps1
   ```
2. فایل خصوصی `.env` ساخته می‌شود؛ PIN را فقط نزد خودتان نگه دارید.
3. Tailscale را نصب کنید و به حساب خود وارد شوید. با دستور `tailscale funnel --bg 8000` قابلیت Funnel را به‌صورت پایدار برای بک‌اند روی پورت ۸۰۰۰ فعال کنید؛ وضعیت را با `tailscale funnel status` ببینید. راه‌اندازی Funnel نیازمند تأیید در حساب Tailscale است.
4. آدرس HTTPS ثابت Funnel را در `.env` به عنوان `PUBLIC_BASE_URL` ثبت کنید؛ `FRONTEND_PUBLIC_URL` و `ALLOWED_ORIGINS` را طبق نمونه حفظ کنید.
5. بک‌اند را با `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` اجرا کنید و Funnel را به آن متصل کنید.
6. با `scripts/set_frontend_backend.py` آدرس عمومی بک‌اند را در فرانت‌اند تنظیم و ابتدا Vercel Preview را تست کنید.

در بسته منتخب Windows Local از Cloudflare Quick Tunnel استفاده نمی‌شود؛ تنها تونل مورد استفاده Tailscale Funnel است.

## مشکلات رفع‌شده در این بسته

- فایل‌های `.env.example`، `.gitignore` و README که در ZIP قبلی جا افتاده بودند اضافه شدند.
- API آزمایش کالیبراسیون از Vercel به بک‌اند HTTPS هدایت می‌شود.
- تصاویر آپلودشده روی Volume دائمی ذخیره و از بک‌اند بارگذاری می‌شوند.
- در حالت `STORE_OPEN=false` رویدادهای حسگر هرگز سبد خرید را تغییر نمی‌دهند.
- انقضای QR ورود از انقضای نشست مدیر جدا و ۳۰ ثانیه شد.
- اگر ONNX در دسترس نباشد، سیستم به جای ساخت embedding تصادفی، شناسایی هویت محصول را غیرفعال می‌کند.
- شناسه رویدادهای حسگر پس از ری‌استارت با اجرای قبلی تداخل پیدا نمی‌کند.

## معیار قبولی نهایی

- `GET /api/health` → HTTP 200 و JSON `status=ok`.
- درخواست بدون توکن به `/api/admin/auth/check` و `/api/presence` → HTTP 401.
- از مبدأ Vercel هدر `Access-Control-Allow-Origin` برابر `https://shelf-ir.vercel.app` باشد.
- اتصال تبلت به `/ws/camera` با توکن معتبر برقرار شود؛ بدون توکن قطع شود.
- کالیبراسیون با دو مرجع و ثبت آن پس از ری‌استارت پایدار بماند.
- در حالت فروشگاه بسته، برداشت آزمایشی هیچ تغییری در سبد خرید/فاکتور ایجاد نکند.
- تست واقعی با زاویه و نور محیط اجرا و موارد UNKNOWN بررسی شود.
