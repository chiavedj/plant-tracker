# Changelog

Tutte le modifiche importanti a questo progetto vengono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/)
e il versioning segue [Semantic Versioning](https://semver.org/lang/it/).

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
