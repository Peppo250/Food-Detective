# 🔬 Food Detective

A child-friendly desktop application (ages 6–12) that reads food labels, demystifies complex chemical ingredients, and calculates daily consumption limits — powered entirely by free, public APIs.

No paid AI services, no subscription models, and no API keys required.

---

## 📸 Screenshots

*(Screenshots coming soon)*

---

## 💡 Motivation

Many modern food products targeting children are packed with artificial colors, preservatives, and processed ingredients. While these ingredients are listed on the packaging, they are often obscured by complex chemical names (e.g. "Sunset Yellow" listed as "E110", or "Sodium Benzoate" hiding under complex text). 

**Food Detective** was built to empower kids and parents:
1. **Demystification**: Explaining what "BHA" or "Tartrazine" actually is in simple, child-friendly terms (e.g., "Tartrazine is a bright yellow dye made from chemicals").
2. **Actionable Limits**: Translating scientific terms like "Acceptable Daily Intake (ADI)" into physical portions, such as "max 1 serving per day" for a child.
3. **Data Independence**: Operating purely on free, open databases (OpenFoodFacts, OpenFDA, Wikipedia, and Wikidata) to keep educational tools accessible to everyone.

---

## 🚀 Features

* **Smart Preprocessing Pipeline**: Adapts automatically to image quality. When OpenCV is installed, it leverages a **Bilateral Filter** (to remove sensor grain while preserving text edges) and **CLAHE** (to equalize contrast on curved packaging and under uneven lighting).
* **Deep Learning OCR**: Utilizes **EasyOCR** (PyTorch) to perform high-accuracy character recognition on noisy, real-world label photos.
* **Concurrent API Scraping**: Fires parallel requests to 4 free public APIs concurrently using `asyncio.gather`, compiling data from OpenFoodFacts, OpenFDA, Wikipedia, and Wikidata.
* **Safety Scorer**: Categories ingredients using strict word boundaries into four categories:
  * ✅ **Safe**: Natural, whole foods (e.g. oats, water, fruits).
  * ⚠️ **Caution**: Processed ingredients to limit (e.g. palm oil, sugar, sodium).
  * 🚫 **Avoid**: Lab-made chemicals, artificial colors, or additives linked to hyperactivity/allergies (e.g. Red 40, MSG, Aspartame).
  * ☠️ **Toxic/Not Food**: Industrial or cleaning chemicals (e.g. bleach, isopropyl alcohol).
* **Kid-Friendly Explainer**: Simplifies complex scientific summaries (e.g. replacing words like "synthesized" with "made in a lab") and provides clear guidance.
* **Serving Limit Calculator**: Automatically extracts serving size (grams) and nutrient levels (sugar, sodium, saturated fat) from the label, calculating how many servings are safe per day for a reference **20 kg child (ages 4–8)**.
* **SQLite Cache**: Stores queried ingredients locally for **90 days** (with automatic background cleanup) so repeat scans are instant.
* **Multithreaded GUI**: Keeps the Tkinter interface fluid and responsive using a thread-safe message queue, streaming backend events (OCR progress, API fetches) in real-time.

---

## 🛠️ Tech Stack

* **Frontend**: Python Tkinter, Pillow (Image Handling)
* **Backend**: FastAPI, Uvicorn, HTTPX (Async HTTP Client)
* **Computer Vision**: OpenCV (Optional/Adaptive Preprocessing), EasyOCR (PyTorch-based OCR)
* **Fuzzy Matching**: RapidFuzz (for correcting OCR read errors against known vocabulary)
* **Database**: SQLite3
* **Testing**: Pytest

---

## 📐 Architecture

Food Detective separates concerns between its desktop GUI and its backend service:

```
[Tkinter Desktop App] <-- (SSE Stream) -- [Local FastAPI Server]
         |                                        |
 (Launches server)                        (Runs OCR in thread)
         |                                        |
         v                                        v
  [main.py Wrapper]                     [EasyOCR + Preprocessing]
                                                  |
                                          (Queries APIs / DB)
                                                  |
                                                  v
                                     [SQLite3 Cache & Public APIs]
```
For more detailed pipeline diagrams, see the [Architecture Documentation](docs/architecture.md).

---

## 📂 Folder Structure

The project is structured as a clean, modular Python package:

```
food_detective/
│
├── main.py               ← Bootstrapper (sets sys.path and runs app)
├── requirements.txt      ← Python dependencies (including Pytest & FastAPI)
├── LICENSE               ← Open-source license (MIT)
│
├── src/                  ← Source directory
│   └── food_detective/   ← Main package namespace
│       ├── main.py       ← Core coordinator (starts Uvicorn & Tkinter)
│       ├── app.py        ← FastAPI web endpoints and SSE generators
│       ├── ui.py         ← Tkinter widget layout & camera loops
│       └── modules/      ← Core business logic
│           ├── cache.py        ← SQLite connection and purge handlers
│           ├── daily_limits.py ← Safe serving thresholds and OCR unit parsers
│           ├── enricher.py     ← Asynchronous HTTP API crawlers
│           ├── explainer.py    ← Simplification templates and keyword matching
│           ├── ocr.py          ← OpenCV image filters and EasyOCR reader
│           ├── ocr_correct.py  ← Typo lookup sets and fuzzy match cutoffs
│           └── scorer.py       ← RegEx vocabulary and score evaluation
│
├── tests/                ← Unit testing suite (Pytest)
│   ├── conftest.py       ← Test path configuration
│   ├── test_cache.py     ← Database test cases
│   ├── test_explainer.py ← Explanation matching checks
│   └── test_scorer.py    ← Scoring logic checks
│
├── scripts/              ← Developer utility scripts
│   └── run.py            ← Direct runner script (auto-resolves paths)
│
├── docs/                 ← Project design documents
│   ├── architecture.md   ← System blueprints
│   └── APIS.md           ← External endpoint references
│
├── assets/               ← Visual assets & mockups
├── examples/             ← Test labels for verification
└── data/
    └── ingredients.db    ← SQLite database (ignored in git)
```

---

## 📥 Installation

### Prerequisites
* **Python 3.11+** installed on your system.
* An active internet connection (required for the first run to download model weights and libraries).

### Step 1: Clone the repository
```bash
git clone https://github.com/Peppo250/Food-Detective.git
cd Food-Detective
```

### Step 2: Set up a Virtual Environment
```bash
# Create environment
python -m venv venv

# Activate environment
# On Windows:
venv\Scripts\activate
# On macOS / Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```
> [!NOTE]
> * EasyOCR relies on **PyTorch** (~1.5 GB). The installation may take several minutes depending on your connection.
> * If `opencv-python` fails to compile on your system, you can remove it from `requirements.txt`. The application will automatically fall back to standard Pillow-based image filtering.

---

## 🎮 Usage

### Running the App
Execute the bootstrapper script from the project root:
```bash
python main.py
```
*Alternatively, you can run the developer script:*
```bash
python scripts/run.py
```

### Scanning a Label
1. **Choose Source**: Click **Pick from Files** to upload an image, or click **Take a Photo** to launch the camera preview.
2. **Align Camera (if using Webcam)**: Hold the ingredient label flat and close to the camera. Press `SPACE` to capture, or `ESC` to cancel.
3. **Analyze**: Click **Scan Ingredients!**.
4. **View Streams**: Watch the safety ratings and child-friendly explanations stream in real-time. Review the **Daily Limit Guide** panel on the right.
5. **Debug**: Toggle the **Debug / Raw Output** tab to see raw OCR reads, fuzzy matches, and API responses.

---

## ⚙️ Configuration

Key configurations are accessible in the following files:
* **Database path & TTL**: Adjusted inside [cache.py](file:///C:/Users/Porchezhian/Documents/GitHub/Food-Detective/src/food_detective/modules/cache.py). Cache duration is set via `TTL_SECONDS` (default: 90 days).
* **Reference Child Weight**: Specified inside [daily_limits.py](file:///C:/Users/Porchezhian/Documents/GitHub/Food-Detective/src/food_detective/modules/daily_limits.py) via `child_kg` (default: 20 kg).
* **API Timeouts**: Configured inside [enricher.py](file:///C:/Users/Porchezhian/Documents/GitHub/Food-Detective/src/food_detective/modules/enricher.py) via `TIMEOUT` (default: 8 seconds).

---

## 📈 Performance & Results

* **Cached Scans**: **~0.05 seconds**. Repeat scans are nearly instantaneous as they read directly from local SQLite storage.
* **Fresh Scans**: **~1.5 to 4 seconds** (depending on network latency and internet speeds), since API requests are dispatched in parallel.
* **OCR Typo Accuracy**: The integration of **RapidFuzz** provides a correction buffer for characters misread due to curved packaging (e.g. automatically matching `"barlev"` to `"barley"`).

---

## 🔮 Future Work

* **PyInstaller Executable**: Creating a single-click installer (`.exe` / `.app`) that packages Python, Tkinter, and runtime dependencies for non-technical users.
* **Barcode Scanner Integration**: Allowing users to simply scan a barcode to fetch ingredient data directly from OpenFoodFacts, bypassing OCR entirely when barcodes are clear.
* **Allergen Alert Profiles**: Letting parents configure custom profiles (e.g., "Nut Allergy" or "Gluten Sensitivity") that trigger custom warning banners regardless of safety scores.
* **Multi-Child Portions**: Adding a slider to adjust the child's age or weight (e.g. from 15kg to 40kg) to scale daily intake limits dynamically.

---

## 👥 Contributors

* **Porchezhian** (Maintainer) - [GitHub Profile](https://github.com/Peppo250)

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
