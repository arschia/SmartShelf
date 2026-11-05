> Historical development note. For current capabilities, read [the project README](../README.md) and [MODEL_CARD.md](MODEL_CARD.md).

# SMARTSHELF - مشخصات مدل‌های هوش مصنوعی محلی (AI Models)

این سند مشخصات، منبع، مجوز و راهنمای مدل‌های هوش مصنوعی مورد استفاده در سامانه SMARTSHELF را طبق مرحله ۷ توصیف می‌کند.

---

## ۱. مدل استخراج ویژگی و شناسایی کالا (Product Recognition / Embedding)

- **نام مدل:** MobileNetV2 (Opset 7)
- **مسیر فایل محلی:** `ai/models/mobilenetv2-7.onnx`
- **منبع رسمی (Source):** [ONNX Model Zoo (Vision Classification)](https://github.com/onnx/models/tree/main/validated/vision/classification/mobilenet)
- **سازنده اصلی:** Google Research / ONNX Model Zoo Authors
- **نوع معماری:** MobileNetV2 Convolutional Neural Network
- **نسخه مدل / اپ‌ست:** MobileNetV2-7 (ONNX Opset 7)
- **مجوز (License):** **Apache License 2.0** (متن‌باز، مجاز برای مصارف تجاری و تحقیقاتی)
- **روش اجرا:** محلی روی پردازنده اصلی (CPU) با استفاده از `onnxruntime`، کاملاً آفلاین و بدون هیچ وابستگی ابری یا اتصال به اینترنت.

### مشخصات ورودی و خروجی مدل

- **ورودی (Input Tensor):**
  - نام: `data`
  - ابعاد: `[1, 3, 224, 224]` (Batch Size=1, Channels=3 RGB, Height=224, Width=224)
  - نوع داده: `float32`
  - پیش‌پردازش: برش مرکزی (Center Crop)، تغییر ابعاد به `224x224`، مقیاس‌گذاری مقادیر پیکسل به `[0.0, 1.0]` و نرمال‌سازی استاندارد ایمیج‌نت:
    - `mean = [0.485, 0.456, 0.406]`
    - `std = [0.229, 0.224, 0.225]`
- **خروجی (Embedding Output):**
  - نام: `mobilenetv20_output_flatten0_reshape0`
  - ابعاد: `[1, 1000]`
  - نوع داده: `float32`
  - بردار ویژگی ۱۰۰۰ بعدی که پس از استخراج با ضریب نرم L2 نرمال‌سازی می‌شود (`v / ||v||`) تا محاسبه شباهت کسینوسی (Cosine Similarity) با ضرب داخلی ساده ماتریسی `np.dot` در کمترین زمان ممکن (زیر ۱۰ میلی‌ثانیه) انجام پذیرد.

---

## ۲. یادداشت در مورد Fine-tuning و آموزش شبکه

ثبت محصول در SMARTSHELF به منزله «آموزش شبکه عصبی» نیست؛ بلکه استخراج بردار تعبیه‌سازی مرجع (Reference Embedding) و ذخیره آن در دیتابیس `smartshelf.db` جدول `product_embeddings` و شاخص ماتریسی رم (In-Memory Index) است.
عملیات Fine-tuning به عنوان کار و امکان توسعه در آینده (Future Work) در نظر گرفته می‌شود.
