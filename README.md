# 🌿 Florae - Plant Care Tracker & Diagnosi IA

![Florae Screenshot](flore.png)

Florae è un'applicazione web locale per il tracciamento e la cura delle tue piante, integrata con un sistema di diagnostica fotografica tramite Intelligenza Artificiale (OpenAI GPT-4o-mini).

## ✨ Funzionalità principali

1. **Bacheca delle Attività**: Visualizzazione ad alta evidenza (in cima alla pagina) dei compiti urgenti da svolgere (es. piante malate o da innaffiare subito).
2. **Tracciamento Stagionale**: Consigli di cura dinamici estratti in base al mese corrente per ciascuna pianta presente nel tuo database.
3. **Database Botanico Personale**: Gestione e consultazione di schede dettagliate per ogni pianta (esposizione, irrigazione, cure generali e calendario stagionale).
4. **Diagnosi IA con Foto**: Carica una foto delle foglie o dei fusti sofferenti. L'IA riconoscerà la pianta, identificherà la malattia/problema e proporrà una cura dettagliata. Cliccando su "Applica e Salva nel Database", l'attività verrà inserita automaticamente tra le priorità urgenti in bacheca!
5. **Simulazione Intelligente**: Se non hai ancora una chiave OpenAI API, l'app simulerà diagnosi botaniche incredibilmente realistiche per farti testare il funzionamento. Puoi inserire la tua chiave reale direttamente dalla pagina delle impostazioni dell'app.

---

## 🚀 Come avviare l'applicazione in locale

L'applicazione è scritta in Python con il framework Flask ed è pronta per essere avviata.

### 1. Prerequisiti
Assicurati di avere Python installato sul tuo computer. Puoi verificarlo aprendo il Terminale e digitando:
```bash
python3 --version
```

### 2. Configura l'ambiente e installa le dipendenze
Apri il **Terminale** sul tuo Mac e spostati nella cartella del progetto:
```bash
cd ~/Desktop/plant-tracker
```

Crea un ambiente virtuale (consigliato per non interferire con altri progetti):
```bash
python3 -m venv venv
source venv/bin/activate
```

Installa le dipendenze richieste:
```bash
pip install -r requirements.txt
```

### 3. Avvia l'applicazione
Esegui lo script principale:
```bash
python3 app.py
```

### 4. Apri il browser
Una volta avviata, l'applicazione sarà disponibile al seguente indirizzo (la porta 5001 evita conflitti con AirPlay su macOS):
👉 **[http://127.0.0.1:5001](http://127.0.0.1:5001)**

---

## 🛠️ Configurazione Chiave API OpenAI (Opzionale)
Per sbloccare la vera intelligenza artificiale per l'analisi delle foto:
1. Avvia l'app e vai alla pagina **Impostazioni** dal menu laterale.
2. Incolla la tua chiave API di OpenAI (inizia con `sk-...`).
3. Clicca su **Salva Configurazione**. Da questo momento, l'app utilizzerà il modello di visione `gpt-4o-mini` per diagnosticare le immagini reali che carichi!
