# چک‌لیست شبکه SmartShelf روی Windows

| لایه | تنظیم | انتظار |
|---|---|---|
| میزبان | Windows 10/11 | روشن، برق‌متصل، بدون Sleep |
| سرویس | Uvicorn | `127.0.0.1:8000` فقط Loopback |
| تونل | Tailscale Funnel | HTTPS عمومی و WSS برای WebSocket |
| Frontend | Vercel | `https://shelf-ir.vercel.app` |
| تبلت | Chrome | `/camera/` با مجوز دوربین |
| داده | SQLite | `data/smartshelf.db` محلی |
| تصاویر آپلودی | فایل محلی | `data/uploads/` |
| فروش | Feature safety | `STORE_OPEN=false` تا پایان آزمون |

## دستورات عیب‌یابی

```powershell
ipconfig /all
tailscale status
tailscale funnel status
Test-NetConnection 127.0.0.1 -Port 8000
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

پورت 8000 نباید روی اینترنت یا WAN باز شود. Funnel از اتصال خروجی Tailscale استفاده می‌کند؛ Port Forwarding روی روتر لازم نیست.
