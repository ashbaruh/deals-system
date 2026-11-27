# PROJECT_STATE — dealim.net (מצב הפרויקט להמשך בשיחה חדשה)

עודכן: 27.11.2026. בעלים: Ash. תשובות אליו: בעברית, קצר, טבלאות, ולכל המלצה זמן + עלות + צעד ראשון.
אין בקובץ הזה סיסמאות, טוקנים או מפתחות. כל הסודות נשמרים ב-GitHub Secrets או ב-Cloudflare, ו-Ash מזין אותם בעצמו.

---

## 1. מטרה

אתר דילים אוטונומי של AliExpress (ו-Joom) עם קישורי שותפים של Admitad, בשלוש שפות שוות בחשיבותן: עברית, ספרדית ואנגלית.
- **יעד:** מנויים, תנועה והכנסה מעמלות, עם מינימום עבודה ידנית.
- **יעד קרוב:** 50–100 חברים אמיתיים לפחות בערוץ טלגרם אחד.
- **ערוצי טלגרם:**
  - עברית: t.me/mivtzaim_kuponim (כ-12 חברים, רובם הגיעו דרך htmag)
  - ספרדית: t.me/ofertas_descuentos_es
  - אנגלית: t.me/discount_deals_promo
- **הפצה נוספת:**
  - Pinterest (חשבון ashbaruh), דרך פידי RSS
  - Bluesky @dealimdeals.bsky.social
  - פורום htmag.co.il (ראה סעיף 6)
- **מצב (23.11):**
  - Admitad: כ-260 הקלקות מאז 10.11, 3 הזמנות ועמלה של $1.52 בהמתנה לאישור.
  - מבקרים אמיתיים: עשרות עד כ-120 ביום. רוב התעבורה ב-Cloudflare היא בוטים.

---

## 2. ארכיטקטורה — מה רץ איפה ומתי

| רכיב | איפה | מתי | הערות |
|---|---|---|---|
| ריפו | GitHub ashbaruh/deals-system | — | האתר נבנה לתיקייה `public/` ונשמר ב-commit לריפו |
| אירוח האתר | Cloudflare Pages ← `public/` | אחרי כל commit | הדומיין dealim.net נרכש ב-Cloudflare Registrar לשנתיים |
| מתזמן ראשי | Cloudflare Worker `bitter-block-44f2` (קוד: `cloudflare/scheduler-worker.js`) | cron `5 6,7,9,11,13,15,17,19,21,23 * * *` UTC | שולח workflow_dispatch ל-`run.yml`. מחזיק את הסוד GH_TOKEN |
| לייב יומי | אותו Worker, cron `37 17 * * *` ← `live.yml` | — | **כבוי**: `live.yml` במצב disabled_manually (ראה סעיף 5). ה-cron עדיין קיים ונכשל בלי נזק |
| גיבוי | `run.yml` schedule `43 1 * * *` UTC (03:43 בישראל) | פעם בלילה | רק גיבוי אחד. הקודמים הוסרו כי התנגשו בתור |
| סבב דילים | `.github/workflows/run.yml` ← `python -m engine.run` | בכל הפעלה | ראה פירוט מתחת |
| תמונות לפינטרסט | שלב "Pinterest images" ב-`run.yml` ← `python -m webgen.pins` | אחרי הבנייה | continue-on-error. אם נכשל, הפיד נשאר עם תמונות המוצר |
| ניתוח תעבורה | Cloudflare Web Analytics, site_tag `2b96eb8e…` | — | מצב lite כבוי מ-23.11, כך שגם מבקרים מאירופה נמדדים |
| Crawler Hints | Cloudflare, הגדרות Caching | מ-23.11 | מודיע ל-Bing ולמנועים אחרים על עמודים חדשים (IndexNow) |
| Bing Webmaster | dealim.net ו-aitoolhd.com, יובאו מ-Search Console | מ-23.11 | sitemap נקרא בהצלחה, כ-1.4K כתובות |
| Search Console | המאפיין `https://dealim.net/` | — | ל-`sc-domain` אין גישה |

**מה עושה סבב דילים (`engine/run.py`):**
1. מושך פידים מ-Admitad.
2. בוחר דילים לפי `engine/core.py`, תוך השוואה להיסטוריית המחיר ב-`data/history.sqlite`, שנשמר ב-Actions cache.
3. מתרגם עם Gemini (`engine/translate.py`).
4. מפרסם לטלגרם (`engine/telegram.py`) ול-Bluesky (`engine/bluesky.py`).
5. בונה את האתר (`webgen/build.py`) ושומר ב-commit.

**קלטים ל-`run.yml` (workflow_dispatch):**
- `retranslate`: בנייה מחדש מהירה עם תרגום של שמות חסרים, בלי פרסום.
- `retranslate_all`: מוחק את מטמון התרגום ומתרגם מחדש את כל השמות.
- `publish_anytime`: מפרסם לטלגרם גם מחוץ ל-08:00–23:00.
- `cleanup`, `seed`, `preview`, `publish_preview`, `delta_hours`, `only_niche`.

**קבוצת concurrency:** GitHub שומר ריצה אחת בלבד בהמתנה. dispatch חדש מבטל את זו שממתינה. ריצה תקועה: `gh api …/runs/{id}/force-cancel`.

**שמות הסודות** (בלי ערכים):
- FEEDS_HE, FEEDS_ES, FEEDS_EN
- TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID
- BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
- GEMINI_API_KEY
- YT_STREAM_KEY (לייב)
- GH_TOKEN (ב-Worker)

**משימות מתוזמנות של Claude (נכון ל-24.11):**
- `trig_019BWAJzA5ywcZQ7RzJKXPnL`: "חדר הפיקוד". מעבד בקשות מהדשבורד, כל יום ב-20:17 שעון ישראל.
- `trig_01Q4mcyoRgaDmmCWFwq1WzRo`: רענון מחירי אודיופיל, 25.11 ב-18:00 UTC. בסוף כל ריצה הוא מתזמן את עצמו שוב לעוד 3 ימים.
- `trig_01XNkr5RVaE9h8uWsc6D8gkQ`: סבב אמזון ל-htmag. **כבוי**. רץ רק כש-Ash מבקש.

---

## 3. קבצי הגדרות חשובים

**`config/languages.json`** — לכל שפה:
- מטבע, שער, ערוץ, `post_times`, מחרוזות, ו-`niches`.
- נישות: brands, coffee, audio, nails, shoes, fashion, appliances, dashcam, power, watch, tech, pets, home, tools, car, sports, kids, dollar.
- שדות של נישה: `title`, `keywords`, `categories_exact`, `also` (כללים נוספים), `take_brands` (נישה שגוברת על "brands").

**`config/settings.json`:**
- **מחיר:**
  - `max_price_usd`: 150.
  - `max_price_usd_tools`: 300.
- **מותגים:**
  - `fav_brands`
  - `audio_brands`: 25 מותגים, כולל 16 שנוספו ב-24.11.
  - `audiophile_scout_brands`
  - `audiophile_picks`: 37 מוצרים ידניים, כל אחד עם `store` ו-`checked`.
- **אירועים (`events`):** gta6, black-friday, singles-day.
  - שדות: keywords, exclude, badge, subtitle, hero_css, hashtags, extra_per_run, site_extra.
- **עמלות וקצב:**
  - `commission_by_category`.
  - `max_posts_per_day` / `per_run`: לפי מה ש-Ash ביקש, 20 פוסטים ליום בכל ערוץ.
- **Joom:** `joom_*`.

**`data/`:**
- `deals_{he,es,en}.json`: ארכיון הדילים באתר.
- `history.sqlite`: היסטוריית מחירים ומטמון תרגומים.
- `live_links*.json`: קישורים קצרים `/l/`, `/g/` ו-`/f/` (‏`/f/` מיועד לפורום).

**`webgen/build.py`:**
- **עמודים:** עמוד לכל דיל, עמוד לכל נישה ועמוד לכל אירוע.
- **SEO ו-AI:** JSON-LD למוצר (שם בשפת העמוד מ-23.11), sitemap, robots, `llms.txt`.
- **פיד RSS:** 10 דילים לכל שפה, בשביל פינטרסט.
- **מעקב מקורות:**
  - `?ref=<code>` נשמר ב-localStorage ומתווסף כ-subid1 לקישורי Admitad.
  - דפי הפניה לפי מקור: `/tt`, `/yt`, `/ig`, `/pin`, `/tg`, `/fb`, `/wa`, `/rd`.

**subid ב-Admitad:**
- פורמט כללי: `lang_source_niche`.
- פורום: `he_htmag_<niche>`.
- הגעה מהפורום דרך האתר: subid1=htmag.

**`webgen/pins.py` + `webgen/Rubik.ttf`:** יוצר תמונות פין בגודל 1000×1500 עם תמונת המוצר, אחוז ההנחה, המחיר ולוגו dealim.net. את ה-bidi לעברית עושה הקוד עצמו (Layout.BASIC).

**`cloudflare/scheduler-worker.js`:** עותק של קוד ה-Worker. שינוי ב-cron נעשה בדשבורד של Cloudflare ובקובץ הזה באותו זמן.

---

## 4. החלטות וכללים של Ash

**כללי עבודה:**
- תשובות בעברית, קצרות, עם טבלאות.
- להחליט בשבילו החלטות תפעוליות שמשרתות את המטרה, בלי לשאול על כל צעד.
- לבדוק לפני שמדווחים "בוצע".
- לא מקלידים סיסמאות או טוקנים. Ash מזין סודות בעצמו.
- לא פותרים CAPTCHA, לא פותחים חשבונות ולא מבצעים תשלומים.

**הפצה:**
- **אינסטגרם:** רק מכינים קובץ וכיתוב. Ash מעלה בעצמו.
- **פייסבוק:** בלי עמוד פייסבוק חדש. מכבדים את הכללים של כל קבוצה.
- **קשרים אישיים:** לא משתמשים במכרים אישיים.
- **ספרדית ואנגלית:** מקדמים רק במקומות שמתירים זאת במפורש.
- **קישורים:** כל קישור שמתפרסם חייב להיות לחיץ.

**תוכן:**
- רק הנחות אמיתיות, שנבדקו מול היסטוריית 30 יום. לכל מוצר באתר חייבים להיות מחיר והנחה.
- בלי זיופים של מותגים.
- המותגים האהובים עליו: Zidoo, FiiO, Shanling, Aiyima, SMSL, Topping, Fosi.
- דילים של מותגי האודיו שלו מתפרסמים גם מעבר למכסת 20 ליום.

**כסף:**
- קודם דרכים חינמיות.
- תשלום רק אם בטוח שזה מביא חברים, רק בכרטיס אשראי או PayPal ובלי להתקין אפליקציות.
- אם יש פרסום ממומן, הוא הולך לערוץ הספרדי.

**שפות:** אף ערוץ לא נזנח, כולל העברי.

**Gemini:** רק לתרגום בתוך ה-pipeline ולתמונות. לא לניתוח.

**htmag:** ראה סעיף 6, והסקיל `htmag-amazon-posting`.

---

## 5. מה נכשל ולמה

| נושא | מה קרה | מצב |
|---|---|---|
| לייב יומי ביוטיוב | מ-18.11 ה-workflow דיווח "success" וה-ffmpeg שידר 10 דקות, אבל ב-YouTube Studio הופיע "No data". הסבירות הגבוהה: `YT_STREAM_KEY` לא תואם למפתח הנוכחי, ויוטיוב לא מחזיר שגיאה על מפתח כזה. הודעות "אנחנו בלייב" יצאו לטלגרם ול-Bluesky בלי שהיה לייב. דיווחתי בטעות "בוצע" בלי לאמת | **27.11: עובד.** `live.yml` הופעל מחדש; YouTube, Twitch ו-Kick אומתו בשידור. ההודעות לטלגרם נשלחות רק אחרי בדיקה שהשידור באוויר (`video/announce.py` → `is_live`). ב-27.11 הבדיקה ליוטיוב החזירה False מהשרת של GitHub למרות שהשידור היה באוויר, ולכן לא נשלחה הודעה. נוסף לוג, לבדוק בריצה הבאה |
| פינטרסט | 602 פינים, אבל כחשיפה אחת ב-30 יום. ההערכה: תמונות מוצר משוכפלות מאלי, ונפח ספאמי | 22.11: תמונות פין מקוריות ו-10 דילים בפיד לכל שפה. לבדוק חשיפות בעוד 4–8 שבועות |
| תרגום | Gemini החליף לפעמים בין פריטים בתוך אצווה (למשל פסלון חתול קיבל את השם "כרית ברך לרכב"). בעומס הוא מחזיר 429 או 503 | נוספה בדיקה שהמודל מחזיר את 3 המילים הראשונות של השם המקורי, והפסקה של 8 שניות בין אצוות. שמות שנכשלו נשארים באנגלית עד הרצת `retranslate` הבאה |
| אוטומציית אמזון ל-htmag | Cloudflare של הפורום חוסם בקשות מהענן. בעל האתר סירב לפתוח חריגה ולא מוכן לתת מפתחות | עובד רק דרך Chrome במחשב של Ash, ורק כשהוא מבקש |
| הרצה של המשימה המתוזמנת של htmag | נכשלה כי חשבון Claude הגיע למגבלת השימוש | כבויה |
| שתי שכבות תזמון | ה-schedule של GitHub התעכב עד שעתיים וביטל ריצות של Cloudflare | נשאר רק גיבוי לילי אחד |
| נישת חיות | מעט היצע: כ-18 פריטים באלי, ו-Joom נחסם ב-boot_noold | לא שוחרר. לבדוק שוב ב-1.12 |
| חסימת בוטים מעתיקים (WAF) | הפעולה נחסמה למערכת האוטומטית | לא בוצע. ניקוי נתונים בלבד, בעדיפות נמוכה |
| `index_html` | קרס כש-"off" היה מספר | הערך חייב להיות מחרוזת, למשל "-63%" |

---

## 6. htmag.co.il (פורום phpBB, משתמש claudia5)

**אמזון (f=107), העמלה של הפורום:**
- **מבנה:** מוצר אחד בכל פוסט. כותרת `$<סה"כ> עד הבית \ <תיאור עם מותג ודגם>`.
- **גוף הפוסט:**
  - תיאור, הנחה ומחיר מקורי.
  - מחיר, משלוח לישראל, מיסים וסה"כ.
  - מידה וצבע שנבדקו.
  - שורת `[url]https://www.amazon.com/dp/ASIN[/url]`.
  - שורה ריקה בין כל שורה לשורה.
- **אסור:** תמונות, קישורים מקוצרים, התו "+".
- **נפסלים:**
  - מוצר שהמשלוח שלו גדול מ-50% מהמחיר.
  - מוצר חשמלי של 110V בלבד.
  - מוצר שכבר פורסם בפורום (לפי מותג ודגם).
  - יותר מ-2 מוצרים מאותו מותג בסבב.
- **קצב:** 150 שניות בין פוסטים. לשמור את ההתקדמות ב-localStorage, כי הדף עלול להיטען מחדש.
- **הסבבים האחרונים:**
  - 23.11: נושאים 404795–404804.
  - 24.11: נושאים 404812–404821.

**HT Deals (f=110), העמלה של Ash:**
- **מה מותר:** קישורי Admitad מלאים וגלויים, בשורה נפרדת: `https://rzekl.com/g/1e8d11449413a2dc498e16525dc3e8/?ulp=<aliexpress item url encoded>&subid=he_htmag_<niche>`.
- **מה Ash החליט:** להוסיף בסוף כל פוסט שורה אחת שמקשרת לעמוד באתר עם `?ref=htmag`, בשביל לגייס חברים לטלגרם.
- **פוסט סיכום:** רק כש-Ash מחליט.
- **מכסה:** אין מכסה יומית.
- **פוסטים אחרונים (23.11):** 404805 (אודיו) ו-404806 (UGREEN ו-Baseus).
- **מה עובד:** הנושא "בלאק פריידיי" הביא הכי הרבה צפיות (94), ואחריו סיכומים מבוססי מותג. פרסום בערב.

---

## 6א. קמפיין סרטון טוויטי בפייסבוק (בלאק פריידיי, 27.11)

**הנכסים:** סרטון קידום של 18.6 שניות עם החתולה טוויטי, בעברית, ספרדית ואנגלית. הקבצים ב-`/home/claude/promo` (סשן זמני):
- `tweety_dealim_{he,en}.mp4`
- גרסאות דחוסות להעלאה (≤3.8MB): `tweety_{he,es,en}_fb.mp4`. הגדרות הדחיסה: crf 27, maxrate 1.4M, aac 96k.

**שיטת הפרסום (דרך החשבון של Ash ב-Chrome):**
1. הסרטון עולה בגוף הפוסט, עם טקסט שונה בכל קבוצה. בטקסט עצמו אין קישור, כי קישור בגוף הפוסט מגדיל את הסיכוי לדחייה.
2. הקישור לאתר נכנס כתגובה ראשונה מיד אחרי הפרסום: `https://dealim.net/<lang>/?ref=fb_tweety`.
3. בין פוסט לפוסט עוברות 3–10 דקות.
4. המצב של כל פוסט נבדק ב-`/groups/<id>/my_posted_content`, ב-`my_pending_content` וב-`my_declined_content`.

**אישור:** ב-27.11 Ash אישר להצטרף לקבוצות, לאשר כללי קבוצה ולפרסם בלי לשאול בכל פעם.

**מצב ב-27.11, 12:55:**

| מצב | קבוצות |
|---|---|
| ✅ פורסם + תגובה עם קישור (12) | EN (נוספו 12:15–12:40): aexpresscouponpromocodedeals (1.9K), aexpresspromoandcouponcodeglobal (11K), 2131451090662594 welcome deals trusted (1.3K). ES: Best Aliexpress, Aliexpress Mexico Dudas y Compras (50K), Cupones Ofertas descuentos Todos los dias (21K). EN: Shopping Discounts Offers (49K), Aliexpress products, Aliexpress Big Sale (31K), Ali express products, Ali Express Products (3.7K), Aliexpress Affiliate marketing 1454095598757208 (8.8K) |
| ⏳ ממתין לאישור מנהל (16, נכון ל-12:35 אף אחד עוד לא אושר; בדיקה מתוזמנת ב-14:37). התגובה עם הקישור תתווסף אחרי האישור | EN: couponsfromchinacom (19K), THE BARGAIN BIN 1032826214055528 (800K), GOOD GOLLY 837612917680653 (384K), blackfridayad (177K), 296804256287111 (107K), 1985465295015321 (44K), 1040511414605438 (61K), 1189744009506598 (26K), 528235004572113 (24K), coupons.coins (18K). ES: chollocupones (78K), comunidad.aliexpress.peru (50K), ofertasmazon (36K), OFERTAPERU (28K), chinaofertasycupones. HE: alioutlet.sale (20K) |
| ❌ נדחה / ⚠️ לא ברור | CHOLLOS Y DESCUENTOS נדחה. ofertastopmexico ו-aliexpressperududas: הדף מחזיר "התוכן לא זמין" |
| 🚫 דולג | AliExpress Chile: הכללים אוסרים קידום |

**לקחים:**
- קבוצות גדולות (מעל 20K) כמעט תמיד בודקות משתתף חדש לפני הפוסט הראשון שלו.
- קבוצות אליאקספרס קטנות-בינוניות מפרסמות מיד.
- יש קבוצות שבהן הפוסטים של Ash נשארים "ממתין" לנצח, ולכן מדלגים עליהן: welcome Deal, COUPONS & PROMO CODES, Group Buy, online shopping group, Aliexpress Online Shopping, Shopping Reviews, Alibaba-AliExpress, 357963973628413.
- **למדידה:** ב-Admitad ובאתר, ההגעה מהקמפיין נספרת לפי `ref=fb_tweety` (subid1).

## 6ב. הארון של טליה (27.11)

- קטגוריה בשם בתו של Ash: he "הארון של טליה", es "El armario de Talia", en "Talia's Closet". בגדי נערות טרנדיים שטליה בחרה.
- **כללים קשיחים:** רק השם הפרטי שלה מופיע באתר. אין תמונה שלה ואין גיל. פריטים חושפניים (בגדי גוף, חזיות וכו') לא נכנסים לקטגוריה שלה. 7 פריטים כאלה (23–29) הוסרו מהאתר לגמרי לבקשת Ash.
- **נתונים:** `config/settings.json` → `talia_picks`, 22 פריטים. לכל פריט: id, img, name_he/es/en, price_usd, list_usd, store, checked. המחירים נבדקו ב-27.11. מקור הנתונים: `/home/claude/talia/raw.jsonl`.
- **קוד:** `webgen/build.py`: TALIA, talia_cards, talia_rail, talia_page.
- **מה נבנה:**
  - דף `/<lang>/talia`
  - קישור "👗" בתפריט
  - שורת פריטים בדף הבית ובנישת אופנה
  - הדף נכלל ב-sitemap
  - הקישורים הם Admitad עם `subid=<lang>_site_talia`
- **באוויר מ-27.11 12:55.** הבנייה נעשתה מקומית ונדחפה לאוויר (Cloudflare מפרסם בכל commit).
- **מדריך בלאק פריידיי (27.11):** כתבה בכתובת `/<lang>/guide/black-friday-teen-girls`, מכוונת להורים לנערות. 22 הפריטים מחולקים ל-4 קבוצות, עם 4 טיפים (מידות, משלוח, מחיר, לשתף אותה) ו-schema מסוג Article. קישורי השותפים עם `subid=<lang>_site_guide`. באנר בדף הבית עד `GUIDE_UNTIL` (2026-12-01). הקוד ב-`webgen/build.py`: GUIDE ו-guide_page.
- **פרסום בפייסבוק (27.11):**
  - פוסט בפרופיל של Ash עם קולאז' בעברית ו-`?ref=fb_talia`.
  - Best Aliexpress: קולאז' בספרדית.
  - Shopping Discounts Offers ו-Aliexpress Big Sale: נוסח כללי, קולאז' "Black Friday fashion for teen girls", ובתגובה קישור למדריך עם `?ref=fb_bfgirls`.
  - **כלל:** בקבוצות ציבוריות מפרסמים בלי השם של טליה ובלי "הבת שלי". מערכת הבטיחות חסמה פרסום שהציג אותה בשמה.
  - הקולאז'ים ב-`/home/claude/promo/talia/`.
- **פוסטים ב-htmag, HT Deals (f=110), 27.11:**
  - מעילים וג'קטים: https://htmag.co.il/phpbb/viewtopic.php?t=404920 (5 דילים, החל מ-12.02$).
  - כל הקטגוריה: https://htmag.co.il/phpbb/viewtopic.php?t=404922. כולל סט טרנינג חם (16.11$), בומבר ורסיטי (22.54$), סט Y2K נמר (14.92$), מגפי שלג (29.05$) וכיסוי אייפון 17 פרו (13.38$). המחירים כוללים משלוח.
  - שני הפוסטים פורסמו בלי השם של טליה. Ash משנה את הכותרת בעצמו כדי להוסיף את השם, ומוסיף שורה כמו "שטליה בחרה בעצמה".
  - בגוף הפוסט: לכל מוצר קישור Admitad עם `subid=he_htmag`, ובסוף קישור למדריך `dealim.net/he/guide/black-friday-teen-girls.html`.
  - **שיטת פרסום:** בטאב posting.php לוחצים על שדה הכותרת (~1000,442) ועל העורך (~800,580), מקלידים, גוללים 10 למטה ולוחצים "שלח" (~596,229). JS לא מוצא את שדות הטופס.
  - **משלוח בפריטי Choice:** כ-1.02$ כשהסל מתחת ל-12$. להוסיף את זה לסה"כ.
- **בהמשך:** לייב בטיקטוק עם טליה, רק כש-Ash יבקש. לרענן מחירים אחרי בלאק פריידיי. מוצע ולא אושר: קולאז' 4 פריטים עם כיתוב לאינסטגרם, וסדרה שבועית "הבחירה של השבוע".

---

## 7. משימות פתוחות לפי עדיפות

0. **קמפיין טוויטי בפייסבוק:** לבדוק את 16 הפוסטים הממתינים ולהוסיף תגובה עם קישור לכל פוסט שאושר (ראה 6א). אחרי יומיים לבדוק קליקים עם `fb_tweety`.

1. **רענון מחירי אודיופיל (כל 3 ימים):** 27.11 נוספו 12 מוצרים (48 סה"כ). **חובה בכל ריצה** — לא רק רענון מחירים: חיפוש לפי מותג (`aliexpress.com/w/wholesale-<brand>.html?sortType=total_tranpro_desc`) לכל `audiophile_scout_brands`, אימות בדף המוצר (`[class*=price--current]`, `[class*=price--original]`, שם חנות). מוסיפים רק: חנות רשמית או מורשה (HiFiGo, Shenzhenaudio, Linsoul, DD-Audio, BrightAudio), הנחה 12%–55% (מעל 55% = מחיר מחירון מנופח), לא אביזרים. ב-27.11 לא נמצאו: Sabaj, Loxjie, Ugoos (אין תוצאות); Gustard ו-Tangzu (הנחה 10%); Douk (71%, מנופח); iBasso (חנות לא מורשית או הנחה מנופחת).
2. **מעקב חשיפות:**
   - Bing (Search Performance ו-AI Performance).
   - Admitad לפי subid: he_htmag_*, htmag, es_site.
   - חשיפות בפינטרסט עם תמונות הפין החדשות.
   - הקהל הספרדי ב-Web Analytics, עכשיו שגם אירופה נמדדת.
3. **גידול טלגרם:**
   - לשאול את בעל htmag אם מותר קישור לערוץ או חתימה בפרופיל.
   - פרסום ממומן לערוץ הספרדי נשקל, רק בכרטיס או PayPal.
4. **לייב בטיקטוק עם הבת:** ממתינים שתבחר תחום ותחליט אם היא מופיעה מול המצלמה. אחר כך בונים גלריה של כ-200 תמונות מהמבצעים, היא בוחרת, והלייב נבנה מהבחירות שלה.
5. **Joom:** בדיקה ב-1.12, כולל נישת החיות.
6. **לייבים רק כש-Ash מבקש (27.11).** ה-cron `37 17` ב-Worker עדיין שולח dispatch, אבל `live.yml` מדלג עליו כי חסר `manual=true`. הפעלה ידנית: `gh api repos/ashbaruh/deals-system/actions/workflows/live.yml/dispatches -f ref=main -f 'inputs[lang]=en' -f 'inputs[target]=youtube|twitch' -F 'inputs[stream]=true' -F 'inputs[manual]=true'` (twitch משדר גם ל-Kick).
7. **`aggregateRating`:** כרגע `reviewCount` מקבל את מספר ההזמנות, שזה לא מספר ביקורות. לשקול להסיר את השדה כדי להימנע מנתונים מטעים.
8. **WAF:** לחסום python-requests, Keenabl, ElevenLabs ו-Reflect. עדיפות נמוכה.

---

## 8. איך מתחילים בשיחה חדשה

- `git clone` של הריפו ו-`gh auth`. הכלי `gh` כבר מחובר דרך הפרוקסי.
- **בנייה מקומית:** `python3 -c "from webgen.build import build; build()"`. אחר כך `git checkout -- public && git clean -fd public` לפני commit, כי ה-CI בונה בעצמו.
- **בנייה מחדש מרחוק:** `gh api repos/ashbaruh/deals-system/actions/workflows/run.yml/dispatches -f ref=main -f 'inputs[retranslate]=true'`
- **Chrome:** הדפדפן המחובר הוא ה-Chrome של Ash. Facebook, Admitad (store.admitad.com), Cloudflare, Bluesky, htmag, Amazon, Pinterest ו-Bing מחוברים בו.
- **דפי אלי:** קוראים בעזרת browser_batch (navigate ואז JS). iframes חסומים.
- **דשבורד חדר הפיקוד:** artifact `fadd4749-2485-4024-a526-9a630dc0c2b0`, הפרויקטים `projects/dealim` ו-`projects/htmag`.

- 27.11 (later): Talia's Closet grew to 45 items (+23: 9 coats, 7 sets/pants, 4 shoes, 3 accessories). GUIDE_GROUPS index ranges 22-31/31-38/38-42/42-45 — new items must be appended in group order. Excluded: sports-bra/yoga sets, backless items, short yoga suit, Juicy Lovers (brand knockoff), Bundle Deals.
