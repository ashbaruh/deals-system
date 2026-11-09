"""Create a realistic mock feed + 30 days of price history, for local testing only."""
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.core import History, Product  # noqa: E402

random.seed(7)
ITEMS = [
    ("Gel Nail Polish Set 24 Colors UV LED", 18, "nails"),
    ("Professional UV LED Nail Lamp 48W", 22, "nails"),
    ("Nail Art Stamping Kit Stainless", 9, "nails"),
    ("Manual Coffee Grinder Ceramic Burr", 27, "coffee"),
    ("Electric Milk Frother Handheld Rechargeable", 14, "coffee"),
    ("Espresso Tamper 51mm Stainless Steel", 12, "coffee"),
    ("Moka Pot 6 Cup Aluminium Stovetop", 19, "coffee"),
    ("Women Oversized Hoodie Fleece Winter", 21, "fashion"),
    ("Men Waterproof Jacket Lightweight Hooded", 34, "fashion"),
    ("Casual Sneakers Breathable Running", 29, "fashion"),
    ("Bluetooth 5.3 Earbuds ANC Wireless", 31, "audio"),
    ("Hi-Fi USB DAC Headphone Amplifier", 45, "audio"),
    ("Portable Bluetooth Speaker 20W Waterproof", 26, "audio"),
    ("Over-Ear Headphones Hi-Res Studio", 39, "audio"),
    ("Smart Plug WiFi Energy Monitor 4 Pack", 17, "home"),
    ("LED Strip Lights RGB 10m App Control", 15, "home"),
    ("Kitchen Drawer Organizer Bamboo Set", 13, "home"),
    ("Cordless Handheld Vacuum Car Home", 38, "home"),
]


def main():
    root = Path(__file__).resolve().parent
    today = date.today()
    hist = History()
    rows = []
    for i in range(240):
        name, base, _ = random.choice(ITEMS)
        pid = f"1005{i:08d}"
        normal = round(base * random.uniform(0.85, 1.25), 2)
        # ~15% of items are on a real, deep discount today
        deal = random.random() < 0.15
        price = round(normal * (random.uniform(0.35, 0.62) if deal else random.uniform(0.9, 1.05)), 2)
        old = round(normal * random.uniform(1.6, 2.2), 2)      # inflated "original" price, typical
        rating = round(random.uniform(4.4, 4.95), 1)
        orders = random.choice([120, 380, 650, 1400, 3200, 8800, 21000])
        rows.append({"id": pid, "name": f"{name} #{i}", "price": price, "oldprice": old,
                     "url": f"https://example.com/aff/{pid}", "picture": f"https://picsum.photos/seed/{pid}/400",
                     "rating": rating, "orders": orders, "ships_to": "IL|ES|US"})
        past = [Product(pid=f"aliexpress:{pid}", store="aliexpress", title=name,
                        price_usd=round(normal * random.uniform(0.95, 1.05), 2),
                        old_price_usd=old, url="", image="")]
        for d in range(30, 0, -1):
            hist.record(past, (today - timedelta(days=d)).isoformat())
    with open(root / "feed.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("mock feed:", len(rows), "items; history seeded for 30 days")


if __name__ == "__main__":
    main()
