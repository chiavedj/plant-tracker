# 🌿 Florae - Plant Care Tracker & AI Diagnosis

![Version](https://img.shields.io/badge/version-1.2.0-emerald) ![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Flask](https://img.shields.io/badge/flask-3.0-grey) ![License](https://img.shields.io/badge/license-MIT-green) ![Docker](https://img.shields.io/badge/docker-ghcr.io-2496ED)

![Florae Screenshot](flore.png)

Florae is a local-first web application for tracking and caring for your plants, integrated with an AI-powered photo diagnosis system. Choose your favorite AI provider (**OpenAI** or **Google Gemini**) and pick the **model that fits your budget** — from ultra-cheap mini/flash models up to premium ones.

## ✨ Key Features

1. **Activity Dashboard**: High-visibility panel (top of the page) showing urgent tasks — sick plants or those needing immediate watering.
2. **Automatic Watering Reminders** 🆕: set a watering frequency (in days) for each plant and Florae automatically creates the "💧 Water" task on your dashboard when it's time — complete it, and the next one schedules itself.
2. **Seasonal Care Tracking**: Dynamic care tips based on the current month for each plant in your database.
3. **Personal Botanical Database**: Manage and browse detailed plant cards (light exposure, watering needs, general care, seasonal calendar).
4. **AI Photo Diagnosis**: Upload a photo of struggling leaves or stems. The AI identifies the plant, diagnoses the disease/problem, and suggests a detailed treatment. Click "Apply & Save to Database" to automatically add the task to your urgent dashboard!
5. **AI Model Selection** 🆕: From the Settings page, choose exactly which AI model to use — cheap options like *GPT-4o mini* or *Gemini Flash* are recommended and cost only a fraction of premium models.
6. **Smart Simulation Mode**: No API key yet? The app simulates incredibly realistic botanical diagnoses so you can test the full workflow. Add your real key anytime from the Settings page.

---

## 🚀 Getting Started (Local Setup)

Built with Python and Flask — ready to run locally.

### 1. Prerequisites
Ensure Python 3 is installed:
```bash
python3 --version
```

### 2. Set Up Environment & Install Dependencies
Open **Terminal** and navigate to the project folder:
```bash
cd ~/Desktop/plant-tracker
```

Create a virtual environment (recommended to avoid conflicts):
```bash
python3 -m venv venv
source venv/bin/activate
```

Install required packages:
```bash
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python3 app.py
```

### 4. Open in Browser
The app runs on port **5001** (avoids AirPlay conflict on macOS):
👉 **[http://127.0.0.1:5001](http://127.0.0.1:5001)**

---

## 🐳 Deploy con Docker / ZimaOS

L'app è disponibile come immagine Docker pronta su GitHub Container Registry.

**Su ZimaOS:**
1. Apri il pannello App/Docker di ZimaOS e crea (o modifica) l'app usando questa immagine:
   ```
   ghcr.io/chiavedj/plant-tracker:latest
   ```
2. Mappa la porta **5001** (es. `5001:5001`).
3. Aggiungi un volume per il database: `/app/instance` → così i tuoi dati sopravvivono agli aggiornamenti.
4. Quando esce una nuova versione, aggiorna l'immagine da ZimaOS e ricrea il container: le impostazioni e i dati restano al loro posto.

**Con docker-compose** (su qualunque server):
```bash
docker compose up -d
```
Il file `docker-compose.yml` nel repo è già configurato con volumi persistenti per database (`florae-data`) e foto caricate (`florae-uploads`).

> ⚠️ Dopo un aggiornamento dell'immagine, fai sempre un hard refresh del browser (`Cmd/Ctrl+Shift+R`) per non vedere pagine vecchie dalla cache.

---

## 🛠️ AI Provider & Model Setup (Optional)

To enable real AI-powered photo analysis:
1. Launch the app and go to **Settings** from the sidebar.
2. Pick your **provider**: OpenAI or Google Gemini.
3. Paste your API key:
   - **OpenAI** → starts with `sk-...`, get one at [platform.openai.com](https://platform.openai.com/)
   - **Google** → starts with `AIzaSy...`, get one at [aistudio.google.com](https://aistudio.google.com/)
4. Choose the **AI model** from the list — budget models (mini / flash / nano) work great for plant diagnosis at a fraction of the cost.
5. Click **Save Configuration**. Done! 🌱

> 💡 Keys are updated only when you type something in the field — leaving it blank keeps the previously saved key.