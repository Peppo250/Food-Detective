# 🔬 Food Detective

A desktop app for kids (ages 6–12) that reads food labels and explains what every ingredient is — using only free, public APIs. No paid AI services required.

---

## How it works

1. Take or upload a photo of any food label
2. Tesseract OCR reads the tiny ingredient text
3. Each ingredient is checked against OpenFoodFacts, OpenFDA, Wikipedia and Wikidata (all free)
4. Results stream to the screen in real time — safe ✅, caution ⚠️, or avoid 🚫
5. Everything is cached for 90 days in SQLite so repeat scans are instant

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | Download from python.org |
| Tesseract OCR engine | See installation below |
| Internet connection | For first-time ingredient lookups |

---

## Step 1 — Install Tesseract

Tesseract is the OCR engine that reads the text on food labels.

### Windows
1. Download the installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the `.exe` installer (keep the default install path)
3. Tesseract will be at: `C:\Program Files\Tesseract-OCR\tesseract.exe`
4. Add it to your PATH, or set the path in your environment:
   ```
   setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
   ```

### macOS
```bash
brew install tesseract
```

### Ubuntu / Debian Linux
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
```

---

## Step 2 — Set up Python environment

Open a terminal (or Command Prompt on Windows) and run:

```bash
# Clone or download the project folder, then navigate into it
cd food_detective

# Create a virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS / Linux:
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

**Note:** `opencv-python` (for camera capture) is optional. If it fails to install on your system, remove it from `requirements.txt` — the app will still work for file uploads, just without the camera button.

---

## Step 3 — Run the app

```bash
python main.py
```

The app window will open. That's it!

---

## Project structure

```
food_detective/
│
├── main.py               ← Entry point: starts server + UI
├── app.py                ← FastAPI backend with SSE streaming
├── ui.py                 ← Tkinter UI (child-friendly interface)
├── requirements.txt      ← Python dependencies
│
├── modules/
│   ├── ocr.py            ← Image preprocessing + Tesseract OCR + text parser
│   ├── cache.py          ← SQLite cache (90-day TTL, auto-cleanup)
│   ├── enricher.py       ← Async parallel API fetcher (4 sources)
│   ├── scorer.py         ← Rule-based safety classifier
│   └── explainer.py      ← Kid-friendly text generator
│
└── data/
    └── ingredients.db    ← Auto-created SQLite database (cache)
```

---

## Free APIs used

| API | What it provides | Rate limit |
|---|---|---|
| **OpenFoodFacts** | Additive data, E-numbers, risk levels | No limit (please be polite) |
| **OpenFDA** | FDA adverse event reports, GRAS status | 1000 req/day without key |
| **Wikipedia REST** | Plain English ingredient summaries | No limit |
| **Wikidata SPARQL** | Structured properties (CAS, hazard flags) | No limit |

No API keys needed for any of these.

---

## Tips for best results

- **Good lighting** makes OCR much more accurate
- **Lay the package flat** so the label isn't curved
- **Get close** — the label should fill most of the photo
- **Avoid glare** from shiny packaging — tilt slightly

---

## Cache management

The SQLite cache lives at `data/ingredients.db`. It:
- Stores results for **90 days**
- Auto-deletes expired entries on every app start
- Also runs a daily background cleanup

To clear the cache manually:
```bash
rm data/ingredients.db
```

---

## Ingredient safety classification

| Label | Meaning |
|---|---|
| ✅ Safe | Natural, whole-food ingredients |
| ⚠️ Caution | Processed but not directly harmful — limit quantity |
| 🚫 Avoid | Linked to hyperactivity, allergies, or cancer risk in studies |
| ❓ Unknown | Not enough data found |

The avoid list includes: artificial colours (Red 40, Yellow 5/6, Blue 1), sodium benzoate, BHA, BHT, TBHQ, sodium nitrate/nitrite, aspartame, saccharin, MSG, HFCS, trans fats, and carrageenan.

---

## Troubleshooting

**"No ingredients found — try a clearer photo!"**
→ The OCR couldn't read the label. Try better lighting or get closer.

**App hangs on startup**
→ The server takes ~1 second to start. Wait a moment after opening.

**Slow on first scan of a new product**
→ Normal — the app is fetching from 4 APIs simultaneously. After the first scan, results are cached and will be instant.

**Camera not working**
→ Make sure `opencv-python` is installed (`pip install opencv-python`). Check your system's camera permissions.

**Tesseract not found error**
→ Make sure Tesseract is installed and in your PATH. On Windows, restart your terminal after installation.
