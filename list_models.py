import os
import google.generativeai as genai
from flask import session
from app import app

# Usiamo l'app context per accedere alla sessione o variabili d'ambiente
with app.app_context():
    # Prova a prendere la chiave dall'ambiente o impostala manualmente se necessario
    api_key = os.environ.get('GOOGLE_API_KEY') 
    if not api_key:
        print("ERRORE: GOOGLE_API_KEY non trovata nelle variabili d'ambiente.")
        print("Per favore, imposta la chiave prima di eseguire: export GOOGLE_API_KEY='tua_chiave'")
    else:
        genai.configure(api_key=api_key)
        print(f"Chiave API configurata. Elenco modelli disponibili per generateContent:\n")
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    print(f"Nome: {m.name}")
        except Exception as e:
            print(f"Errore durante l'elenco dei modelli: {e}")
