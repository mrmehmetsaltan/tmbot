# Togg T10F – Panoramik Cam Tavan Takip Botu

`configurator.togg.com.tr` üzerinde **T10F V2 RWD Uzun Menzil** için seçtiğiniz
kombinasyonda (Kış Paketi + Mardin + 19" jant + siyah vegan deri koltuk +
Meridian Premium Ses) **Panoramik Cam Tavan** seçilebilir hale geldiği anda
Telegram'dan haber veren bot.

> **Sunucunuz / Docker bilginiz yok mu?** Botu ücretsiz olarak GitHub Actions üzerinde
> çalıştırabilirsiniz, hiç komut satırı gerekmez → **[KURULUM-GITHUB.md](KURULUM-GITHUB.md)**

## Nasıl çalışıyor?

Configurator sayfası tarayıcıda açıldığında arka planda şu API'yi çağırıyor:

```
GET https://bff.dfs.togg.cloud/smart-device-products/TUR/getSmartDeviceProducts/v1?collectionHandle=t10f-configurator
```

Yanıtta her model için bir **`variants`** listesi var. Her varyant, sipariş
verilebilen geçerli bir opsiyon kombinasyonu (renk + koltuk + paketler + cam
tavan + ...). Sitedeki bir kutucuğun "seçilebilir" olması, mevcut seçimlerinizle
birlikte o opsiyonu içeren bir varyantın bu listede bulunması demek.

25.09.2026 itibarıyla V2 için 34 varyant var ve
`Mardin + siyah koltuk + Meridian VAR + Cam tavan VAR` kombinasyonu listede **yok**
(çakışma tam olarak bu). Bot her 5 dakikada bir listeyi çekip bu kombinasyonun
eklenip eklenmediğine bakıyor; tarayıcı/Playwright'a ihtiyaç yok, hafif ve hızlı.

Bildirim mantığı:

* Kombinasyon **ilk kez** seçilebilir olduğunda 🚨 mesaj gelir (bir kez).
* Tekrar kaybolursa bilgi mesajı, yeniden gelirse yine 🚨 mesaj.
* API 3 kez üst üste cevap vermezse bir uyarı, düzelince bir "düzeldi" mesajı.
* İsteğe bağlı: `REMIND_EVERY_HOURS` ile açıkken periyodik hatırlatma.

Komutlar: `/status` (son kontrol), `/check` (hemen kontrol), `/variants`
(base seçimlerinizle şu an sipariş verilebilen kombinasyonlar), `/help`.
Bot yalnızca `.env`'deki `TELEGRAM_CHAT_ID`'ye cevap verir.

## Dosyalar

| Dosya | Açıklama |
|---|---|
| `togg_checker.py` | API çağrısı + varyant eşleştirme mantığı |
| `bot.py` | Telegram botu, zamanlayıcı, komutlar, durum dosyası (VPS/Docker için) |
| `check_once.py` + `.github/workflows/check.yml` | GitHub Actions ile tek seferlik kontrol (sunucusuz) |
| `KURULUM-GITHUB.md` | GitHub Actions kurulum rehberi, adım adım |
| `.env.example` | Ayar şablonu – kopyalayıp `.env` yapın |
| `Dockerfile`, `docker-compose.yml` | Docker ile çalıştırma |
| `togg-bot.service` | Docker'sız, systemd ile çalıştırma |
| `tests/test_checker.py` | Eşleştirme mantığı testleri (gerçek varyant verisinden fixture) |

---

## 1. Telegram botu oluşturma (BotFather)

1. Telegram'da **@BotFather**'ı açın → `/newbot`.
2. Bir isim (`Togg Cam Tavan`) ve kullanıcı adı (`togg_cam_tavan_bot` gibi, `bot` ile bitmeli) verin.
3. BotFather size **token** verir: `123456789:AAxxxxxxxx...` → `.env` → `TELEGRAM_BOT_TOKEN`.
4. Yeni botunuza gidip **Start**'a basın (bot size mesaj gönderebilsin diye şart).

## 2. Chat ID'nizi bulma

En pratik yol: Telegram'da **@userinfobot**'a `/start` yazın; size `Id: 123456789`
döner. Bu sayı `.env` → `TELEGRAM_CHAT_ID`.

Alternatif: kendi botunuza herhangi bir mesaj attıktan sonra tarayıcıda açın:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

`"chat":{"id":123456789,...}` alanındaki sayı chat ID'nizdir.

## 3. Yapılandırma

```bash
cp .env.example .env
nano .env        # TOKEN ve CHAT_ID'yi girin
```

Diğer ayarlar varsayılan olarak ekran görüntülerinizdeki seçimlerle aynı
(Kış Paketi VAR, Akıllı Destek YOK, Mardin, 19", siyah koltuk, Meridian VAR).
Renk/koltuk değiştirmek isterseniz `.env`'deki `TARGET_*` değerlerini düzenleyin;
geçerli değerler dosyanın içinde yorum olarak yazılı.

---

## 4. Çalıştırma – Seçenek A: Docker (önerilen, herhangi bir VPS)

Gereksinim: Docker + Docker Compose (Ubuntu için `sudo apt install docker.io docker-compose-v2`).

```bash
git clone <repo>  # veya klasörü sunucuya kopyalayın (scp / rsync)
cd togg-cam-tavan-bot
cp .env.example .env && nano .env

docker compose up -d --build     # başlat
docker compose logs -f           # logları izle (Ctrl+C ile çıkılır, bot çalışmaya devam eder)
```

Bot açılınca Telegram'a "🤖 Bot başlatıldı" mesajı gelir; 5 sn sonra ilk kontrol
yapılır. `/status` yazarak doğrulayın.

Güncelleme / yeniden başlatma:

```bash
docker compose down && docker compose up -d --build
```

Durum (`data/state.json`) volume'de tutulduğu için yeniden başlatmada
"zaten bildirildi" bilgisi kaybolmaz.

## 5. Çalıştırma – Seçenek B: Docker'sız (systemd)

```bash
sudo useradd -r -s /usr/sbin/nologin togg
sudo mkdir -p /opt/togg-cam-tavan-bot && sudo cp -r . /opt/togg-cam-tavan-bot
cd /opt/togg-cam-tavan-bot
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env && sudo nano .env
sudo chown -R togg:togg /opt/togg-cam-tavan-bot

sudo cp togg-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now togg-bot
sudo journalctl -u togg-bot -f      # loglar
```

## 6. Çalıştırma – Seçenek C: Yerel makinede hızlı deneme

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
python bot.py
```

(Mac uyuyunca bot durur; kalıcı takip için A veya B'yi kullanın.)

## 7. Ücretsiz/ucuz barındırma alternatifleri

* **Railway / Render / Fly.io**: repo'yu bağlayın, servis tipi "Worker/Background"
  seçin, `Dockerfile` otomatik algılanır, ortam değişkenlerini panelden girin.
  Not: Render'ın ücretsiz planı web servisleri için; worker için ücretli plan gerekir.
  Fly.io'da `fly launch --no-deploy` → `fly secrets set TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...` → `fly deploy`.
  Kalıcı disk yoksa `data/state.json` her deploy'da sıfırlanır; bu sadece bildirimin
  bir kez daha gelmesine yol açar, kritik değil.
* **Oracle Cloud Always Free / Hetzner (~4 €/ay)**: küçük bir Ubuntu VM'de Seçenek A.
* **Evdeki Raspberry Pi / NAS**: Docker ile Seçenek A birebir çalışır (arm64 imajı var).

---

## Test

```bash
pip install -r requirements.txt pytest
python -m pytest -q
# veya
python tests/test_checker.py
```

Testler gerçek API'den alınmış varyant kombinasyonlarıyla; "şu an seçilemiyor",
"varyant eklenince seçilebilir", "başka renk tetiklemez", "siyah tavan değeri
önemsiz" senaryolarını doğrular.

## Sorun giderme

* **`API 403 döndü`**: Togg'un CDN'i sunucu IP'sini/UA'yı engelliyor olabilir.
  `togg_checker.py` içindeki `User-Agent`'ı güncel bir tarayıcı UA'sı ile değiştirin;
  hâlâ olmuyorsa Türkiye lokasyonlu bir VPS deneyin.
* **Bot mesaj atmıyor**: Bota Telegram'da **Start** verdiniz mi? `TELEGRAM_CHAT_ID`
  doğru mu? `docker compose logs -f` çıktısına bakın.
* **`'V2' içeren model bulunamadı`**: Togg model adını değiştirmiş; `/variants`
  yerine loglardaki model listesine bakıp `TARGET_MODEL_CONTAINS` değerini güncelleyin.
* **Opsiyon isimleri değişirse** (`Kış Paketi` vb.): `togg_checker.py` başındaki
  `OPT_*` sabitlerini API'deki yeni başlıklarla eşitleyin.

## Notlar

* API herkese açık, kimlik doğrulama yok; 5 dk'da bir tek istek Togg için
  ihmal edilebilir bir yük. Daha sık sorgulamak (1 dk altı) önerilmez.
* Bot yalnızca "seçilebilirlik" bilgisini verir; sipariş adımı manuel.
