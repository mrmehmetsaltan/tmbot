"""
GitHub Actions için tek seferlik kontrol.

Her çalıştırmada:
  1. data/state.json'u okur (önceki durum),
  2. Togg API'sini sorgular,
  3. Cam tavan kombinasyonu YENİ seçilebilir olduysa Telegram'a mesaj atar,
  4. state.json'u günceller (workflow bunu repo'ya commit eder).

Ortam değişkenleri: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (GitHub Secrets)
İsteğe bağlı: TARGET_* (bot.py ile aynı), RUN_MODE=manual → her durumda özet mesaj atar.
"""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import togg_checker as tc

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path(os.getenv("STATE_FILE", "data/state.json"))
MANUAL = os.getenv("RUN_MODE", "scheduled") == "manual"
ERROR_ALERT_AFTER = int(os.getenv("ERROR_ALERT_AFTER", "3"))
NOTIFY_ON_LOST = os.getenv("NOTIFY_ON_LOST", "true").lower() == "true"
TZ = timezone(timedelta(hours=3))

TARGET = tc.Target(
    product_name_contains=os.getenv("TARGET_MODEL_CONTAINS", "V2"),
    base={
        tc.OPT_KIS: os.getenv("TARGET_KIS_PAKETI", "VAR"),
        tc.OPT_ADP: os.getenv("TARGET_AKILLI_DESTEK", "YOK"),
        tc.OPT_RENK: os.getenv("TARGET_RENK", "mardin"),
        tc.OPT_JANT: os.getenv("TARGET_JANT", "19-inch-jant"),
        tc.OPT_KOLTUK: os.getenv("TARGET_KOLTUK", "seats-faux-leather-black"),
        tc.OPT_MERIDIAN: os.getenv("TARGET_MERIDIAN", "VAR"),
    },
)


def now_str() -> str:
    return datetime.now(TZ).strftime("%d.%m.%Y %H:%M:%S")


def send(text: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Telegram hata {r.status_code}: {r.text[:200]}", file=sys.stderr)


def load_state() -> dict:
    base = {"was_available": False, "consecutive_errors": 0, "error_alerted": False,
            "last_check": None, "last_error": None, "checks": 0, "heartbeat_day": None}
    if STATE_FILE.exists():
        try:
            base.update(json.loads(STATE_FILE.read_text()))
        except Exception:  # noqa: BLE001
            pass
    return base


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    state = load_state()
    state["checks"] += 1
    state["last_check"] = now_str()
    # Günde bir kez değişen alan → repo'ya günde en az bir commit gider,
    # böylece GitHub 60 gün hareketsizlik nedeniyle zamanlayıcıyı kapatmaz.
    state["heartbeat_day"] = datetime.now(TZ).strftime("%Y-%m-%d")

    try:
        result = tc.check(TARGET)
    except Exception as e:  # noqa: BLE001
        state["consecutive_errors"] += 1
        state["last_error"] = f"{now_str()} – {e}"
        print(f"HATA: {e}", file=sys.stderr)
        if state["consecutive_errors"] >= ERROR_ALERT_AFTER and not state["error_alerted"]:
            state["error_alerted"] = True
            send(f"⚠️ Togg API'ye {state['consecutive_errors']} kez üst üste ulaşılamadı.\n"
                 f"Son hata: <code>{html.escape(str(e))}</code>")
        if MANUAL:
            send(f"❌ Kontrol başarısız: <code>{html.escape(str(e))}</code>")
        save_state(state)
        return 0  # workflow'u kırmızıya boyamayalım; state commit edilsin

    if state["error_alerted"]:
        send("✅ Togg API tekrar erişilebilir, kontroller normal devam ediyor.")
    state["consecutive_errors"] = 0
    state["error_alerted"] = False
    state["last_error"] = None

    became_available = result.available and not state["was_available"]
    became_lost = (not result.available) and state["was_available"]

    if became_available:
        lines = "\n".join(f"• {html.escape(v.describe())}" for v in result.matching)
        send("🚨🚨 <b>PANORAMİK CAM TAVAN SEÇİLEBİLİR HALE GELDİ!</b> 🚨🚨\n\n"
             f"Model: <b>{html.escape(result.product_name)}</b>\n"
             f"Zaman: {now_str()}\n\nEşleşen varyant(lar):\n{lines}\n\n"
             "👉 https://configurator.togg.com.tr/")
    elif became_lost and NOTIFY_ON_LOST:
        send("ℹ️ Cam tavan kombinasyonu tekrar <b>seçilemez</b> oldu. Takip devam ediyor.")
    elif MANUAL:
        durum = "✅ <b>seçilebilir</b>" if result.available else "⏳ henüz <b>seçilemiyor</b>"
        send(f"🔎 Manuel kontrol ({now_str()})\n"
             f"Model: {html.escape(result.product_name)}\n"
             f"Cam tavan: {durum}\n"
             f"{result.total_variants} varyant tarandı, base seçimle eşleşen: "
             f"{len(result.base_matches)}\n"
             f"Toplam kontrol sayısı: {state['checks']}")

    state["was_available"] = result.available
    save_state(state)
    print(f"Sonuç: available={result.available} "
          f"(toplam {result.total_variants}, base {len(result.base_matches)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
