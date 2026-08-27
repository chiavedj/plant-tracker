e il versioning segue [Semantic Versioning](https://semver.org/lang/it/).

## [1.6.0] – 2025-08-26

### Aggiunto
- **Bacheca / Altre cose da fare raggruppabili per pianta**: aggiunto anche alla sezione "Altre cose da fare" l'interruttore *"Raggruppa per pianta"* / *"Elenca"*, identico a quello già presente per "In Evidenza"
  - Card comprimibili per pianta con contatore compiti e badge `💧 Auto`
  - Preferenza salvata separatamente nel browser (`localStorage.florae_pending_view`)



## [1.5.5] – 2025-08-26

### Corretto
- **Chatbot: eliminazione definitiva e categorica di qualsiasi traccia di ragionamento e scratchpad in inglese** — riscritto il motore di estrazione per individuare esattamente la prima riga di risposta utile in italiano ed eliminare al 100% tutte le note di pianificazione (`* Role:`, `* Context:`, `* General watering rule:`, `* Check soil with a finger`, ecc.)



## [1.5.4] – 2025-08-26

### Corretto
- **Chatbot / Gemma 4: estrazione deterministica della risposta italiana** — rimpiazzato l'approccio regex precedente con un parser per lingua che individua esattamente il punto in cui inizia la risposta reale in italiano, eliminando al 100% qualsiasi scratchpad, bozza o planning in inglese



## [1.5.3] – 2025-08-26

### Corretto
- **Chatbot / Gemma 4: eliminazione totale dello scratchpad di ragionamento** — risolto il problema per cui Gemma continuava a mostrare sezioni `Persona:`, `App:`, `User's Plants:`, `Self-Correction` e blocchi duplicati prima della risposta vera



## [1.5.2] – 2025-08-26

### Corretto
- **Gemma mostrava tutto il ragionamento interno** (persona, opzioni valutate, drafting, word count) prima della risposta vera. Ora la chat applica una pulizia automatica che:
  - taglia i blocchi di ragionamento e gli appunti interni del modello
  - individua la risposta finale anche quando Gemma la ripete più volte (deduplicazione dei blocchi simili)
  - non altera in alcun modo le risposte normali già pulite

### Nota
- Le release 1.5.0/1.5.1 contenevano già queste correzioni di codice ma con costante di versione errata (1.4.0)



## [1.5.1] – 2025-08-26

### Corretto
- **Chatbot (Google/Gemma): il contesto delle piante non veniva inviato** — il bot diceva "non conosco le tue piante". Ora istruzioni + elenco piante reali vengono iniettati nel primo turno della conversazione
- **Gemma mostrava il ragionamento interno** (opzioni, appunti in inglese) invece della sola risposta: aggiunte istruzioni esplicite anti-rivelazione nel prompt di sistema



## [1.5.0] – 2025-08-26

### Corretto
- **Chatbot: falsi "timeout" eliminati** — gli errori reali dell'API venivano nascosti e mascherati da "Non sono riuscito a rispondere entro 3 minuti" anche quando fallivano subito. Ora:
  - gli errori vengono mostrati chiaramente in chat (es. modello non trovato)
  - se il modello selezionato non è disponibile, **riprova automaticamente** con quello consigliato del provider e lo segnala nel messaggio
  - l'errore completo viene loggato nei container log per il debug



## [1.4.0] – 2025-08-26

### Aggiunto
- **Gemma 4 31B** (gratuito) nel listino Google — il modello gratuito più potente
- Indicatore di attesa in chat con secondi trascorsi e suggerimenti sui modelli gratuiti

### Modificato
- **Timeout della chat portato da 45s a 180s**: i modelli gratuiti grandi (Gemma 3 27B / Gemma 4 31B) possono richiedere qualche minuto — ora il bot aspetta la risposta invece di arrendersi



## [1.3.1] – 2025-08-26

### Corretto
- La costante `__version__` non era stata aggiornata nel rilascio precedente (segnalava ancora 1.3.0)
- Nota: la release 1.2.1 (vista urgente raggruppabile) è stata pubblicata dopo la 1.3.0 con numerazione errata — **il codice più recente è quello con numero più alto da qui in avanti**

### Aggiunto
- Vista urgente raggruppabile per pianta (introdotta nella 1.2.1, inclusa qui per chiarezza di versione)

## [1.3.0] – 2025-08-26

### Aggiunto
- **🤖 Chat col Botanico IA**: nuova pagina "Botanico IA" nel menu. Chatta con un agronomo virtuale che:
  - conosce tutte le piante del tuo tracker (nomi, specie, frequenze di annaffiatura)
  - usa il provider e il modello che hai scelto nelle impostazioni
  - mantiene la conversazione per tutta la sessione (con pulsante "Azzera")
  - timeout di 45s: mai attese infinite
- **☀️ Meteo in dashboard** (Open-Meteo, gratuito, nessuna chiave API):
  - temperatura attuale + previsioni 4 giorni della tua città
  - allerta rossa rischio gelate (proteggi le piante esterne!)
  - consiglio intelligente: se piove ≥2mm suggerisce di saltare l'annaffiatura manuale
  - si configura dalla pagina Impostazioni con il solo nome città; cache 30 min
- **🔔 Notifiche Telegram**: avvisi automatici su Telegram quando vengono programmate innaffiature e quando una diagnosi crea un compito urgente
  - token bot + Chat ID configurabili nelle Impostazioni con pulsante "Messaggio di prova"
  - invii asincroni: non rallentano mai l'app

## [1.2.0] – 2025-08-26

### Aggiunto
- **💧 Innaffiature ricorrenti automatiche**: per ogni pianta puoi impostare la frequenza (in giorni) e Florae genera da sola il compito "Innaffia" nella bacheca quando è ora
  - Nessun duplicato: se un compito è già in attesa non ne crea altri
  - Rispetta l'intervallo: dopo aver completato l'annaffiatura attende X giorni prima di riprogrammare
  - Badge "💧 Automatica" sui compiti generati in dashboard
- Nuovo campo nel form piante con spiegazione integrata

## [1.1.2] – 2025-08-24

### Aggiunto
- Modelli **Gemma gratuiti** nel listino Google: Gemma 3 27B e Gemma 3 12B

### Corretto
- **Wishlist lentissima**: l'IA veniva chiamata ad ogni apertura pagina. Ora:
  - timeout di 20 secondi sulle chiamate IA (mai più pagine in caricamento infinito)
  - cache dei suggerimenti stagionali per 6 ore (prima apertura lenta, poi istantanea)
  - stesso trattamento per il consiglio d'acquisto aggiunto alla wishlist

## [1.1.1] – 2025-08-24

### Aggiunto
- Immagine Docker ufficiale pubblicata automaticamente su GitHub Container Registry (`ghcr.io/chiavedj/plant-tracker`) ad ogni nuova versione
- `Dockerfile`, `docker-compose.yml` e `.dockerignore` per deployment su server/NAS (ZimaOS incluso)
- Volumi persistenti documentati per database (`/app/instance`) e foto caricate (`/app/static/uploads`)

### Modificato
- Modalità debug di Flask disattivata nel container (variabile `FLASK_DEBUG=0`), attiva di default solo in sviluppo locale

## [1.1.0] – 2025-08-24

### Aggiunto
- Selezione del modello IA nella pagina Impostazioni, con listino diviso per provider:
  - **OpenAI**: GPT-4o mini, GPT-4.1 nano, GPT-4.1 mini, GPT-4o
  - **Google**: Gemini 3.6 Flash, Gemini 2.5 Flash, Gemini Flash Latest
- Badge "Consigliato" sul modello economico e descrizione costo per ogni voce
- Colonna `ai_model` nel database con migrazione automatica all'avvio
- Helper `get_selected_model()` con fallback automatico al modello consigliato
- Helper `clean_ai_json()` per parsing robusto delle risposte IA
- Placeholder immagine per piante senza foto (`static/img/placeholder.svg`)
- Banner dedicato agli errori API nella pagina di diagnosi

### Corretto
- Crash su `/diagnose` con pianta eliminata o ID non valido
- Crash su `/diagnose/apply` quando la pianta indicata non esiste più (ora crea una pianta nuova)
- Crash su aggiunta/modifica pianta senza nome (validazione + messaggio)
- Crash su creazione attività senza titolo o con `plant_id` non valido
- Diagnosi Gemini senza flag `is_mock` (return anticipato rimosso)
- Modelli Google deprecati (`gemini-2.0-flash`) sostituiti con auto-migrazione
- Le chiavi API non vengono più cancellate salvando le impostazioni con campi vuoti
- Nomi file upload svuotati da `secure_filename` (fallback automatico)
- Default stagionali applicati anche quando i campi sono inviati vuoti

## [1.0.0] – 2025-07-26

### Aggiunto
- Dashboard attività con sezione urgente evidenziata
- Database piante con schede dettagliate e calendario di cura stagionale
- Diagnosi foto tramite IA (OpenAI / Google Gemini)
- Modalità simulazione realistica senza chiave API
- Wishlist piante con suggerimento IA sul periodo d'acquisto migliore
- Suggerimenti stagionali di piante consigliate
