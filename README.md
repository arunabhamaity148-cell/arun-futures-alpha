# ARUN — CoinDCX Futures সিগন্যাল বট (সম্পূর্ণ বাংলা গাইড)

> **সতর্কবাণী:** এটি একটি **সিগন্যাল-অনলি বট**। এটি কখনো নিজে কোনো অর্ডার প্লেস করে না।
> সব সিগন্যাল টেলিগ্রামে পাঠানো হয়, অপারেটর ম্যানুয়ালি CoinDCX-এ ট্রেড করে।
> **CoinDCX = এক্সিকিউশন ট্রুথ।** বাইরের এক্সচেঞ্জ = শুধু তথ্যের উৎস।
> যদি CoinDCX আর বাইরের ডেটা আলাদা হয় → **NO TRADE**।

---

## সূচি

1. [বট কী এবং কেন](#1-বট-কী-এবং-কেন)
2. [ইনস্টল ও রান](#2-ইনস্টল-ও-রান)
3. [ফাইল স্ট্রাকচার — প্রতিটি ফাইলের কাজ](#3-ফাইল-স্ট্রাকচার--প্রতিটি-ফাইলের-কাজ)
4. [সিগন্যাল ইঞ্জিন কীভাবে কাজ করে](#4-সিগন্যাল-ইঞ্জিন-কীভাবে-কাজ-করে)
5. [৫টি অ্যালফা স্ট্র্যাটেজি (S1–S5)](#5-৫টি-অ্যালফা-স্ট্র্যাটেজি-s1s5)
6. [৫টি ভেটো (V1–V5)](#6-৫টি-ভেটো-v1v5)
7. [রিস্ক গেট](#7-রিস্ক-গেট)
8. [NewsGuard](#8-newsguard)
9. [টেলিগ্রাম কমান্ড](#9-টেলিগ্রাম-কমান্ড)
10. [সিগন্যাল কেমন দেখতে](#10-সিগন্যাল-কেমন-দেখতে)
11. [NO TRADE শর্তসমূহ](#11-no-trade-শর্তসমূহ)
12. [সেফটি ল্যাচ](#12-সেফটি-ল্যাচ)
13. [টপ ১০ পেয়ার](#13-টপ-১০-পেয়ার)
14. [পারফরম্যান্স ও র্যাম](#14-পারফরম্যান্স-ও-র্যাম)
15. [সমস্যা সমাধান (Troubleshooting)](#15-সমস্যা-সমাধান-troubleshooting)
16. [পরিচিত সীমাবদ্ধতা (NOT VERIFIED)](#16-পরিচিত-সীমাবদ্ধতা-not-verified)

---

## 1. বট কী এবং কেন

**ARUN** একটি CoinDCX Futures-এর জন্য প্রোডাকশন-গ্রেড পাইথন সিগন্যাল বট।
এটি টেলিগ্রামে LONG/SHORT সিগন্যাল পাঠায় ম্যানুয়াল এক্সিকিউশনের জন্য।

**বটটি যা করে না:**
- ❌ অটো-ট্রেড করে না (কোনো অর্ডার প্লেস করে না)
- ❌ RSI/MACD/EMA ক্রসওভার ব্যবহার করে না (এগুলো crowded)
- ❌ LLM/AI দিয়ে প্রেডিক্ট করে না
- ❌ ব্যাকটেস্ট সংখ্যা বানায় না
- ❌ লাভের প্রতিশ্রুতি দেয় না

**বটটি যা করে:**
- ✅ রিয়েল মার্কেট মাইক্রোস্ট্রাকচার থেকে অ্যালফা বের করে
- ✅ CoinDCX-এর সাথে বাইরের এক্সচেঞ্জের মিল যাচাই করে
- ✅ ৫টি ভেটো দিয়ে সিগন্যাল ফিল্টার করে
- ✅ রিস্ক গেট দিয়ে সাইজ নির্ধারণ করে
- ✅ সব সিদ্ধান্ত অডিট করে
- ✅ **Fail-closed:** নিশ্চিত না হলে NO TRADE

**মূল নীতি:** দুর্বল সিগন্যালের চেয়ে NO TRADE ভালো।

---

## 2. ইনস্টল ও রান

```bash
# ১. ZIP এক্সট্রাক্ট করো
unzip ARUN_COINDCX_FUTURES_SIGNAL_BOT_FINAL.zip
cd ARUN_SIGNAL_BOT

# ২. ভার্চুয়াল এনভায়রনমেন্ট তৈরি
python3 -m venv .venv
source .venv/bin/activate

# ৩. ডিপেন্ডেন্সি ইনস্টল
pip install -r requirements.txt

# ৪. .env ফাইল তৈরি
cp .env.example .env
# .env ফাইল এডিট করে টেলিগ্রাম টোকেন ও chat_id বসাও

# ৫. টেস্ট রান
pip install -r requirements-dev.txt
pytest tests/

# ৬. বট চালু
python3 main.py
```

**.env ফাইলে যা বসাবে:**
```
ARUN_PAPER_MODE=true
ARUN_TELEGRAM_BOT_TOKEN=তোমার_বট_টোকেন
ARUN_TELEGRAM_CHAT_ID=তোমার_চ্যাট_আইডি
ARUN_OPERATOR_WHITELIST=তোমার_টেলিগ্রাম_ইউজার_আইডি
```

---

## 3. ফাইল স্ট্রাক্চার — প্রতিটি ফাইলের কাজ

```
ARUN_SIGNAL_BOT/
├── main.py                    ← এন্ট্রি পয়েন্ট (python main.py)
├── trader_arun/
│   ├── app.py                 ← মেইন অ্যাপ্লিকেশন (সব কম্পোনেন্ট একসাথে চালায়)
│   ├── __init__.py
│   │
│   ├── core/                  ← বেসিক ইউটিলিটি
│   │   ├── config.py          ← কনফিগারেশন লোড (env vars থেকে)
│   │   ├── logger.py          ← স্ট্রাকচার্ড JSON লগিং (সিক্রেট রিড্যাক্ট করে)
│   │   ├── types.py           ← সব ডেটা ক্লাস (Signal, Ticker, OrderBook ইত্যাদি)
│   │   ├── ringbuffer.py      ← বাউন্ডেড রিং বাফার (RAM সীমিত রাখে)
│   │   ├── rolling.py         ← O(1) রোলিং স্ট্যাটিস্টিক্স (mean, variance, z-score)
│   │   ├── circuit_breaker.py ← সার্কিট ব্রেকার + রেট লিমিটার + ব্যাকঅফ
│   │   ├── exceptions.py      ← কাস্টম এক্সেপশন
│   │   └── time_utils.py      ← টাইমস্ট্যাম্প হেল্পার
│   │
│   ├── data/                  ← ডেটা প্রোভাইডার (সব রিয়েল API)
│   │   ├── base.py            ← প্রোভাইডার বেস ক্লাস (circuit breaker সহ)
│   │   ├── coindcx.py         ← CoinDCX (execution truth — সবচেয়ে গুরুত্বপূর্ণ)
│   │   ├── hyperliquid.py     ← Hyperliquid (no-key, OI/funding/candles)
│   │   ├── kraken.py          ← Kraken (spot anchor)
│   │   ├── binance.py         ← Binance Futures (fallback)
│   │   ├── bybit.py           ← Bybit v5 (SUI/SOL-এর জন্য primary)
│   │   ├── coinglass.py       ← CoinGlass (liquidations)
│   │   ├── gdelt.py           ← GDELT (ফ্রি নিউজ)
│   │   ├── fred.py            ← FRED (ম্যাক্রো ডেটা)
│   │   ├── tokenunlocks.py    ← TokenUnlocks (আনলক ক্যালেন্ডার)
│   │   ├── manager.py         ← সব প্রোভাইডার অর্কেস্ট্রেট করে
│   │   ├── mismatch.py        ← CoinDCX mismatch স্কোর ইঞ্জিন
│   │   └── leadlag.py         ← ক্রস-এক্সচেঞ্জ lead/lag বিশ্লেষণ
│   │
│   ├── microstructure/        ← মাইক্রোস্ট্রাকচার অ্যানালাইসার
│   │   ├── cvd.py             ← Cumulative Volume Delta (buy vs sell pressure)
│   │   ├── obi.py             ← Order Book Imbalance
│   │   ├── absorption.py      ← Absorption ডিটেক্টর (price stable + heavy flow)
│   │   ├── trade_clusters.py  ← ট্রেড বার্স্ট ডিটেক্টর
│   │   └── price_impact.py    ← স্কয়ার-রুট ইম্প্যাক্ট মডেল
│   │
│   ├── derivatives/           ← ডেরিভেটিভস অ্যানালাইসার
│   │   ├── funding.py         ← ফান্ডিং রেট z-score
│   │   ├── open_interest.py   ← OI ইম্পালস ডিটেক্টর
│   │   ├── liquidations.py    ← লিকুইডেশন ক্যাসকেড ইনডেক্স
│   │   └── basis.py           ← পার্প vs স্পট বেসিস z-score
│   │
│   ├── alpha/                 ← ৫টি অ্যালফা স্ট্র্যাটেজি
│   │   ├── base.py            ← বেস ক্লাস
│   │   ├── s1_cascade.py      ← S1: লিকুইডেশন-ক্যাসকেড এক্সহশন
│   │   ├── s2_leadlag.py      ← S2: ক্রস-এক্সচেঞ্জ lead/lag
│   │   ├── s3_funding_oi.py   ← S3: ফান্ডিং/OI ক্রাউডিং আনওয়াইন্ড
│   │   ├── s4_absorption.py   ← S4: অর্ডার-বুক অ্যাবজর্পশন/CVD
│   │   ├── s5_basis.py        ← S5: পার্প-বেসিস কনভার্জেন্স
│   │   └── engine.py          ← সব স্ট্র্যাটেজি চালিয়ে সেরা বেছে নেয়
│   │
│   ├── regime/                ← মার্কেট রেজিম ক্লাসিফায়ার
│   │   └── classifier.py      ← TREND_UP/DOWN, RANGE, LOW_VOL, HIGH_VOL ইত্যাদি
│   │
│   ├── institutional/         ← ইনস্টিটিউশনাল ফুটপ্রিন্ট
│   │   └── footprint.py       ← "large/informed participant activity proxy" স্কোর
│   │
│   ├── vetoes/                ← ৫টি ভেটো ইঞ্জিন
│   │   ├── base.py
│   │   ├── v1_cross_exch.py   ← V1: ক্রস-এক্সচেঞ্জ কন্ট্রাডিকশন
│   │   ├── v2_oi_funding.py   ← V2: OI/ফান্ডিং কন্ট্রাডিকশন
│   │   ├── v3_liquidity_vacuum.py ← V3: লিকুইডিটি ভ্যাকুয়াম
│   │   ├── v4_liq_exhaustion.py   ← V4: অসম্পূর্ণ ক্যাসকেড
│   │   ├── v5_macro_news.py   ← V5: ম্যাক্রো/নিউজ কন্ট্রাডিকশন
│   │   └── engine.py          ← সব ভেটো চালায়
│   │
│   ├── risk/                  ← রিস্ক ম্যানেজমেন্ট
│   │   ├── gate.py            ← RISK_SCORE (0-100) → TRADE/REDUCED/WATCH/NO_TRADE
│   │   ├── sizing.py          ← পজিশন সাইজ (leverage cap, book depth cap)
│   │   └── sltp.py            ← SL/TP বিল্ডার (ATR-based, R:R ≥ 1.5)
│   │
│   ├── portfolio/             ← পোর্টফোলিও ক্রাউডিং
│   │   └── crowding.py        ← BTC/ETH beta, PCA concentration
│   │
│   ├── newsguard/             ← নিউজ গার্ড
│   │   └── engine.py          ← ALLOW/REDUCE/BLOCK (কখনো BUY/SELL নয়)
│   │
│   ├── signals/               ← সিগন্যাল জেনারেশন
│   │   ├── generator.py       ← সব ইঞ্জিন একসাথে চালিয়ে সিগন্যাল বানায়
│   │   ├── publisher.py       ← টেলিগ্রামে সিগন্যাল পাঠায়
│   │   └── audit.py           ← সব সিদ্ধান্ত অডিট করে রাখে
│   │
│   ├── ops/                   ← অপারেশনস
│   │   ├── storage.py         ← SQLite WAL স্টোরেজ
│   │   ├── safety.py          ← ৮টি সেফটি ল্যাচ
│   │   ├── operator.py        ← টেলিগ্রাম কমান্ড হ্যান্ডলার
│   │   ├── health.py          ← RSS/CPU/event-loop lag মনিটর
│   │   └── shutdown.py        ← গ্রেসফুল শাটডাউন
│   │
│   └── backtest/              ← ব্যাকটেস্ট ফ্রেমওয়ার্ক
│       ├── engine.py          ← walk-forward + bootstrap CI
│       ├── costs.py           ← ফি/স্লিপেজ/ফান্ডিং কস্ট মডেল
│       └── metrics.py         ← Sharpe/Sortino/Deflated Sharpe
│
├── tests/                     ← ১৫১টি টেস্ট (সব পাস)
├── .env.example               ← কনফিগ টেমপ্লেট
├── requirements.txt           ← প্রোডাকশন ডিপেন্ডেন্সি
├── requirements-dev.txt       ← ডেভ ডিপেন্ডেন্সি (pytest)
├── README.md                  ← এই ফাইল
├── ARCHITECTURE.md            ← আর্কিটেকচার ডিটেইল
├── CONFIG.md                  ← কনফিগ রেফারেন্স
├── ROOT_CAUSE_REPORT.md       ← ডিজাইন সিদ্ধান্তের কারণ
├── TEST_RESULTS.md            ← টেস্ট ফলাফল
├── RUNTIME_VERIFICATION.md    ← রানটাইম ভেরিফিকেশন
├── PRODUCTION_READINESS.md    ← প্রোডাকশন রেডিনেস
└── CHANGELOG.md               ← পরিবর্তন লগ
```

---

## 4. সিগন্যাল ইঞ্জিন কীভাবে কাজ করে

সিগন্যাল তৈরি হওয়ার সম্পূর্ণ পাইপলাইন (১৪ ধাপ):

```
DATA → QUALITY → MISMATCH → REGIME → ALPHA → FOOTPRINT
    → VETO → NEWS → PORTFOLIO → RISK → SIZING → SL/TP → SIGNAL → TELEGRAM
```

### ধাপ ১: ডেটা সংগ্রহ (DATA)
প্রতি ৩০ সেকেন্ডে বট ১০টি পেয়ারের জন্য সমান্তরালভাবে ডেটা আনে:
- **CoinDCX** (execution truth): ticker, orderbook, candles, trades
- **Hyperliquid**: mid, OI, funding, candles
- **Kraken**: spot ticker, orderbook
- **Binance/Bybit**: futures ticker, OI, funding
- **CoinGlass**: liquidations
- **GDELT**: নিউজ (৫ মিনিট পরপর)

### ধাপ ২: কোয়ালিটি গেট (QUALITY)
প্রতিটি ডেটা যাচাই হয়:
- ফ্রেশনেস (কত সেকেন্ড আগের?)
- NaN/শূন্য দাম?
- স্প্রেড অস্বাভাবিক বড়? (>৫০০০ bps)
- bid > ask? (অসম্ভব)

কোনো ডেটা স্টেল বা অবৈধ → **NO TRADE**।

### ধাপ ৩: MISMATCH স্কোর
CoinDCX আর বাইরের এক্সচেঞ্জের মধ্যে পার্থক্য মাপা হয়:
- প্রাইস ডেভিয়েশন (CoinDCX vs বাইরের মিড)
- কোরিলেশন (১৫ মিনিট রিটার্ন)
- স্প্রেড ডাইভার্জেন্স
- ভলাটিলিটি ডাইভার্জেন্স
- বুক ডেপথ পার্থক্য

স্কোর ০-১০০:
- ০-২৫: NORMAL (ট্রেড চলবে)
- ২৫-৪০: WATCH (সাইজ কমানো হবে)
- ৪০-৬০: REDUCE (অবজারভ করো)
- ≥৬০: **NO TRADE**

### ধাপ ৪: রেজিম ক্লাসিফিকেশন
মার্কেট কোন অবস্থায় আছে:
- TREND_UP / TREND_DOWN
- RANGE
- LOW_VOL / HIGH_VOL
- POST_LIQUIDATION
- LIQUIDITY_STRESS
- EVENT_RISK
- CROSS_EXCHANGE_DISLOCATION

রেজিমের উপর ভিত্তি করে স্ট্র্যাটেজি বাছাই হয়।

### ধাপ ৫: অ্যালফা ইঞ্জিন
৫টি স্ট্র্যাটেজি (S1-S5) একসাথে চালানো হয়। যেটা সবচেয়ে বেশি কনফিডেন্স দেয়, সেটা বাছাই হয়।
বাকিগুলো অডিটে রেকর্ড হয়।

### ধাপ ৬: ইনস্টিটিউশনাল ফুটপ্রিন্ট
"large/informed participant activity proxy" স্কোর (০-১০০) — কোনো নাম নিয়ে দাবি করে না।
শুধু পরিমাপযোগ্য সিগন্যাল (OI impulse, CVD, absorption ইত্যাদি) থেকে কম্পোজিট স্কোর।

### ধাপ ৭: ভেটো ইঞ্জিন
৫টি ভেটো (V1-V5) চালানো হয়। কোনো HARD ভেটো ট্রিগার হলে → **NO TRADE**।

### ধাপ ৮: NewsGuard
নিউজ স্টেট চেক: BLOCK হলে → **NO TRADE**। REDUCE হলে সাইজ কমে।

### ধাপ ৯: পোর্টফোলিও ক্রাউডিং
খোলা পজিশনগুলোর কোরিলেশন চেক। খুব কোরিলেটেড হলে নতুন সিগন্যাল রিজেক্ট।

### ধাপ ১০: রিস্ক গেট
RISK_SCORE (০-১০০) হিসাব হয়:
- ভলাটিলিটি, স্প্রেড, স্লিপেজ, লিকুইডিটি
- ফান্ডিং, ক্যাসকেড, মিসম্যাচ
- নিউজ, কনফিডেন্স, R:R
- পোর্টফোলিও এক্সপোজার

স্কোর ≥৭৫ → **NO TRADE**। ≥৬০ → WATCH। ≥৪০ → REDUCED_RISK (সাইজ ×০.৫)।

### ধাপ ১১: পজিশন সাইজিং
রিস্ক-বেসড সাইজ:
- `size = (equity × risk_pct × size_mult) / stop_distance`
- ক্যাপ: ম্যাক্স লেভারেজ, ম্যাক্স নোশনাল, বুক ডেপথের ৫%, কোরিলেটেড এক্সপোজার

### ধাপ ১২: SL/TP বিল্ডার
ATR-ভিত্তিক:
- SL = entry − ১.৫×ATR
- TP1 = entry + ৩×ATR
- TP2 = entry + ৫×ATR
- TP3 = entry + ৮×ATR
- R:R অবশ্যই ≥১.৫ হতে হবে

### ধাপ ১৩: সিগন্যাল জেনারেশন
সব তথ্য একত্রিত করে Signal অবজেক্ট তৈরি। ইউনিক signal_id দেওয়া হয়।

### ধাপ ১৪: টেলিগ্রামে প্রকাশ
প্রিমিয়াম ফরম্যাটে সিগন্যাল পাঠানো হয়। অডিট ট্রেইল SQLite-এ সেভ হয়।

---

## 5. ৫টি অ্যালফা স্ট্র্যাটেজি (S1–S5)

### S1: লিকুইডেশন-ক্যাসকেড এক্সহশন
**কনসেপ্ট:** বড় লিকুইডেশন শেষ হলে দাম ঘুরে ওঠে।
**ট্রিগার:**
- cascade_index ≥ ১.৫ (৬ ঘণ্টার লিকুইডেশন ভলিউম বেসলাইনের ১.৫ গুণ)
- exhaustion_score ≥ ৪০ (ভলিউম ডিসেলারেট করছে)
- CoinDCX প্রাইস স্টেবিলাইজড
**দিক:** যে দিকের লিকুইডেশন বেশি, তার উল্টো দিকে এন্ট্রি (long liq → LONG)।
**হোল্ডিং:** ৬ ঘণ্টা–৩ দিন।

### S2: ক্রস-এক্সচেঞ্জ Lead/Lag
**কনসেপ্ট:** বড় এক্সচেঞ্জ (Binance/HL) আগে মুভ করে, CoinDCX পরে।
**ট্রিগার:**
- ল্যাগ ≥ ১ মিনিট (৫-১৫ মিনিট উইন্ডো)
- কোরিলেশন ≥ ০.৫
- বাইরের মুভ ≥ ১σ
- CoinDCX কোরিলেশন ≥ ০.৯৫
**দিক:** বাইরের মুভের দিকে।
**হোল্ডিং:** ১৫ মিনিট।

### S3: ফান্ডিং/OI ক্রাউডিং আনওয়াইন্ড
**কনসেপ্ট:** ফান্ডিং এক্সট্রিম + OI বাড়ছে = ক্রাউডেড। আনওয়াইন্ড শুরু হলে সেটাই সিগন্যাল।
**ট্রিগার:**
- |funding_z| ≥ ২
- OI কমছে (long crowding আনওয়াইন্ড)
- CoinDCX প্রাইস ডিরেকশন কনফার্ম করে
**দিক:** LONG ক্রাউডিং আনওয়াইন্ড → SHORT। SHORT ক্রাউডিং → LONG।
**হোল্ডিং:** ১-৫ দিন।

### S4: অর্ডার-বুক অ্যাবজর্পশন/CVD
**কনসেপ্ট:** বড় সেল প্রেশারেও দাম নামছে না = কেউ কিনছে (absorption)।
**ট্রিগার:**
- absorption_score ≥ ৫০
- CVD z-score এক্সট্রিম
- CoinDCX বুক ডেপথ ≥ ১০০k USD
- OBI ডিরেকশনের সাথে মিলে
**দিক:** সেল অ্যাবজর্পশন → LONG। বাই অ্যাবজর্পশন → SHORT।
**হোল্ডিং:** ১৫ মিনিট–৬ ঘণ্টা।

### S5: পার্প-বেসিস কনভার্জেন্স
**কনসেপ্ট:** পার্প vs স্পট বেসিস এক্সট্রিমে গেলে মিন-রিভার্ট করে।
**ট্রিগার:**
- |basis_z| ≥ ২
- ফান্ডিং ইভেন্ট-ডে নয়
- CoinDCX স্প্রেড স্বাভাবিক
**দিক:** PERP_PREMIUM (perp > spot) → SHORT। PERP_DISCOUNT → LONG।
**হোল্ডিং:** ১-৪ ঘণ্টা।

---

## 6. ৫টি ভেটো (V1–V5)

ভেটো = সিগন্যাল ব্লক করার হার্ড গেট।

### V1: ক্রস-এক্সচেঞ্জ কনট্রাডিকশন
CoinDCX আর বাইরের এক্সচেঞ্জের মধ্যে দামের পার্থক্য ≥ ৬০ bps → **HARD NO TRADE**।
(PEPE/DOGE-এর জন্য ১.৫× বেশি টলারেন্স।)

### V2: OI/ফান্ডিং কনট্রাডিকশন
ফান্ডিং পজিটিভ (LONG ক্রাউডিং) কিন্তু OI কমছে (LONG এক্সিট) — এই কনট্রাডিকশন ৬ ঘণ্টা+ থাকলে → **HARD NO TRADE**।

### V3: লিকুইডিটি ভ্যাকুয়াম
CoinDCX বুক ডেপথ বাইরের এক্সচেঞ্জের ১০%-এর কম, অথবা স্প্রেড মিডিয়ানের ৫ গুণের বেশি → **HARD NO TRADE**।

### V4: অসম্পূর্ণ ক্যাসকেড
cascade_index ≥ ৩ কিন্তু exhaustion_score < ৪০ (ক্যাসকেড এখনো এক্সিলারেট করছে) → **HARD NO TRADE**।
(ক্যাসকেডের মাঝে ঢুকলে ছুরিকাঘাত হয়।)

### V5: ম্যাক্রো/নিউজ কনট্রাডিকশন
NewsGuard BLOCK (CRITICAL ইভেন্ট ±২ ঘণ্টা) → **HARD NO TRADE**।
FOMC, CPI, NFP, হ্যাক, ডেলিস্ট ইত্যাদি।

---

## 7. রিস্ক গেট

RISK_SCORE = ০-১০০ (যত বেশি, তত ঝুঁকিপূর্ণ)।

**ইনপুট:**
- ভলাটিলিটি z-score
- স্প্রেড z-score
- স্লিপেজ vs এজ অনুপাত
- বুক ডেপথ
- ফান্ডিং z-score
- ক্যাসকেড ইনডেক্স
- ক্রস-এক্সচেঞ্জ ডেভিয়েশন
- মিসম্যাচ স্কোর
- নিউজ অ্যাকশন
- সিগন্যাল কনফিডেন্স
- R:R অনুপাত
- পোর্টফোলিও কোরিলেশন
- ডাইরেকশনাল এক্সপোজার

**আউটপুট:**
| স্কোর | সিদ্ধান্ত | সাইজ |
|---|---|---|
| ০-৩৯ | TRADE | ×১.০ |
| ৪০-৫৯ | REDUCED_RISK | ×০.৫ |
| ৬০-৭৪ | WATCH | ×০ (নতুন নয়) |
| ≥৭৫ | NO_TRADE | ×০ |

**Fail-closed:** কোনো ইনপুট মিসিং/স্টেল হলে → NO_TRADE।

---

## 8. NewsGuard

ফ্রি সোর্স থেকে নিউজ ক্লাসিফাই করে: GDELT, FRED, অফিসিয়াল RSS, TokenUnlocks।

**সিভেরিটি:**
- CRITICAL (FOMC, CPI, NFP, হ্যাক, ডেলিস্ট) → BLOCK ±২ ঘণ্টা
- HIGH (PCE, বড় আনলক, SEC) → REDUCE
- MEDIUM/LOW → ALLOW

**নিয়ম:** NewsGuard কখনো BUY/SELL জেনারেট করে না। শুধু গেট।
**Fail-safe:** নিউজ প্রোভাইডার ডাউন হলে → BLOCK (সেফ সাইডে থাকা)।

---

## 9. টেলিগ্রাম কমান্ড

বট চালু হলে টেলিগ্রামে কমান্ড মেনুতে এগুলো দেখাবে:

| কমান্ড | কাজ |
|---|---|
| `/status` | বটের সম্পূর্ণ স্ট্যাটাস (uptime, signals, rejects, can_trade) |
| `/paused` | পজ অবস্থা দেখাও |
| `/pause` | নতুন সিগন্যাল বন্ধ করো |
| `/resume` | নতুন সিগন্যাল চালু করো |
| `/mute` | টেলিগ্রামে সিগন্যাল আউটপুট বন্ধ (কমান্ড কাজ করবে) |
| `/unmute` | সিগন্যাল আউটপুট চালু |
| `/reset` | সব সেফটি ল্যাচ রিসেট (daily loss, consecutive loss ইত্যাদি) |
| `/health` | প্রোভাইডার হেলথ রিপোর্ট (CoinDCX, HL, Kraken ইত্যাদির অবস্থা) |
| `/signals` | সাম্প্রতিক ৫টি সিগন্যাল |
| `/risk` | রিস্ক গেট অবস্থা |
| `/help` | কমান্ড তালিকা |

**অথোরাইজেশন:** `ARUN_OPERATOR_WHITELIST` সেট করা থাকলে শুধু সেই ইউজাররা কমান্ড দিতে পারবে।

---

## 10. সিগন্যাল কেমন দেখতে

টেলিগ্রামে এরকম মেসেজ আসবে:

```
━━━━━━━━━━━━━━━━━━━━━━
  ARUN · 🟢 LONG · B
━━━━━━━━━━━━━━━━━━━━━━
Pair: BTC/USDT
CoinDCX Symbol: BTCUSDT
Strategy: S2_LEAD_LAG_CONFIRM
Regime: TREND_UP

Entry Zone: 77100.0000 – 77150.0000
Stop Loss: 76800.0000
TP1: 77600.0000
TP2: 78100.0000
TP3: 78600.0000
R:R: 2.50
Leverage: 1x–5x
Risk: 1.00% of equity

Confidence: 70/100
CoinDCX Match: 85/100
Transfer Score: 82/100
Liquidity: ADEQUATE
Funding: binance +0.5bp/8h (z=+0.50, LONG)
OI: binance ΔOI +0.50% (z=+0.80)
News: ALLOW
Portfolio Crowding: 20/100
Footprint Proxy: 55/100

Primary Alpha: lead/lag confirm (binance leads CoinDCX by 2m)
Validity: 15 min from issue
Invalidation: Price closes below 76800.0000 on 5m candle, OR mismatch score exceeds 60, OR validity window expires.
Signal ID: ARUN-A1B2C3D4E5F6
━━━━━━━━━━━━━━━━━━━━━━
```

**প্রতিটি ফিল্ডের মানে:**
- **Pair:** কোন কয়েন (BTC/USDT)
- **CoinDCX Symbol:** CoinDCX-এ যে সিম্বল খুঁজবে (BTCUSDT)
- **Strategy:** কোন স্ট্র্যাটেজি সিগন্যাল দিয়েছে (S1-S5)
- **Regime:** মার্কেট অবস্থা
- **Entry Zone:** যে দামে এন্ট্রি করবে (একটি ছোট রেঞ্জ)
- **Stop Loss:** যদি এই দামে যায়, ট্রেড বন্ধ করো (loss)
- **TP1/TP2/TP3:** টেক-প্রফিট লেভেল (৩টি — ধাপে ধাপে বিক্রি করো)
- **R:R:** Risk:Reward অনুপাত (১.৫+ ভালো)
- **Leverage:** কত লেভারেজ পর্যন্ত যাবে
- **Risk:** ইকুইটির কত % ঝুঁকি
- **Confidence:** সিগন্যালের আত্মবিশ্বাস (০-১০০)
- **CoinDCX Match:** CoinDCX কতটা মিলে যাচ্ছে (১০০ = পারফেক্ট)
- **Transfer Score:** বাইরের সিগন্যাল CoinDCX-এ কতটা ট্রান্সফার করবে
- **Liquidity:** বুক ডেপথ (ADEQUATE/STRESSED)
- **Funding:** ফান্ডিং রেট কনটেক্সট
- **OI:** ওপেন ইন্টারেস্ট পরিবর্তন
- **News:** নিউজ স্টেট (ALLOW/REDUCE/BLOCK)
- **Portfolio Crowding:** পোর্টফোলিওতে কত ক্রাউডেড
- **Footprint Proxy:** বড় পার্টিসিপ্যান্ট অ্যাক্টিভিটি প্রক্সি
- **Primary Alpha:** মূল অ্যালফা কী
- **Validity:** কত মিনিট ভ্যালিড (১৫ মিনিট)
- **Invalidation:** কখন সিগন্যাল বাতিল
- **Signal ID:** ইউনিক আইডি (অডিটের জন্য)

---

## 11. NO TRADE শর্তসমূহ

যেকোনো একটি হলেই **NO TRADE**:

1. CoinDCX futures সিম্বল NOT VERIFIED
2. CoinDCX mismatch ≥ ৬০/১০০
3. CoinDCX কোরিলেশন (১৫মি) < ০.৯৫
4. CoinDCX স্প্রেড > ৩× মিডিয়ান
5. CoinDCX ডেপথ < বাইরের এক্সচেঞ্জের ১০%
6. ডেটা ফ্রেশনেস ভায়োলেশন
7. ক্যাসকেড ইনডেক্স ≥ ৩ কিন্তু exhaustion < ৪০
8. ফান্ডিং ইভেন্ট-ডে (|ফান্ডিং| ≥ ০.০০১)
9. RISK_SCORE ≥ ৭৫
10. যেকোনো HARD ভেটো (V1-V5)
11. এন্ট্রি ভ্যালিডিটি উইন্ডো পেরিয়ে গেছে
12. নিউজ স্টেট BLOCK

---

## 12. সেফটি ল্যাচ

৮টি পারসিস্টেন্ট কিল সুইচ (রিস্টার্টেও থাকে):

1. **Daily-loss kill** — দিনে ৩% লস হলে বন্ধ
2. **Consecutive-loss latch** — টানা ৩টি লস হলে বন্ধ
3. **Extreme-volatility halt** — ভলাটিলিটি এক্সট্রিম হলে বন্ধ
4. **Data-quality halt** — CoinDCX ডেটা খারাপ হলে বন্ধ
5. **Exchange-outage halt** — এক্সচেঞ্জ ডাউন হলে বন্ধ
6. **CoinDCX mismatch halt** — মিসম্যাচ এক্সট্রিম হলে বন্ধ
7. **Network-degraded mode** — নেটওয়ার্ক খারাপ হলে
8. **Manual pause** — `/pause` কমান্ড

**শুধু `/reset` দিলেই ক্লিয়ার হবে।**

---

## 13. টপ ১০ পেয়ার

| # | পেয়ার | CoinDCX Spot | Futures (NV) | সেরা স্ট্র্যাটেজি | প্রাইমারি ভেটো |
|---|---|---|---|---|---|
| ১ | BTC | B-BTC_USDT | BTCUSDT | S2/S1 | V1 |
| ২ | ETH | B-ETH_USDT | ETHUSDT | S2/S3 | V5 |
| ৩ | XRP | B-XRP_USDT | XRPUSDT | S1/S2 | V3 |
| ৪ | DOGE | B-DOGE_USDT | DOGEUSDT | S1/S3 | V4 |
| ৫ | ADA | B-ADA_USDT | ADAUSDT | S1 | V3 |
| ৬ | SOL | B-SOL_USDT | SOLUSDT | S2 | V1 |
| ৭ | SUI | B-SUI_USDT | SUIUSDT | S8/S1 | V3/V5 |
| ৮ | BNB | B-BNB_USDT | BNBUSDT | S9 | V3 |
| ৯ | PEPE | B-PEPE_USDT | 1000PEPEUSDT | S1 | V3/V4 |
| ১০ | LINK | B-LINK_USDT | LINKUSDT | S3 | V2 |

NV = NOT VERIFIED — CoinDCX futures API থেকে ভেরিফাই হওয়া বাকি।

---

## 14. পারফরম্যান্স ও র্যাম

**RAM সীমিত রাখার জন্য:**
- সব বাফার bounded (`deque(maxlen=N)`)
- সব রোলিং স্ট্যাটিস্টিক্স O(1) — হিস্ট্রি ধরে রাখে না
- একটি শেয়ার্ড `aiohttp.ClientSession`
- ব্লকিং কাজ `asyncio.to_thread`-এ
- LLM কল নেই
- র টিক স্প্যাম নেই
- SQLite WAL, bounded retention (১০০k রো)

**মনিটরিং:**
- RSS মেমোরি (warning ৩৫০ MB, critical ৬০০ MB)
- Event-loop lag (warning ০.৫s, critical ২s)
- Queue HWM
- Task count
- Cache sizes
- Reconnect count
- Provider error rate
- Signal/veto counts

---

## 15. সমস্যা সমাধান (Troubleshooting)

### সমস্যা: বট চালু হচ্ছে না, "coindcx futures universe NOT VERIFIED"
**কারণ:** CoinDCX futures API আপনার VPS থেকে অ্যাক্সেস হচ্ছে না (geo-block বা 403)।
**সমাধান:**
- ভারতের VPS ব্যবহার করুন (CoinDCX ভারত-ভিত্তিক)
- VPN ব্যবহার করুন
- এই অবস্থায় বট সঠিকভাবে NO TRADE করবে (fail-closed)

### সমস্যা: টেলিগ্রামে কোনো মেসেজ আসছে না
**কারণ:** টোকেন/chat_id ভুল, অথবা bot chat-এ অ্যাড নেই।
**সমাধান:**
- `.env`-এ `ARUN_TELEGRAM_BOT_TOKEN` ও `ARUN_TELEGRAM_CHAT_ID` ঠিক আছে কিনা দেখুন
- বটকে chat-এ অ্যাড করুন (গ্রুপ হলে admin দিন)
- `/start` পাঠান bot-কে

### সমস্যা: কোনো সিগন্যাল আসছে না
**স্বাভাবিক:** বট fail-closed — নিশ্চিত না হলে NO TRADE।
- প্রথম ২-৪ সপ্তাহ শুধু paper validation
- CoinDCX verified হওয়া দরকার
- সব ভেটো পাস করতে হবে
- রিস্ক স্কোর < ৬০ হতে হবে

### সমস্যা: "kraken ticker empty result"
**কারণ:** Kraken pair সিম্বল ভুল।
**সমাধান:** `config.py`-এ সঠিক Kraken pair বসান (যেমন DOGE-এর জন্য `XDGUSD`)।

### সমস্যা: "hyperliquid 422 client error"
**কারণ:** HL API পেলোড ফরম্যাট ভুল।
**সমাধান:** `hyperliquid.py`-এ `candleSnapshot` পেলোড `req`-এ wrapped থাকতে হবে।

### সমস্যা: বট ক্র্যাশ করছে
**কারণ:** সম্ভবত unhandled exception।
**সমাধান:**
- `ARUN_LOG_LEVEL=DEBUG` করে লগ দেখুন
- Issue report করুন
- বট restart হলে safety latches persist করবে

### সমস্যা: র্যাম বেশি খাচ্ছে
**কারণ:** সম্ভবত unbounded cache।
**সমাধান:**
- `ARUN_RSS_WARNING_MB` কমান
- বট রিস্টার্ট করুন
- Health monitor দেখুন (`/health` কমান্ড)

---

## 16. পরিচিত সীমাবদ্ধতা (NOT VERIFIED)

গবেষণার সময় এগুলো verify করা যায়নি (স্যান্ডবক্স সীমাবদ্ধতা):

1. **CoinDCX Futures instrument list** — API geo-blocked
2. **CoinDCX funding/OI endpoints** — public docs-এ নেই
3. **CoinDCX fee/slippage structure** — app-side schedule
4. **Backtest performance numbers** — historical data নেই
5. **Transfer score calibration** — ২-৪ সপ্তাহ live data দরকার
6. **Mismatch threshold calibration** — default bands, 95th/99th percentile বাকি

**এগুলো verify না হওয়া পর্যন্ত:**
- বট paper mode-এ চলবে
- কোনো real money trade নয়
- সব সিগন্যাল paper validation

**Real money-র আগে ৪টি শর্ত (research §25.11):**
1. CoinDCX futures data ২ সপ্তাহ live capture + mismatch calibration
2. ২০০+ paper signal-এ ≥৮০% CoinDCX-এ confirm
3. Transfer score ≥৭০ ও net expectancy >০ (fee+slippage+funding সহ) OOS
4. Veto false-positive rate <২০%

---

## ডিসক্লেইমার

এটি গবেষণা সফটওয়্যার, আর্থিক পরামর্শ নয়। কোনো লাভের প্রতিশ্রুতি নেই।
সিস্টেম fail-closed — অনিশ্চিত হলে NO TRADE।

**ব্র্যান্ড:** ARUN
**ভার্সন:** 1.0.0
**রিসার্চ কাটঅফ:** ২২ আগস্ট ২০২৬
**টার্গেট ডিপ্লয়মেন্ট:** আগস্ট-সেপ্টেম্বর ২০২৬
