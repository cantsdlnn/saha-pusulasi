# Mimari

Tarayıcı yalnız API yanıtını gösterir ve kullanıcı onayını gönderir. FastAPI katmanı girdi doğrulaması ve HTTP hata eşlemesi yapar. `domain.py` saf puanlama, mesafe ve öneri kurallarını; `database.py` SQLite şemasını, işlem sınırını ve denetim izini taşır.

Atama sırasında `BEGIN IMMEDIATE` ile yazma sırası alınır. İşin açık olması, sürümün beklenen değerle eşleşmesi, teknisyenin becerisi ve kalan kapasitesi aynı işlem içinde yeniden doğrulanır. Başarılı güncelleme ile audit olayı aynı commit içinde kalır.
