"""
Togg configurator kontrol mantığı.

Configurator (configurator.togg.com.tr) arka planda şu uç noktayı çağırır:

    GET https://bff.dfs.togg.cloud/smart-device-products/TUR/getSmartDeviceProducts/v1
        ?collectionHandle=t10f-configurator

Yanıt, her model (T10F V1 / V2 ...) için "variants" listesi içerir. Her varyant,
sipariş verilebilen GEÇERLİ bir opsiyon kombinasyonudur. Sitede bir opsiyonun
"seçilebilir" olması = mevcut seçimlerinizle birlikte o opsiyonu içeren bir
varyantın listede bulunması demektir.

Bu modül, hedef kombinasyonun (Kış Paketi + Mardin + 19" jant + siyah koltuk +
Meridian + PANORAMİK CAM TAVAN) varyant listesinde olup olmadığını kontrol eder.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

log = logging.getLogger("togg.checker")

API_URL = (
    "https://bff.dfs.togg.cloud/smart-device-products/{country}/getSmartDeviceProducts/v1"
)

# Opsiyon başlıkları API'de tam olarak böyle geçiyor (Türkçe karakterli).
OPT_KIS = "Kış Paketi"
OPT_ADP = "Akıllı Destek Paketi"
OPT_RENK = "Renk"
OPT_JANT = "Jant"
OPT_KOLTUK = "Koltuklar"
OPT_CAM = "Panoramik Cam Tavan"
OPT_MERIDIAN = "Meridian Premium Ses Sistemi"
OPT_SIYAH = "Siyah Renkte Tavan ve Yan Aynalar"


@dataclass
class Target:
    """Takip edilen konfigürasyon."""

    product_name_contains: str = "V2"          # "T10F V2 RWD Uzun Menzil"
    collection_handle: str = "t10f-configurator"
    country: str = "TUR"
    # Sabit tutulan seçimler (ekran görüntülerinizdeki seçimler)
    base: dict[str, str] = field(default_factory=lambda: {
        OPT_KIS: "VAR",
        OPT_ADP: "YOK",
        OPT_RENK: "mardin",
        OPT_JANT: "19-inch-jant",
        OPT_KOLTUK: "seats-faux-leather-black",
        OPT_MERIDIAN: "VAR",
    })
    # Seçilebilir hale gelmesini beklediğimiz opsiyon
    watch_option: str = OPT_CAM
    watch_value: str = "VAR"
    # Bu opsiyonlar için herhangi bir değer kabul edilir (örn. siyah tavan)
    ignore_options: tuple[str, ...] = (OPT_SIYAH,)


@dataclass
class Variant:
    id: str
    options: dict[str, str]
    turnkey_price: float | None
    delivery: str | None

    def describe(self) -> str:
        parts = [f"{k}: {v}" for k, v in self.options.items()]
        price = f"{self.turnkey_price:,.0f} ₺".replace(",", ".") if self.turnkey_price else "-"
        return f"{' | '.join(parts)}  →  {price} (teslimat: {self.delivery or '-'})"


@dataclass
class CheckResult:
    available: bool
    product_name: str
    matching: list[Variant]          # hedefle birebir eşleşen varyantlar (cam tavan VAR)
    base_matches: list[Variant]      # cam tavan hariç, base seçimlerle eşleşen varyantlar
    total_variants: int


class ToggAPIError(RuntimeError):
    pass


def fetch_products(target: Target, session: requests.Session | None = None,
                   timeout: int = 30) -> list[dict[str, Any]]:
    s = session or requests.Session()
    url = API_URL.format(country=target.country)
    headers = {
        "Accept": "application/json",
        "Origin": "https://configurator.togg.com.tr",
        "Referer": "https://configurator.togg.com.tr/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
    }
    try:
        r = s.get(url, params={"collectionHandle": target.collection_handle},
                  headers=headers, timeout=timeout)
    except requests.RequestException as e:  # ağ hatası
        raise ToggAPIError(f"Ağ hatası: {e}") from e
    if r.status_code != 200:
        raise ToggAPIError(f"API {r.status_code} döndü: {r.text[:200]}")
    try:
        data = r.json()
    except ValueError as e:
        raise ToggAPIError("API geçersiz JSON döndü") from e
    products = data.get("products")
    if not isinstance(products, list):
        raise ToggAPIError("API yanıtında 'products' yok")
    return products


def parse_variants(product: dict[str, Any]) -> list[Variant]:
    """Varyantların opsiyon id'lerini okunabilir başlık/değer çiftlerine çevirir."""
    opt_title: dict[str, str] = {}
    val_name: dict[str, str] = {}
    for opt in product.get("options", []):
        opt_title[opt["id"]] = opt.get("title", opt["id"])
        for v in opt.get("values", []) or []:
            val_name[v["id"]] = v.get("value", v["id"])

    out: list[Variant] = []
    for v in product.get("variants", []):
        opts = {}
        for o in v.get("options", []) or []:
            opts[opt_title.get(o.get("id"), o.get("id"))] = val_name.get(
                o.get("value_id"), o.get("value_id"))
        out.append(Variant(
            id=v.get("id", "?"),
            options=opts,
            turnkey_price=v.get("turnkey_price"),
            delivery=v.get("estimated_delivery_date_text"),
        ))
    return out


def _matches(variant: Variant, wanted: dict[str, str]) -> bool:
    for k, val in wanted.items():
        if variant.options.get(k) != val:
            return False
    return True


def evaluate(products: list[dict[str, Any]], target: Target) -> CheckResult:
    product = next(
        (p for p in products if target.product_name_contains in p.get("name", "")), None)
    if product is None:
        names = ", ".join(p.get("name", "?") for p in products)
        raise ToggAPIError(
            f"'{target.product_name_contains}' içeren model bulunamadı. Modeller: {names}")

    variants = parse_variants(product)
    base_matches = [v for v in variants if _matches(v, target.base)]
    full = dict(target.base)
    full[target.watch_option] = target.watch_value
    matching = [v for v in variants if _matches(v, full)]

    return CheckResult(
        available=len(matching) > 0,
        product_name=product.get("name", "?"),
        matching=matching,
        base_matches=base_matches,
        total_variants=len(variants),
    )


def check(target: Target, session: requests.Session | None = None) -> CheckResult:
    products = fetch_products(target, session=session)
    result = evaluate(products, target)
    log.info("Kontrol: %s | toplam %d varyant | base eşleşme %d | hedef eşleşme %d",
             result.product_name, result.total_variants,
             len(result.base_matches), len(result.matching))
    return result
