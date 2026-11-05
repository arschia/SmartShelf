# راهنمای استقرار SmartShelf — Windows + Tailscale Funnel

این سند مسیر منتخب فعلی را پوشش می‌دهد. بک‌اند، پردازش تصویر و SQLite روی کامپیوتر Windows فروشگاه اجرا می‌شوند؛ Vercel فقط رابط استاتیک را ارائه می‌کند.

**راهنمای اجرایی کامل:** [WINDOWS_LOCAL_DEPLOY_FA.md](WINDOWS_LOCAL_DEPLOY_FA.md)

## معماری

- Frontend: `https://shelf-ir.vercel.app`
- Backend: FastAPI روی `127.0.0.1:8000`
- Public tunnel: Tailscale Funnel با HTTPS و URL ثابت `*.ts.net`
- Camera: Chrome روی تبلت و اتصال WebSocket احراز هویت‌شده به backend
- Data: SQLite و تصاویر آپلودشده روی دیسک محلی Windows

## نصب و اجرا

1. ZIP را در `C:\SmartShelf` استخراج کنید.
2. `INSTALL-SMARTSHELF.bat` را اجرا کنید.
3. Tailscale را از [صفحه رسمی Windows](https://tailscale.com/download/windows/) نصب و وارد حساب شوید.
4. `START-SMARTSHELF.bat` را اجرا کنید.
5. از PowerShell Administrator، `ENABLE-FUNNEL.bat` را اجرا کنید و مجوزهای Funnel/HTTPS را در مرورگر تأیید کنید.
6. پس از نوشتن URL واقعی در `.env`، backend را متوقف و دوباره اجرا کنید.
7. `REGISTER-AUTOSTART.bat` را اجرا کنید تا backend پس از ورود حساب Windows شروع شود.

از Cloudflare Tunnel، Quick Tunnel یا سرویس‌های واسط انتقال فریم استفاده نمی‌شود. پورت 8000 را روی روتر یا Windows Firewall به اینترنت باز نکنید؛ Uvicorn فقط روی loopback گوش می‌دهد.

## تنظیم Frontend

اسکریپت Funnel مقدار `apiBase` را در `frontend/config.js` محلی می‌نویسد. این فایل به‌صورت خودکار روی Vercel منتشر نمی‌شود. برای اتصال مرورگرها، URL Funnel را از دکمه «تنظیم سرور» در پنل Admin و صفحه Camera وارد کنید؛ یا پس از بررسی Preview، پوشه `frontend/` را به پروژه Vercel `shelf` منتشر کنید.

## امنیت و داده

- `STORE_OPEN=false` باقی می‌ماند.
- محصول اولیه فقط «دلستر هی‌جو هلو» است؛ غیرفعال و با قیمت صفر. دو جایگاه دیگر خالی‌اند.
- شناسایی هویت محصول با مدل عمومی MobileNet عمداً غیرفعال است؛ موتور دو‌مرجعی فقط `PRESENT`، `ABSENT` یا `UNKNOWN` را تعیین می‌کند.
- فریم خام دوربین در حافظه پردازش می‌شود و روی دیسک ذخیره نمی‌شود.
- `.env`، PIN، دیتابیس و بکاپ‌ها را منتشر یا ارسال نکنید.
- Funnel آدرس را در اینترنت عمومی قابل دسترس می‌کند؛ احراز هویت سمت برنامه همچنان الزامی است.
- WSS و throughput باید با تبلت واقعی آزمایش شوند؛ ایجاد Funnel به‌تنهایی آزمون WebSocket را تأیید نمی‌کند.

## کنترل وضعیت

```powershell
.\scripts\check_local_backend.ps1
.\.venv\Scripts\python.exe scripts\verify_public_backend.py https://YOUR-DEVICE.YOUR-TAILNET.ts.net
.\scripts\backup_shelf.ps1
```

برای قطع دسترسی عمومی بدون حذف داده‌ها:

```powershell
.\scripts\disable_tailscale_funnel.ps1
```
