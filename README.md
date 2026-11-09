# מערכת דילים אוטונומית

מנוע שרץ פעמיים ביום ב-GitHub Actions, מושך פידים של מוצרים מ-Admitad, בוחר רק דילים חזקים
(הנחה של 30% ומעלה מול החציון של 30 יום, דירוג 4.7 ומעלה, לפחות 500 הזמנות, ציון חום 55 ומעלה),
מפרסם ל-3 ערוצי טלגרם ובונה אתר סטטי בשלוש שפות (‎/he/ ‎/es/ ‎/en/) ל-Cloudflare Pages.

## מבנה
| תיקייה | תוכן |
|---|---|
| `engine/core.py` | קריאת פידים, היסטוריית מחירים (SQLite), מסננים וציון חום |
| `engine/translate.py` | כותרות בעברית ובספרדית דרך Gemini (חינם). בלי מפתח – כותרת מקורית |
| `engine/telegram.py` | פרסום לערוצים, והתראות פרטיות לבעלים |
| `engine/run.py` | ריצה מלאה |
| `webgen/build.py` | בניית האתר: hreflang, sitemap, Schema, גרף מחיר |
| `config/settings.json` | ספים, משקלים ו-`"paused": true` לעצירה |
| `config/languages.json` | טקסטים, נישות ומילות מפתח לכל שפה |

## Secrets (ב-GitHub: Settings ← Secrets and variables ← Actions)
| שם | מאיפה |
|---|---|
| `FEEDS_HE` / `FEEDS_ES` / `FEEDS_EN` | Admitad ← Product Feeds ← קישור הפיד (CSV). פורמט: `aliexpress=URL,banggood=URL` |
| `TELEGRAM_BOT_TOKEN` | ‎@BotFather ← ‎/newbot |
| `TELEGRAM_OWNER_CHAT_ID` | המזהה הפרטי שלך בטלגרם (להתראות ולדוח) |
| `GEMINI_API_KEY` | aistudio.google.com ← Get API key (חינם) |

Variables (לא סודי): `SITE_BASE_URL`, ואופציונלית `CLICK_BASE_URL` (מונה הקליקים).

## הרצה מקומית עם נתוני דמה
```
python3 mock/generate.py && DEALS_MOCK=1 python3 -m engine.run
```
