# 🌿 Florae - Plant Care Tracker & AI Diagnosis

![Florae Screenshot](flore.png)

Florae is a local-first web application for tracking and caring for your plants, integrated with an AI-powered photo diagnosis system (OpenAI GPT-4o-mini).

## ✨ Key Features

1. **Activity Dashboard**: High-visibility panel (top of the page) showing urgent tasks — sick plants or those needing immediate watering.
2. **Seasonal Care Tracking**: Dynamic care tips based on the current month for each plant in your database.
3. **Personal Botanical Database**: Manage and browse detailed plant cards (light exposure, watering needs, general care, seasonal calendar).
4. **AI Photo Diagnosis**: Upload a photo of struggling leaves or stems. The AI identifies the plant, diagnoses the disease/problem, and suggests a detailed treatment. Click "Apply & Save to Database" to automatically add the task to your urgent dashboard!
5. **Smart Simulation Mode**: No OpenAI API key yet? The app simulates incredibly realistic botanical diagnoses so you can test the full workflow. Add your real key anytime from the Settings page.

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

## 🛠️ OpenAI API Key Setup (Optional)

To enable real AI-powered photo analysis:
1. Launch the app and go to **Settings** from the sidebar.
2. Paste your OpenAI API key (starts with `sk-...`).
3. Click **Save Configuration**. The app will now use the `gpt-4o-mini` vision model for real image diagnosis!