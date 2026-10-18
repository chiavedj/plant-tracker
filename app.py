import os
import re
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import json
import threading
import time
import uuid
import requests
import google.generativeai as genai
import io
from PIL import Image

__version__ = "1.8.4"  # Fonte unica della versione (vedi CHANGELOG.md)

app = Flask(__name__)
app.secret_key = "plant_tracker_super_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///plants.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Ensure upload directory exists
os.makedirs(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']), exist_ok=True)

db = SQLAlchemy(app)

# Database Models
class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(100), nullable=True)
    exposure = db.Column(db.String(150), nullable=True)  # Sole, Ombra, Mezz'ombra, Luce Indiretta, ecc.
    watering = db.Column(db.String(250), nullable=True)  # Frequenza e modalità
    care = db.Column(db.Text, nullable=True)             # Istruzioni generali
    
    # Seasonal Care Istruzioni
    spring_care = db.Column(db.Text, nullable=True)
    summer_care = db.Column(db.Text, nullable=True)
    autumn_care = db.Column(db.Text, nullable=True)
    winter_care = db.Column(db.Text, nullable=True)
    
    image_url = db.Column(db.String(250), nullable=True)
    watering_frequency_days = db.Column(db.Integer, nullable=True)  # Innaffiatura automatica: intervallo in giorni
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to tasks
    tasks = db.relationship('Task', backref='plant', lazy=True, cascade="all, delete-orphan")

class WishlistPlant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(100), nullable=True)
    best_time = db.Column(db.Text, nullable=True)  # AI recommendation
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.String(50), nullable=True)  # Data o intervallo temporale
    is_urgent = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed
    task_type = db.Column(db.String(20), nullable=True)   # None = manuale, 'watering' = innaffiatura automatica
    completed_at = db.Column(db.DateTime, nullable=True)  # Quando è stata completata (per la ricorrenza)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Modelli gratuiti OpenRouter curati a mano: usati come fallback se il
# caricamento live dall'API non è disponibile. La disponibilità dei modelli
# gratuiti cambia spesso, per questo l'app prova ad aggiornare la lista da sola.
_OPENROUTER_CURATED = [
    {'id': 'nvidia/nemotron-3.5-super-vl:free', 'name': 'Nemotron 3.5 Super VL', 'desc': 'VISION · GRATUITO — affidabile e specializzato nelle immagini (consigliato)', 'icon': 'fa-gift', 'vision': True},
    {'id': 'google/gemma-4-31b-it:free', 'name': 'Gemma 4 31B', 'desc': 'VISION · GRATUITO — qualità elevata', 'icon': 'fa-gift', 'vision': True},
    {'id': 'google/gemma-4-26b-a4b-it:free', 'name': 'Gemma 4 26B', 'desc': 'VISION · GRATUITO — leggero e veloce', 'icon': 'fa-gift', 'vision': True},
    {'id': 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', 'name': 'Nemotron 3 Nano Omni', 'desc': 'VISION · GRATUITO — con ragionamento', 'icon': 'fa-gift', 'vision': True},
    {'id': 'nvidia/nemotron-3-super-120b-a12b:free', 'name': 'Nemotron 3 Super 120B', 'desc': 'GRATUITO — solo testo, per la chat', 'icon': 'fa-comments', 'vision': False},
    {'id': 'nvidia/nemotron-3.5-lightning:free', 'name': 'Nemotron 3.5 Lightning', 'desc': 'GRATUITO — solo testo, chat veloce', 'icon': 'fa-comments', 'vision': False},
]

# Modelli IA disponibili, suddivisi per provider
# 'vision': True  -> il modello analizza anche le immagini (diagnosi foto)
# 'vision': False -> solo testo (chat, consigli, suggerimenti)
AI_MODELS = {
    'openai': [
        {'id': 'gpt-4o-mini', 'name': 'GPT-4o mini', 'desc': 'Economico e veloce (consigliato)', 'icon': 'fa-feather', 'vision': True},
        {'id': 'gpt-4.1-nano', 'name': 'GPT-4.1 nano', 'desc': 'Il più economico in assoluto', 'icon': 'fa-seedling', 'vision': True},
        {'id': 'gpt-4.1-mini', 'name': 'GPT-4.1 mini', 'desc': 'Buon compromesso qualità/prezzo', 'icon': 'fa-scale-balanced', 'vision': True},
        {'id': 'gpt-4o', 'name': 'GPT-4o', 'desc': 'Massima qualità, più costoso', 'icon': 'fa-gem', 'vision': True},
    ],
    'google': [
        {'id': 'models/gemini-3.6-flash', 'name': 'Gemini 3.6 Flash', 'desc': 'Veloce ed economico (consigliato)', 'icon': 'fa-feather', 'vision': True},
        {'id': 'models/gemini-2.5-flash', 'name': 'Gemini 2.5 Flash', 'desc': 'Più intelligente, costo moderato', 'icon': 'fa-scale-balanced', 'vision': True},
        {'id': 'models/gemini-flash-latest', 'name': 'Gemini Flash Latest', 'desc': 'Ultima versione flash disponibile', 'icon': 'fa-wand-magic-sparkles', 'vision': True},
        {'id': 'models/gemma-4-31b-it', 'name': 'Gemma 4 31B', 'desc': 'GRATUITO — solo testo, non vede le foto', 'icon': 'fa-gift', 'vision': False},
        {'id': 'models/gemma-3-27b-it', 'name': 'Gemma 3 27B', 'desc': 'GRATUITO — solo testo, non vede le foto', 'icon': 'fa-gift', 'vision': False},
        {'id': 'models/gemma-3-12b-it', 'name': 'Gemma 3 12B', 'desc': 'GRATUITO — solo testo, non vede le foto', 'icon': 'fa-gift', 'vision': False},
    ],
    # OpenRouter: aggregatore di modelli gratuiti ("...:free").
    # I modelli VISION vedono le immagini e sono adatti alla diagnosi foto.
    # NB: la lista viene aggiornata automaticamente dall'API (vedi
    # fetch_openrouter_free_models); questa è la versione di partenza
    # (all'avvio, prima del primo aggiornamento).
    'openrouter': list(_OPENROUTER_CURATED)
}

def vision_models(provider):
    """Modelli del provider in grado di analizzare le immagini."""
    return [m for m in AI_MODELS.get(provider, []) if m.get('vision')]


# Cache dei modelli gratuiti OpenRouter scaricati dall'API (6 ore)
_OR_MODELS_CACHE = {'ts': 0.0, 'models': None}
_OR_MODELS_TTL = 60 * 60 * 6

def fetch_openrouter_free_models(force=False):
    """Scarica l'elenco LIVE dei modelli gratuiti di OpenRouter e aggiorna
    AI_MODELS['openrouter']. I modelli gratuiti cambiano spesso: aggiornando
    automaticamente la lista si evitano errori "modello non più disponibile".
    Se la rete fallisce, resta la lista curata (_OPENROUTER_CURATED)."""
    import json as _json
    now = time.time()
    cached = _OR_MODELS_CACHE
    if not force and cached['models'] and (now - cached['ts']) < _OR_MODELS_TTL:
        return cached['models']

    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        data = r.json().get('data', [])

        live_free = {}   # id -> nome leggibile
        for m in data:
            mid = m.get('id', '')
            if ':free' not in mid:
                continue
            # Esclude modelli non adatti alle piante (sicurezza contenuti, codice)
            if any(x in mid for x in ['content-safety', 'code', 'coder']):
                continue
            live_free[mid] = m

        def is_vision(mid):
            arch = (live_free[mid].get('architecture') or {})
            return 'image' in (arch.get('input_modalities') or [])

        # 1) Prima i modelli curati che sono ANCORA gratuiti (mantengono il nome
        #    e l'ordine con cui li conosciamo), poi gli altri scoperti live.
        models = []
        seen = set()
        for c in _OPENROUTER_CURATED:
            if c['id'] in live_free:
                models.append(dict(c))
                seen.add(c['id'])

        live_vision = [mid for mid in live_free if mid not in seen and is_vision(mid)]
        live_text = [mid for mid in live_free if mid not in seen and not is_vision(mid)]
        for mid in live_vision[:8]:
            models.append({'id': mid, 'name': live_free[mid].get('name') or mid,
                           'desc': 'VISION · GRATUITO', 'icon': 'fa-gift', 'vision': True})
        for mid in live_text[:6]:
            models.append({'id': mid, 'name': live_free[mid].get('name') or mid,
                           'desc': 'GRATUITO — solo testo', 'icon': 'fa-comments', 'vision': False})

        if models:
            AI_MODELS['openrouter'] = models
            _OR_MODELS_CACHE['ts'] = now
            _OR_MODELS_CACHE['models'] = models
            print(f"OpenRouter: aggiornati {len(models)} modelli gratuiti dall'API")
            return models
    except Exception as e:
        print(f"OpenRouter: aggiornamento modelli non riuscito ({e}) — uso la lista curata")

    return _OR_MODELS_CACHE['models'] or list(_OPENROUTER_CURATED)


def _needs_model_choice(provider, preferred, error):
    """Risultato speciale: il modello scelto non ha risposto.
    Non cambiamo modello da soli: chiediamo all'utente (vedi diagnose_choice)."""
    alternatives = [
        {'id': m['id'], 'name': m['name'], 'desc': m['desc']}
        for m in vision_models(provider)
        if m['id'] != preferred
    ]
    # Suggerimento utile quando l'errore è un limite di utilizzo (tipico dei
    # modelli gratuiti su OpenRouter) oppure un modello non più disponibile
    low = (error or '').lower()
    if '429' in low or 'rate limit' in low or 'quota' in low:
        hint = ("Il modello gratuito ha raggiunto il limite di utilizzo. "
                "Aspetta qualche minuto oppure scegli un altro modello qui sotto.")
    elif '404' in low or 'unavailable' in low or 'not found' in low:
        hint = ("Questo modello non è più disponibile su OpenRouter. "
                "Scegline un altro qui sotto (o aggiorna la lista nelle Impostazioni).")
    else:
        hint = "Scegli un altro modello qui sotto per riprovare."
    return {
        "status": "needs_model_choice",
        "is_mock": False,
        "message": hint,
        "preferred_model_id": preferred,
        "preferred_model_name": _get_model_display_name(preferred),
        "failed_error": error,
        "alternatives": alternatives,
    }

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ai_provider = db.Column(db.String(50), default='openai')
    ai_model = db.Column(db.String(100), nullable=True)  # Modello scelto dall'utente
    openai_api_key = db.Column(db.String(500), nullable=True)
    google_api_key = db.Column(db.String(500), nullable=True)
    openrouter_api_key = db.Column(db.String(500), nullable=True)
    weather_city = db.Column(db.String(100), nullable=True)      # Città per il meteo
    telegram_bot_token = db.Column(db.String(500), nullable=True) # Token bot Telegram
    telegram_chat_id = db.Column(db.String(100), nullable=True)   # Chat ID per le notifiche

# Helper to get the AI model chosen by the user for a given provider
def get_selected_model(settings, provider):
    """Restituisce il modello scelto dall'utente, oppure il primo consigliato."""
    saved = (settings.ai_model or '').strip()
    valid_ids = [m['id'] for m in AI_MODELS.get(provider, [])]
    if saved in valid_ids:
        return saved
    # Default: primo modello della lista (sempre quello economico/consigliato)
    return valid_ids[0] if valid_ids else None


# OpenRouter espone un'API compatibile con OpenAI: basta cambiare base_url.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

def get_openrouter_client(api_key):
    """Client OpenAI-compatibile puntato su OpenRouter."""
    import openai
    return openai.OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/chiavedj/plant-tracker",
            "X-Title": "Florae Plant Tracker",
        },
    )


def get_openai_compatible_client(provider, api_key):
    """Client per i provider che parlano l'API OpenAI (OpenAI e OpenRouter)."""
    if provider == 'openrouter':
        return get_openrouter_client(api_key)
    import openai
    return openai.OpenAI(api_key=api_key)


def ai_json_completion(client, model, messages, max_tokens=1000):
    """Chiamata chat che deve restituire JSON.
    Prova prima a forzare il formato JSON (response_format), ma se il modello
    non lo supporta (molti modelli gratuiti, es. certi Nemotron) riprova senza:
    in quel caso ci affidiamo a clean_ai_json per estrarre il JSON dal testo."""
    base_kwargs = dict(model=model, messages=messages, max_tokens=max_tokens)
    try:
        resp = client.chat.completions.create(
            response_format={"type": "json_object"}, **base_kwargs)
    except Exception as e:
        print(f"response_format non supportato da {model} ({str(e)[:120]}) — riprovo senza")
        resp = client.chat.completions.create(**base_kwargs)
    return json.loads(clean_ai_json(resp.choices[0].message.content))


def provider_api_key(settings):
    """Restituisce (provider, api_key) in base alle impostazioni salvate."""
    provider = settings.ai_provider or 'openai'
    if provider == 'openai':
        key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY')
    elif provider == 'google':
        key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY')
    else:  # openrouter
        key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY')
    return provider, key


# Helper to get/init app settings
def get_app_settings():
    setting = Settings.query.first()
    if not setting:
        setting = Settings(ai_provider='openai')
        db.session.add(setting)
        db.session.commit()
    return setting

def clean_ai_json(text):
    """Rimuove eventuali blocchi di codice markdown dalla risposta dell'IA."""
    text = (text or '').strip()
    # Rimuove fence ```json ... ``` oppure ``` ... ```
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: estrae il primo blocco { ... } valido
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        return text[start:end+1]
    return text

# Timeout per le chiamate IA: se l'API non risponde entro N secondi si usa il
# fallback, così le pagine non restano MAI in caricamento all'infinito
AI_CALL_TIMEOUT_SECONDS = 20
CHAT_TIMEOUT_SECONDS = 180  # La chat può aspettare di più: modelli grandi come Gemma 27B sono lenti ma completi

# Cache dei suggerimenti stagionali della wishlist (evita di chiamare l'IA
# ad ogni apertura pagina). Scade dopo 6 ore.
_SUGGESTIONS_CACHE = {}
_SUGGESTIONS_CACHE_TTL = 60 * 60 * 6

# --- DIAGNOSI ASINCRONA (anti "pagina non raggiungibile / scaduta") ---
# L'analisi IA gira in un thread in background e il frontend fa polling.
# Se il telefono va in standby durante l'analisi, il polling riprende al
# risveglio e il risultato arriva comunque: il POST non muore mai.
diagnosis_jobs = {}            # job_id -> dict di stato
_diagnosis_jobs_lock = threading.Lock()
_DIAGNOSIS_JOBS_TTL = 60 * 60  # i job completati restano in memoria 1 ora


def _prune_diagnosis_jobs():
    """Rimuove i job completati più vecchi di 1 ora per liberare memoria."""
    now = time.time()
    with _diagnosis_jobs_lock:
        for jid in [j for j, v in diagnosis_jobs.items()
                    if v.get('finished_at') and now - v['finished_at'] > _DIAGNOSIS_JOBS_TTL]:
            diagnosis_jobs.pop(jid, None)


def _get_model_display_name(model_id):
    """Converte un ID modello interno (es. models/gemma-4-31b-it) in nome leggibile."""
    for provider_models in AI_MODELS.values():
        for m in provider_models:
            if m['id'] == model_id:
                return m['name']
    return (model_id or 'IA').replace('models/', '').replace('-', ' ').title()


def _set_job(job_id, **fields):
    """Aggiorna in sicurezza lo stato di un job di diagnosi."""
    with _diagnosis_jobs_lock:
        job = diagnosis_jobs.get(job_id)
        if job is not None:
            job.update(fields)


def _run_diagnosis_job(job_id, image_path, plant_name, species, model_override=None):
    """Esegue l'analisi IA in background e aggiorna lo stato del job.
    Se il thread muore per un'eccezione inattesa, il job finisce in errore
    (il frontend mostra il messaggio invece di restare in attesa eterna)."""
    # Il thread non eredita il contesto applicazione di Flask:
    # senza app_context() l'accesso al database (get_app_settings) fallirebbe.
    with app.app_context():
        try:
            result = analyze_plant_image(image_path, plant_name, species,
                                         model_override=model_override)
            if result.get('status') == 'needs_model_choice':
                new_status = 'needs_choice'
            elif result.get('status') == 'error':
                new_status = 'error'
            else:
                new_status = 'complete'
            _set_job(job_id, result=result, status=new_status, finished_at=time.time())
        except Exception as e:
            import traceback
            traceback.print_exc()
            _set_job(job_id,
                     result={
                         "status": "error",
                         "message": f"Errore inatteso durante l'analisi: {str(e)}",
                         "is_mock": False,
                         "plant_name": plant_name or "Pianta generica",
                         "problem": "Diagnosi non disponibile",
                         "details": "",
                         "solution": "",
                         "urgency": "Media",
                         "exposure_rules": "",
                         "watering_rules": "",
                     },
                     status='error',
                     finished_at=time.time())

def run_with_timeout(func, timeout_seconds=AI_CALL_TIMEOUT_SECONDS, raise_on_error=False):
    """Esegue func() in un thread separato.
    - Timeout scaduto -> restituisce None
    - Eccezione interna -> restituisce None (e logga), OPPURE rilancia se raise_on_error=True
    """
    result = {}
    def _target():
        # Il thread non eredita il contesto Flask: lo riapriamo qui
        # così func() può usare database e configurazione in sicurezza.
        with app.app_context():
            try:
                result['value'] = func()
            except Exception as e:
                import traceback
                traceback.print_exc()
                result['error'] = e
    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_seconds)
    if t.is_alive():
        print(f"Chiamata IA interrotta dopo {timeout_seconds}s di attesa")
        return None
    if 'error' in result:
        if raise_on_error:
            raise result['error']
        print(f"Errore chiamata IA: {result['error']}")
        return None
    return result.get('value')

# --- METEO (Open-Meteo: gratuito, senza chiave API) ---

_WEATHER_CACHE = {'ts': 0, 'data': None}
_WEATHER_CACHE_TTL = 60 * 30  # 30 minuti
_GEOCODE_CACHE = {}

WEATHER_CODES = {
    0: ('Sereno', 'fa-sun'), 1: ('Poco nuvoloso', 'fa-cloud-sun'), 2: ('Parzialmente nuvoloso', 'fa-cloud-sun'),
    3: ('Nuvoloso', 'fa-cloud'), 45: ('Nebbia', 'fa-smog'), 48: ('Nebbia', 'fa-smog'),
    51: ('Pioviggine', 'fa-cloud-rain'), 53: ('Pioviggine', 'fa-cloud-rain'), 55: ('Pioviggine', 'fa-cloud-rain'),
    61: ('Pioggia leggera', 'fa-cloud-rain'), 63: ('Pioggia', 'fa-cloud-showers-heavy'), 65: ('Pioggia forte', 'fa-cloud-showers-heavy'),
    71: ('Neve', 'fa-snowflake'), 73: ('Neve', 'fa-snowflake'), 75: ('Neve', 'fa-snowflake'),
    80: ('Rovesci', 'fa-cloud-showers-heavy'), 81: ('Rovesci', 'fa-cloud-showers-heavy'), 82: ('Rovesci forti', 'fa-cloud-showers-water'),
    95: ('Temporale', 'fa-bolt'), 96: ('Temporale grandine', 'fa-bolt'), 99: ('Temporale grandine', 'fa-bolt'),
}

def _geocode_city(city):
    """Converte il nome città in coordinate via Open-Meteo Geocoding (con cache)."""
    if city in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[city]
    loc = None
    try:
        r = requests.get(
            'https://geocoding-api.open-meteo.com/v1/search',
            params={'name': city, 'count': 1, 'language': 'it', 'format': 'json'},
            timeout=10
        )
        results = r.json().get('results') or []
        if results:
            loc = {'lat': results[0]['latitude'], 'lon': results[0]['longitude'],
                   'name': results[0].get('name', city)}
    except Exception as e:
        print(f'Errore geocoding "{city}": {e}')
    _GEOCODE_CACHE[city] = loc
    return loc

def get_weather():
    """Meteo attuale + previsioni 4 giorni per la città configurata. None se non configurato."""
    settings = get_app_settings()
    city = (settings.weather_city or '').strip()
    if not city:
        return None
    
    now_ts = time.time()
    if _WEATHER_CACHE['data'] and (now_ts - _WEATHER_CACHE['ts']) < _WEATHER_CACHE_TTL:
        return _WEATHER_CACHE['data']
    
    loc = _geocode_city(city)
    if not loc:
        return {'error': f'Non riesco a trovare la città "{city}"'}
    
    try:
        r = requests.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude': loc['lat'], 'longitude': loc['lon'],
                'current': 'temperature_2m',
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code',
                'timezone': 'auto', 'forecast_days': 4,
            },
            timeout=10
        )
        j = r.json()
    except Exception as e:
        print(f'Errore meteo: {e}')
        return None
    
    daily = j.get('daily', {})
    dates = daily.get('time', [])
    tmax = daily.get('temperature_2m_max', [])
    tmin = daily.get('temperature_2m_min', [])
    pprob = daily.get('precipitation_probability_max', [])
    psum = daily.get('precipitation_sum', [])
    wcode = daily.get('weather_code', [])
    
    weather = {
        'city': loc['name'],
        'temp': j.get('current', {}).get('temperature_2m'),
        'today_rain_mm': psum[0] if psum else None,
        'days': [],
        'frost_alert': False,
        'rain_hint': False,
    }
    for i, dstr in enumerate(dates):
        code_i = wcode[i] if i < len(wcode) else -1
        day = {
            'date': datetime.strptime(dstr, '%Y-%m-%d').strftime('%d/%m'),
            'tmax': round(tmax[i]) if i < len(tmax) and tmax[i] is not None else None,
            'tmin': round(tmin[i]) if i < len(tmin) and tmin[i] is not None else None,
            'rain_prob': pprob[i] if i < len(pprob) else None,
            'desc': WEATHER_CODES.get(code_i, ('—', 'fa-question'))[0],
            'icon': WEATHER_CODES.get(code_i, ('—', 'fa-question'))[1],
        }
        weather['days'].append(day)
        if day['tmin'] is not None and day['tmin'] <= 2:
            weather['frost_alert'] = True
    if weather['today_rain_mm'] is not None and weather['today_rain_mm'] >= 2:
        weather['rain_hint'] = True
    
    _WEATHER_CACHE['ts'] = now_ts
    _WEATHER_CACHE['data'] = weather
    return weather

# --- NOTIFICHE TELEGRAM ---

def send_telegram(message):
    """Invia una notifica Telegram se configurata (asincrona, mai blocca la pagina)."""
    settings = get_app_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    def _send():
        try:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'},
                timeout=10
            )
        except Exception as e:
            print(f'Errore invio Telegram: {e}')
    threading.Thread(target=_send, daemon=True).start()
    return True

# --- PULIZIA RISPOSTE CHAT (modelli come Gemma "pensano ad alta voce") ---

# Parole italiane usate per riconoscere le righe della risposta vera
_IT_WORDS_DETECT = {
    'il','lo','la','i','gli','le','un','uno','una','di','a','da','in','con','su','per','tra','fra','e','ed','o','se','non','che','chi','come','dove','perché','quando','anche','ancora','più','meno','molto','poco','tutto','sono','è','siamo','hanno','ho','ha','terreno','terra','pianta','piante','acqua','annaffia','annaffiare','innaffia','innaffiare','umido','asciutto','asciutti','radici','foglie','vaso','sottovasi','consiglio','oggi','sempre','prima','procedi','così','dati','ciao','ecco','decidere','risultano','varietà','controlla','queste','priorità','dipende','migliore','evita','bagnare','mantieni','leggermente','ristagni','argentee','grigio','spesso','esagerare','collezione','umidità','frequente','moderato','sporadico','ricorda','speciale','caso'
}

# Parole/frasi che indicano appunti interni del modello
_META_KEYWORDS = [
    'persona:', 'role:', 'app:', 'goal:', 'constraint', 'strict output', 'output rule',
    'format:', 'language:', 'style:', 'input:', 'user question', "user's plants",
    'user plants', 'since the', 'the user is asking', "i don't have", 'i have to',
    'i need to', 'i cannot', 'general watering rule', 'grouping by needs',
    'high water', 'moderate:', 'low water', 'low/dry', 'practical check',
    'greeting:', 'main advice', 'guidance:', 'categorized', 'specific groupings',
    'check soil first', 'general rule:', 'ensure no', 'keep it under',
    'bullet points', 'word count', 'drafting', 'final polish', 'self-correction',
    'italian?', 'concise?', 'friendly', 'used user', 'no preamble',
    'based on user', 'option ', 'instruction:', 'the user has', 'wait,',
    'hmm,', 'my plan', 'first,', 'second,',
]

def _italian_line(line):
    """True se la riga è testo discorsivo italiano (non bullet, non intestazione)."""
    ls = line.strip()
    if not ls or ls.startswith(('*','-','#','>')):
        return False
    words = re.findall(r"[a-zA-Zàèéìòù']+", ls.lower())
    return sum(1 for w in words if w in _IT_WORDS_DETECT) >= 2

def _block_segments(block):
    """Scompagna un blocco in segmenti ('ital', testo) / ('meta', testo).
    Se un blocco contiene meta-appunti SEGUIDI dalla risposta italiana, la recupera."""
    b = block.strip()
    lower = b.lower()
    lines = b.split('\n')
    last_it = -1
    for i, l in enumerate(lines):
        if _italian_line(l):
            last_it = i
    has_meta = any(k in lower for k in _META_KEYWORDS)
    if not has_meta:
        return [('ital', b)]
    if last_it == -1:
        return [('meta', b)]
    head = '\n'.join(lines[:last_it]).strip()
    tail = '\n'.join(lines[last_it:]).strip()
    segs = []
    if head:
        segs.append(('meta', head))
    if tail:
        segs.append(('ital', tail))
    return segs

def clean_chat_reply(text):
    """Estrae SOLO la risposta finale in italiano.
    Gemma mette la risposta vera sempre alla FINE del messaggio, dopo lo scratchpad;
    quindi si parte dall'ultimo blocco italiano e si risale finché la sequenza è contigua.
    I blocchi di ragionamento separano sempre (appunti tipo '* Italian? Yes.'), quindi
    il confine è netto e deterministico."""
    t = (text or '').strip()
    if not t:
        return t
    t = re.sub(r'<think>[\s\S]*?</think>', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\(Word count[^\)]*\)', '', t, flags=re.IGNORECASE)

    blocks = [b.strip() for b in t.split('\n\n') if b.strip()]
    segs = []
    for b in blocks:
        segs.extend(_block_segments(b))

    # Risali dall'ultimo segmento italiano, estendi all'indietro finché contiguo
    end = len(segs) - 1
    while end >= 0 and segs[end][0] != 'ital':
        end -= 1
    if end < 0:
        return t  # niente italiano riconosciuto: lascia il testo originale
    start = end
    while start > 0 and segs[start - 1][0] == 'ital':
        start -= 1
    return '\n\n'.join(s[1] for s in segs[start:end + 1]).strip()
# Context processor to expose current season and month
@app.context_processor
def utility_processor():
    def get_current_season():
        month = datetime.now().month
        if month in [3, 4, 5]:
            return "Primavera", "spring_care"
        elif month in [6, 7, 8]:
            return "Estate", "summer_care"
        elif month in [9, 10, 11]:
            return "Autunno", "autumn_care"
        else:
            return "Inverno", "winter_care"
    
    def get_italian_month():
        months = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", 
                  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        return months[datetime.now().month - 1]

    season_name, season_attr = get_current_season()
    return dict(
        current_season=season_name, 
        current_season_attr=season_attr, 
        current_month=get_italian_month(),
        app_version=__version__,
        plant_category=plant_category
    )

# Helper for AI Analysis
def optimize_image_for_ai(image_path):
    """Ridimensiona e comprime l'immagine per l'invio alle API di analisi.
    Le foto moderne sono spesso 10-20MB: riducendole a max 1024px si
    velocizza enormemente l'invio e l'elaborazione lato AI."""
    try:
        img = Image.open(image_path)
        # Gestisce formati HEIC/PNG con trasparenza convertendo in RGB su sfondo bianco
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.convert("RGBA").split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        max_dimension = 1024
        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()
    except Exception as e:
        print(f"Errore ottimizzazione immagine: {str(e)} — uso il file originale")
        with open(image_path, "rb") as f:
            return f.read()

def analyze_plant_image(image_path, plant_name, species_hint="", model_override=None):
    settings = get_app_settings()
    ai_provider = settings.ai_provider or 'openai'
    
    if ai_provider == 'openai':
        api_key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY')
    elif ai_provider == 'google':
        api_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY')
    else:  # openrouter
        api_key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY')
    
    # OpenRouter: aggiorna la lista live dei modelli gratuiti (cache 6h) così
    # le alternative proposte dopo un errore sono modelli realmente disponibili
    if ai_provider == 'openrouter':
        fetch_openrouter_free_models()

    # Mock data if API key is not present
    if not api_key:
        # Generate rich realistic mockup analysis based on plant_name
        p_name = (plant_name or "Pianta generica").lower()
        
        issue_title = "Problema di Irrigazione / Luce inadeguata"
        issue_desc = "Le foglie mostrano segni di sofferenza (ingiallimento o punte secche)."
        solution = "Controlla il drenaggio del vaso. Assicurati che il sottovaso non trattenga acqua stagnante. Posiziona la pianta in un luogo più luminoso ma al riparo dai raggi diretti del sole."
        
        if "monstera" in p_name:
            issue_title = "Eccesso d'acqua (Foglie Gialle) / Bruciature solari"
            issue_desc = "Presenza di macchie gialle con aloni marroni sulle foglie inferiori, tipico sintomo di ristagno idrico alle radici."
            solution = "Sospendi le annaffiature fino a quando i primi 4-5 cm di terreno non sono completamente asciutti. Rimuovi le foglie gravemente danneggiate. Assicurati che il terreno sia ben drenante (aggiungi perlite se necessario)."
        elif "ficus" in p_name:
            issue_title = "Perdita improvvisa di foglie / Mancanza di umidità"
            issue_desc = "Le foglie cadono ancora verdi o leggermente secche. Il Ficus risente molto degli sbalzi di temperatura e dell'aria secca dei termosifoni."
            solution = "Allontana la pianta da correnti d'aria fredda o fonti di calore diretto. Nebulizza regolarmente le foglie con acqua distillata o posiziona un umidificatore nelle vicinanze."
        elif "succulenta" in p_name or "cactus" in p_name or "pianta grassa" in p_name:
            issue_title = "Marciume radicale da sovra-irrigazione"
            issue_desc = "I tessuti alla base appaiono molli, scuri e tendenti al marcio. Le piante grasse tollerano la siccità ma temono l'umidità stagnante."
            solution = "Riduci drasticamente le annaffiature (massimo una volta al mese in inverno). Se il fusto è molto molle, taglia le parti sane per fare talee e rinvasa in un terriccio specifico per cactus ad altissimo drenaggio."
        elif "pothos" in p_name:
            issue_title = "Foglie mosce e sbiadite (Carenza di luce/acqua)"
            issue_desc = "La pianta appare priva di vigore, con fusti lunghi ma con poche foglie distanti tra loro, indicando eziolatura per scarsa luce."
            solution = "Sposta in una posizione con più luce indiretta. Accorcia i rami troppo lunghi e spogli per stimolare una crescita più folta alla base. Innaffia solo quando il terriccio è del tutto asciutto."

        return {
            "status": "success",
            "is_mock": True,
            "plant_name": plant_name or "Pianta Rilevata",
            "problem": issue_title,
            "details": issue_desc,
            "solution": solution,
            "urgency": "Alta" if "marciume" in issue_title.lower() or "eccesso" in issue_title.lower() else "Media",
            "watering_rules": "Annaffia solo a terreno completamente asciutto.",
            "exposure_rules": "Luce indiretta e brillante, evita correnti d'aria."
        }

    # If API Key exists, we use the selected provider
    try:
        # Tracciamento del modello effettivamente usato + eventuali fallback
        result_model_used = None
        failed_models = []

        # Common prompt for both providers
        prompt = f"""
        Sei un esperto agronomo e botanico virtuale. Analizza questa immagine di una pianta ({plant_name if plant_name else 'specie sconosciuta'}) e identifica:
        1. Identificazione corretta della pianta (Nome comune e scientifico).
        2. Qual è il problema principale visibile (malattie, parassiti, carenze di luce/acqua, bruciature, o se è in salute).
        3. Spiegazione dettagliata del problema.
        4. Soluzione pratica passo-passo per risolverlo.
        5. Livello di urgenza (Alta, Media, Bassa).
        6. Regole di esposizione consigliate.
        7. Regole di irrigazione consigliate.

        Rispondi ESCLUSIVAMENTE con un formato JSON valido, senza blocchi di codice markdown o altri commenti esterni al JSON, con la seguente struttura:
        {{
            "plant_name": "Nome della pianta",
            "problem": "Titolo breve del problema",
            "details": "Spiegazione dettagliata dei sintomi e delle cause",
            "solution": "Guida pratica passo-passo per salvare o curare la pianta",
            "urgency": "Alta / Media / Bassa",
            "exposure_rules": "Esposizione ideale",
            "watering_rules": "Frequenza e consigli di irrigazione"
        }}
        """

        if ai_provider in ('openai', 'openrouter'):
            # OpenAI e OpenRouter condividono la stessa API (OpenAI-compatibile)
            # Ottimizza l'immagine (ridimensionamento a 1024px) prima di inviarla
            optimized_image_bytes = optimize_image_for_ai(image_path)
            base64_image = base64.b64encode(optimized_image_bytes).decode('utf-8')

            selected_model = model_override or get_selected_model(settings, ai_provider)
            result_model_used = selected_model
            if ai_provider == 'openrouter':
                client = get_openrouter_client(api_key)
            else:
                import openai
                client = openai.OpenAI(api_key=api_key)

            try:
                result = ai_json_completion(
                    client,
                    selected_model,
                    [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1000,
                )
            except Exception as e:
                # Nessun cambio automatico di modello: se l'utente ha già
                # confermato un modello, l'errore è definitivo.
                if model_override:
                    raise
                return _needs_model_choice(ai_provider, selected_model, str(e))

        else: # Google Gemini / Gemma
            genai.configure(api_key=api_key)

            # IMPORTANTE: viene usato SOLO il modello scelto dall'utente (o
            # quello confermato esplicitamente). Nessun passaggio automatico ad
            # altri modelli: se fallisce, chiediamo all'utente cosa fare.
            preferred = model_override or get_selected_model(settings, 'google')
            result_model_used = preferred

            result = None
            last_error = ""
            failed_models = []

            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            try:
                print(f"Trying model: {preferred}...")
                model = genai.GenerativeModel(preferred)
                # Ottimizza l'immagine (ridimensionamento a 1024px) prima di inviarla
                image_data = optimize_image_for_ai(image_path)

                contents = [
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_data}
                ]

                response = model.generate_content(
                    contents,
                    safety_settings=safety_settings
                )

                if response and response.text:
                    result = json.loads(clean_ai_json(response.text))
                    result["model_used"] = preferred
                    print(f"Success with model: {preferred}")
            except Exception as e:
                last_error = str(e)
                print(f"Model {preferred} failed: {last_error}")

            if result is None:
                # Nessun fallback automatico: se l'utente ha già scelto un
                # modello alternativo, segnaliamo l'errore definitivo.
                if model_override:
                    raise Exception(f"Il modello selezionato non ha risposto. Errore: {last_error}")
                # Altrimenti chiediamo all'utente quale modello usare.
                return _needs_model_choice('google', preferred, last_error)

        # Nota: niente 'return' anticipato nel ramo Google,
        # così is_mock viene impostato correttamente per TUTTI i provider
        result["is_mock"] = False
        result["model_used_id"] = result_model_used
        result["model_used_name"] = _get_model_display_name(result_model_used)
        return result

    except Exception as e:
        print(f"Errore chiamata {ai_provider}: {str(e)}")
        # Fallback in case of error
        return {
            "status": "error",
            "message": f"Errore durante l'analisi con {ai_provider}: {str(e)}. È stata utilizzata una diagnosi di fallback.",
            "is_mock": True,
            "plant_name": plant_name or "Pianta generica",
            "problem": "Diagnosi non disponibile",
            "details": f"Si è verificato un errore durante la connessione con l'API di {ai_provider}: {str(e)}",
            "solution": "Verifica la tua connessione internet e che la chiave API inserita sia corretta.",
            "urgency": "Media",
            "watering_rules": "Verifica le impostazioni standard.",
            "exposure_rules": "Luce indiretta."
        }

def get_best_purchase_time(plant_name, species=""):
    settings = get_app_settings()
    ai_provider = settings.ai_provider or 'openai'
    
    if ai_provider == 'openai':
        api_key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY')
    elif ai_provider == 'google':
        api_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY')
    else:  # openrouter
        api_key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY')
    
    if not api_key:
        return "Consiglio: In generale, la primavera è il momento migliore per acquistare la maggior parte delle piante da interno per favorire l'acclimatazione."

    try:
        prompt = f"""
        Sei un esperto botanico. Per la pianta '{plant_name}' ({species}), indica il periodo migliore dell'anno per acquistarla e spiega brevemente perché. 
        Considera la disponibilità nei vivai, la salute della pianta e la facilità di trapianto/acclimatazione.
        Rispondi in modo conciso (massimo 3 frasi).
        """
        
        def _ask():
            if ai_provider in ('openai', 'openrouter'):
                client = get_openai_compatible_client(ai_provider, api_key)
                response = client.chat.completions.create(
                    model=get_selected_model(settings, ai_provider),
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content.strip()
            else: # Google Gemini / Gemma
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(get_selected_model(settings, 'google'))
                response = model.generate_content(prompt)
                return response.text.strip()
        
        answer = run_with_timeout(_ask)
        if answer:
            return answer.strip()
            
    except Exception as e:
        print(f"Errore get_best_purchase_time: {str(e)}")
    return "Consiglio: Acquista in primavera o inizio estate per garantire una crescita vigorosa."

def get_seasonal_suggestions():
    settings = get_app_settings()
    ai_provider = settings.ai_provider or 'openai'
    
    month = datetime.now().month
    if month in [3, 4, 5]: season = "Primavera"
    elif month in [6, 7, 8]: season = "Estate"
    elif month in [9, 10, 11]: season = "Autunno"
    else: season = "Inverno"

    # Default suggestions to show if AI fails or keys are missing
    default_suggestions = [
        {"name": "Monstera Deliciosa", "reason": f"Un classico intramontabile, ideale per iniziare in {season}."},
        {"name": "Sansevieria", "reason": f"Estremamente resistente, perfetta per stabilizzarsi in {season}."},
        {"name": "Pothos", "reason": f"Crescita rapida e facile manutenzione, ottima per {season}."}
    ]

    if ai_provider == 'openai':
        api_key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY')
    elif ai_provider == 'google':
        api_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY')
    else:  # openrouter
        api_key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY')
    
    # Cache: se i suggerimenti per questa stagione sono freschi (< 6 ore),
    # restituiscili subito senza chiamare l'IA → wishlist sempre rapida
    cached = _SUGGESTIONS_CACHE.get(season)
    if cached and (time.time() - cached[0]) < _SUGGESTIONS_CACHE_TTL:
        return cached[1]

    if not api_key:
        return default_suggestions

    def _fetch():
        prompt = f"""
        Sei un esperto botanico. Siamo in {season}. Suggerisci 3 piante diverse che sia l'ideale acquistare e trapiantare in questo periodo.
        Per ogni pianta fornisci:
        1. Nome della pianta
        2. Un motivo breve (max 15 parole) per cui è consigliata ora.
        
        Rispondi ESCLUSIVAMENTE in formato JSON come segue:
        {{
            "suggestions": [
                {{"name": "Nome Pianta", "reason": "Motivo"}},
                {{"name": "Nome Pianta", "reason": "Motivo"}}
            ]
        }}
        """
        
        if ai_provider in ('openai', 'openrouter'):
            client = get_openai_compatible_client(ai_provider, api_key)
            data = ai_json_completion(
                client,
                get_selected_model(settings, ai_provider),
                [{"role": "user", "content": prompt}],
            )
        else: # Google Gemini / Gemma
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(get_selected_model(settings, 'google'))
            response = model.generate_content(prompt)
            data = json.loads(clean_ai_json(response.text))
        
        suggestions = data.get("suggestions", [])
        return suggestions if suggestions else None
    
    suggestions = run_with_timeout(_fetch)
    if isinstance(suggestions, list) and suggestions:
        _SUGGESTIONS_CACHE[season] = (time.time(), suggestions)
        return suggestions
    
    return default_suggestions


# --- INNAFFIATURE RICORRENTI AUTOMATICHE ---

def ensure_watering_tasks():
    """Per ogni pianta con frequenza impostata, crea il compito 'Innaffia'
    quando l'intervallo è scaduto. Chiamata ad ogni apertura della dashboard.
    Ritorna il numero di compiti creati."""
    from datetime import timedelta
    now = datetime.utcnow()
    created = 0
    created_plant_names = []
    
    plants = Plant.query.filter(
        Plant.watering_frequency_days.isnot(None),
        Plant.watering_frequency_days > 0
    ).all()
    
    for p in plants:
        freq_days = p.watering_frequency_days
        
        # C'è già un'innaffiatura in attesa? Niente da fare
        pending = Task.query.filter_by(plant_id=p.id, task_type='watering', status='pending').first()
        if pending:
            continue
        
        # Quando è stata innaffiata l'ultima volta?
        last_done = Task.query.filter_by(plant_id=p.id, task_type='watering', status='completed')\
                              .order_by(Task.completed_at.desc()).first()
        
        if last_done and last_done.completed_at:
            days_since = (now - last_done.completed_at).days
            if days_since < freq_days:
                continue  # Non è ancora ora
            # Se è in ritardo, la data scadenza resta "oggi"
            due_date = now.strftime('%d/%m/%Y')
        else:
            # Prima programmazione: compito immediato per partire col ritmo
            days_since = None
            due_date = now.strftime('%d/%m/%Y')
        
        new_task = Task(
            plant_id=p.id,
            title=f"💧 Innaffia {p.name}",
            description=(p.watering or '')[:300] or 'Innaffiatura programmata automaticamente.',
            due_date=due_date,
            is_urgent=False,
            status='pending',
            task_type='watering'
        )
        db.session.add(new_task)
        created += 1
        created_plant_names.append(p.name)
    
    if created:
        db.session.commit()
        print(f"Generati {created} compiti di innaffiatura automatici")
        # Notifica Telegram (se configurata) solo con le piante appena programmate
        send_telegram(f"💧 <b>Florae</b>\nOggi da innaffiare:\n" + ', '.join(created_plant_names))
    return created


# --- ROUTES ---

@app.route('/')
def dashboard():
    # Genera le innaffiature scadute PRIMA di caricare la bacheca
    ensure_watering_tasks()
    # Meteo per la città configurata (None se non impostata)
    weather = get_weather()
    
    # Fetch all tasks grouped by status and urgency
    urgent_tasks = Task.query.filter_by(status='pending', is_urgent=True).order_by(Task.created_at.desc()).all()
    pending_tasks = Task.query.filter_by(status='pending', is_urgent=False).order_by(Task.created_at.desc()).all()
    completed_tasks = Task.query.filter_by(status='completed').order_by(Task.created_at.desc()).limit(5).all()
    
    # Compiti urgenti raggruppati per pianta (vista "Raggruppa" della bacheca)
    _groups = {}
    for t in urgent_tasks:
        g_name = t.plant.name if t.plant else 'Compiti Generali'
        g_key = (g_name, t.plant.id if t.plant else None)
        if g_key not in _groups:
            _groups[g_key] = {'name': g_name, 'plant_id': (t.plant.id if t.plant else None), 'tasks': []}
        _groups[g_key]['tasks'].append(t)
    urgent_groups = [
        {'name': v['name'], 'plant_id': v['plant_id'], 'count': len(v['tasks']),
         'has_watering': any(t.task_type == 'watering' for t in v['tasks']),
         'tasks': v['tasks']}
        for v in sorted(_groups.values(), key=lambda x: x['name'].lower())
    ]
    
    # Compiti standard / pendenti raggruppati per pianta (vista "Raggruppa" della bacheca)
    _p_groups = {}
    for t in pending_tasks:
        g_name = t.plant.name if t.plant else 'Compiti Generali'
        g_key = (g_name, t.plant.id if t.plant else None)
        if g_key not in _p_groups:
            _p_groups[g_key] = {'name': g_name, 'plant_id': (t.plant.id if t.plant else None), 'tasks': []}
        _p_groups[g_key]['tasks'].append(t)
    pending_groups = [
        {'name': v['name'], 'plant_id': v['plant_id'], 'count': len(v['tasks']),
         'has_watering': any(t.task_type == 'watering' for t in v['tasks']),
         'tasks': v['tasks']}
        for v in sorted(_p_groups.values(), key=lambda x: x['name'].lower())
    ]
    
    # Plants count
    plants_count = Plant.query.count()
    pending_count = Task.query.filter_by(status='pending').count()
    
    # Simple list of all plants to show care tips for the current season
    plants = Plant.query.all()
    
    # Guida stagionale raggruppata per categoria botanica: le piante con il
    # consiglio default della categoria vengono accorpate; quelle con testo
    # personalizzato dall'utente restano in vista individuale
    month = datetime.now().month
    if month in [3, 4, 5]: season_attr = 'spring_care'
    elif month in [6, 7, 8]: season_attr = 'summer_care'
    elif month in [9, 10, 11]: season_attr = 'autumn_care'
    else: season_attr = 'winter_care'
    
    _cat_groups = {}
    custom_plants = []
    for p in plants:
        label, icon = plant_category(p.name, p.species)
        default_care = seasonal_care_defaults(p.name, p.species)[season_attr]
        current_care = getattr(p, season_attr, None)
        if current_care and current_care != default_care:
            custom_plants.append(p)
            continue
        if label not in _cat_groups:
            _cat_groups[label] = {'label': label, 'icon': icon, 'care': default_care, 'plants': []}
        _cat_groups[label]['plants'].append(p.name)
    
    _order = {meta[0]: i for i, meta in enumerate(_CATEGORY_META)}
    _order["Altre piante"] = len(_CATEGORY_META)
    seasonal_groups = sorted(_cat_groups.values(), key=lambda g: _order.get(g['label'], 99))
    for g in seasonal_groups:
        g['count'] = len(g['plants'])
    custom_plants.sort(key=lambda p: p.name.lower())
    
    return render_template('dashboard.html', 
                           urgent_tasks=urgent_tasks, 
                           pending_tasks=pending_tasks, 
                           completed_tasks=completed_tasks,
                           plants_count=plants_count,
                           pending_count=pending_count,
                           plants=plants,
                           seasonal_groups=seasonal_groups,
                           custom_plants=custom_plants,
                           urgent_groups=urgent_groups,
                           pending_groups=pending_groups,
                           weather=weather)


# --- CONSIGLI STAGIONALI IN BASE ALLA SPECIE ---
# Il vecchio fallback applicava lo stesso testo identico a tutte le piante.
# Ora i consigli default vengono scelti in base alla categoria botanica.

_OLD_GENERIC_DEFAULTS = {
    'spring_care': "Ricomincia a concimare una volta al mese. Innaffia con più regolarità.",
    'summer_care': "Innaffia frequentemente, controllando che il terreno non si secchi del tutto. Proteggi dai raggi solari troppo intensi.",
    'autumn_care': "Riduci gradualmente le annaffiature. Sospendi le concimazioni. Riporta in casa se la pianta soffre il freddo.",
    'winter_care': "Innaffia solo sporadicamente. Assicurati che la stanza sia luminosa e lontana dai termosifoni."
}

_SEASONAL_CARE_CATEGORIES = [
    # (parole chiave, consigli)
    (["rosmarino", "salvia", "menta", "lavanda", "basilico", "prezzemolo", "origano", "magiorana", "aromatica", "erp", "ceriolo"], {
        "spring_care": "Riprendi annaffiature regolari e una concimazione mensile leggera. Raccogli le foglie più giovani per stimolare la crescita.",
        "summer_care": "Innaffia al mattino senza bagnare le foglie. Se va in fiore taglia gli steli fiorali: le erbe perdono aroma dopo la fioritura.",
        "autumn_care": "Riduci gradualmente le annaffiature e sospendi le concimazioni. Raccogli gli ultimi rametti prima delle prime gelate.",
        "winter_care": "Mantieni il terreno poco umido e la pianta in un luogo luminoso e riparato dal freddo. Nessuna concimazione."
    }),
    (["cactus", "grassa", "succul", "sansevieria", "crassula", "echeveria", "aloe", "fantasma", "kalanchoe", "sedum", "agave", "haworthia"], {
        "spring_care": "Riprendi le annaffiature solo a terreno completamente asciutto. Inizia una concimazione specifica per succulente una volta al mese.",
        "summer_care": "Annaffia solo quando il terreno è asciutto. Ripara dai raggi solari più intensi delle ore centrali e garantisci buona ventilazione.",
        "autumn_care": "Dirada molto le annaffiature e sospendi le concimazioni: con le giornate più corte il terreno resta umido a lungo.",
        "winter_care": "Innaffia una volta al mese o meno. Mantieni temperature sopra i 5-8°C in ambiente luminoso e asciutto."
    }),
    (["monstera", "pothos", "potos", "filodendro", "dracena", "orchidea", "ficus", "palma", "felce", "calathea", "spatifillo", "sgambo", "croton", "dieffenbachia"], {
        "spring_care": "Inizia una concimazione quindicinale e aumenta gradualmente le annaffiature. È il momento ideale per il rinvaso.",
        "summer_care": "Innaffia con regolarità mantenendo il terreno fresco. Aumenta l'umidità fogliare e ripara dal sole diretto.",
        "autumn_care": "Riduci le annaffiature e sospendi il concime. Sposta la pianta lontano da finestre fredde e correnti d'aria.",
        "winter_care": "Annaffia solo quando i primi centimetri di terriccio sono asciutti. Allontana dai termosifoni e vaporizza se l'aria è secca."
    }),
    (["ciclamino", "viola", "margherita", "ortensia", "dalia", "tulipano", "geranio", "campanule", "zinnia", "tagete", "fresia", "giacinto", "narciso", "petunia", "begonia"], {
        "spring_care": "Concima quindicinalmente per stimolare nuovi boccioli e mantieni il terreno fresco senza ristagni d'acqua.",
        "summer_care": "Elimina i fiori appassiti e innaffia regolarmente nelle ore fresche. Proteggi i petali più delicati dal sole intenso.",
        "autumn_care": "Riduci le annaffiature con l'arrivo del fresco. Rimuovi le parti secche e prepara la pianta alla pausa vegetativa.",
        "winter_care": "Annaffia pochissimo e proteggi dalle gelate. Le bulbose possono rimanere nel terreno e apprezzano il freddo per rifiorire."
    }),
    (["limone", "arancio", "mandarino", "ulivo", "vite", "ibisco", "acero", "melograno", "larice", "olivo", "albero", "rosa", "gelsomino"], {
        "spring_care": "Riprendi concimazione e annaffiature regolari. È il periodo ideale per potature leggere e rinvaso.",
        "summer_care": "Annaffia abbondantemente nei periodi caldi, verifica la presenza di parassiti sulle foglie e proteggi i frutti in formazione.",
        "autumn_care": "Dirada le annaffiature, sospendi il concime e porta in riparo le specie più sensibili al freddo.",
        "winter_care": "Annaffia solo sporadicamente. Proteggi dalle gelate con telo o spostando in un luogo luminoso e riparato."
    })
]

def seasonal_care_defaults(name="", species=""):
    """Consigli stagionali di default in base alla specie della pianta.
    Restituisce un dict con spring_care, summer_care, autumn_care, winter_care."""
    text = f"{(name or '')} {(species or '')}".lower()
    for keywords, care in _SEASONAL_CARE_CATEGORIES:
        if any(k in text for k in keywords):
            return dict(care)
    return dict(_OLD_GENERIC_DEFAULTS)

_CATEGORY_META = [
    ("Aromatiche", "fa-mortar-pestle"),
    ("Succulente e piante grasse", "fa-sun"),
    ("Piante tropicali e da fogliame", "fa-leaf"),
    ("Fioriture", "fa-spa"),
    ("Alberi e arbusti", "fa-tree"),
]

def plant_category(name="", species=""):
    """Restituisce (etichetta, icona) della categoria botanica della pianta."""
    text = f"{(name or '')} {(species or '')}".lower()
    for i, (keywords, _care) in enumerate(_SEASONAL_CARE_CATEGORIES):
        if any(k in text for k in keywords):
            return _CATEGORY_META[i]
    return ("Altre piante", "fa-seedling")

@app.route('/plants')
def list_plants():
    plants = Plant.query.order_by(Plant.name).all()
    return render_template('plants.html', plants=plants)


@app.route('/plant/add', methods=['POST'])
def add_plant():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash("Il nome della pianta è obbligatorio!", "error")
        return redirect(url_for('list_plants'))
    species = request.form.get('species')
    exposure = request.form.get('exposure')
    watering = request.form.get('watering')
    care = request.form.get('care')
    
    # Consigli stagionali di default in base alla specie (non più testo generico identico per tutte)
    defaults = seasonal_care_defaults(name, species)
    spring_care = (request.form.get('spring_care') or '').strip() or defaults['spring_care']
    summer_care = (request.form.get('summer_care') or '').strip() or defaults['summer_care']
    autumn_care = (request.form.get('autumn_care') or '').strip() or defaults['autumn_care']
    winter_care = (request.form.get('winter_care') or '').strip() or defaults['winter_care']
    
    # Frequenza innaffiatura automatica (giorni, opzionale)
    try:
        watering_freq = int(request.form.get('watering_frequency_days'))
        if watering_freq < 1: raise ValueError
    except (TypeError, ValueError):
        watering_freq = None
    
    # Handle image upload
    image_file = request.files.get('image')
    image_url = None
    if image_file and image_file.filename != '':
        filename = secure_filename(image_file.filename)
        # Fallback se secure_filename svuota il nome (es. caratteri non-ASCII)
        if not filename:
            filename = f"pianta_{int(datetime.now().timestamp())}.jpg"
        # Append timestamp to avoid overwrite
        filename = f"{int(datetime.now().timestamp())}_{filename}"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(os.path.join(app.root_path, image_path))
        image_url = '/' + image_path.replace('\\', '/')

    new_plant = Plant(
        name=name,
        species=species,
        exposure=exposure,
        watering=watering,
        care=care,
        spring_care=spring_care,
        summer_care=summer_care,
        autumn_care=autumn_care,
        winter_care=winter_care,
        image_url=image_url,
        watering_frequency_days=watering_freq
    )
    db.session.add(new_plant)
    db.session.commit()
    
    flash(f"Pianta '{name}' aggiunta con successo!", "success")
    return redirect(url_for('list_plants'))


@app.route('/plant/<int:id>')
def plant_details(id):
    plant = Plant.query.get_or_404(id)
    
    # Recuperiamo tutte le attività associate a questa pianta
    tasks = Task.query.filter_by(plant_id=id).all()
    
    # Creiamo una lista di dizionari per le attività da inviare al frontend
    tasks_list = [
        {
            'id': task.id,
            'title': task.title,
            'status': task.status,
            'is_urgent': task.is_urgent
        } for task in tasks
    ]
    
    return jsonify({
        "id": plant.id,
        "name": plant.name,
        "species": plant.species,
        "exposure": plant.exposure,
        "watering": plant.watering,
        "care": plant.care,
        "spring_care": plant.spring_care,
        "summer_care": plant.summer_care,
        "autumn_care": plant.autumn_care,
        "winter_care": plant.winter_care,
        "image_url": plant.image_url or '/static/img/placeholder.svg',
        "watering_frequency_days": plant.watering_frequency_days,
        "tasks": tasks_list  # Inviamo la lista delle attività
    })


@app.route('/plant/edit/<int:id>', methods=['POST'])
def edit_plant(id):
    plant = Plant.query.get_or_404(id)
    new_name = (request.form.get('name') or '').strip()
    if not new_name:
        flash("Il nome della pianta è obbligatorio! Modifica non salvata.", "error")
        return redirect(url_for('list_plants'))
    plant.name = new_name
    plant.species = request.form.get('species')
    plant.exposure = request.form.get('exposure')
    plant.watering = request.form.get('watering')
    plant.care = request.form.get('care')
    
    plant.spring_care = request.form.get('spring_care')
    plant.summer_care = request.form.get('summer_care')
    plant.autumn_care = request.form.get('autumn_care')
    plant.winter_care = request.form.get('winter_care')
    
    # Frequenza innaffiatura automatica (giorni, opzionale)
    try:
        plant.watering_frequency_days = int(request.form.get('watering_frequency_days')) or None
    except (TypeError, ValueError):
        plant.watering_frequency_days = None
    
    # Image update (optional)
    image_file = request.files.get('image')
    if image_file and image_file.filename != '':
        filename = secure_filename(image_file.filename)
        filename = f"{int(datetime.now().timestamp())}_{filename}"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(os.path.join(app.root_path, image_path))
        plant.image_url = '/' + image_path.replace('\\', '/')
        
    db.session.commit()
    flash(f"Informazioni di '{plant.name}' aggiornate!", "success")
    return redirect(url_for('list_plants'))


@app.route('/plant/delete/<int:id>')
def delete_plant(id):
    plant = Plant.query.get_or_404(id)
    db.session.delete(plant)
    db.session.commit()
    flash("Pianta eliminata con successo.", "success")
    return redirect(url_for('list_plants'))


# --- WISHLIST MANAGEMENT ---

@app.route('/wishlist')
def wishlist():
    items = WishlistPlant.query.order_by(WishlistPlant.created_at.desc()).all()
    suggestions = get_seasonal_suggestions()
    return render_template('wishlist.html', wishlist=items, suggestions=suggestions)


@app.route('/wishlist/add', methods=['POST'])
def add_wishlist_item():
    name = request.form.get('name')
    species = request.form.get('species')
    notes = request.form.get('notes')
    
    if not name:
        flash("Il nome della pianta è obbligatorio!", "error")
        return redirect(url_for('wishlist'))
    
    # Chiediamo all'IA il periodo migliore per l'acquisto
    best_time = get_best_purchase_time(name, species)
    
    new_item = WishlistPlant(
        name=name,
        species=species,
        notes=notes,
        best_time=best_time
    )
    db.session.add(new_item)
    db.session.commit()
    
    flash(f"'{name}' aggiunta alla tua wishlist!", "success")
    return redirect(url_for('wishlist'))


@app.route('/wishlist/delete/<int:id>', methods=['POST'])
def delete_wishlist_item(id):
    item = WishlistPlant.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash("Elemento rimosso dalla wishlist.", "info")
    return redirect(url_for('wishlist'))


@app.route('/wishlist/buy/<int:id>', methods=['POST'])
def move_to_plants(id):
    item = WishlistPlant.query.get_or_404(id)
    
    # Crea una nuova pianta nella collezione principale
    new_plant = Plant(
        name=item.name,
        species=item.species,
        exposure="Da definire",
        watering="Da definire",
        care=f"Note dalla wishlist: {item.notes if item.notes else 'Nessuna nota'}",
        **seasonal_care_defaults(item.name, item.species)
    )
    
    db.session.add(new_plant)
    # Rimuovi dalla wishlist
    db.session.delete(item)
    db.session.commit()
    
    flash(f"Congratulazioni! '{new_plant.name}' è ora parte della tua collezione!", "success")
    return redirect(url_for('list_plants'))


# --- TASK MANAGEMENT ---

@app.route('/task/add', methods=['POST'])
def add_task():
    plant_id = request.form.get('plant_id')
    title = request.form.get('title')
    description = request.form.get('description')
    due_date = request.form.get('due_date') or "Subito"
    is_urgent = 'is_urgent' in request.form
    
    if not title or not title.strip():
        flash("Il titolo dell'attività è obbligatorio!", "error")
        return redirect(url_for('dashboard'))

    try:
        plant_id = int(plant_id)
    except (TypeError, ValueError):
        plant_id = None

    new_task = Task(
        plant_id=plant_id,
        title=title.strip(),
        description=description,
        due_date=due_date,
        is_urgent=is_urgent,
        status='pending'
    )
    db.session.add(new_task)
    db.session.commit()
    flash("Nuova attività programmata!", "success")
    return redirect(url_for('dashboard'))


@app.route('/task/complete/<int:id>')
def complete_task(id):
    task = Task.query.get_or_404(id)
    task.status = 'completed'
    task.completed_at = datetime.utcnow()  # Usato dalle innaffiature ricorrenti
    db.session.commit()
    flash("Attività completata! Ottimo lavoro!", "success")
    return redirect(url_for('dashboard'))


@app.route('/task/delete/<int:id>')
def delete_task(id):
    task = Task.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()
    flash("Attività rimossa.", "info")
    return redirect(url_for('dashboard'))


# --- AI DIAGNOSIS (ASINCRONA: niente più "pagina scaduta" quando il telefono va in standby) ---

@app.route('/diagnose', methods=['GET', 'POST'])
def diagnose_page():
    plants = Plant.query.order_by(Plant.name).all()

    if request.method == 'POST':
        plant_id = request.form.get('plant_id')
        custom_plant_name = request.form.get('custom_plant_name')

        image_file = request.files.get('plant_photo')
        if not image_file or image_file.filename == '':
            flash("Devi caricare una foto per poter effettuare la diagnosi!", "error")
            return redirect(url_for('diagnose_page'))

        # Determine actual plant name
        if plant_id and plant_id != "new":
            try:
                selected_plant = Plant.query.get(int(plant_id))
            except (TypeError, ValueError):
                selected_plant = None
            if not selected_plant:
                flash("La pianta selezionata non esiste più. Riprova.", "error")
                return redirect(url_for('diagnose_page'))
            plant_name = selected_plant.name
            species = selected_plant.species or ""
        else:
            plant_name = custom_plant_name or "Pianta Sconosciuta"
            species = ""

        # Save photo
        filename = secure_filename(image_file.filename)
        # Fallback se secure_filename svuota il nome (es. caratteri non-ASCII)
        if not filename:
            filename = f"diagnosi_{int(datetime.now().timestamp())}.jpg"
        filename = f"diag_{int(datetime.now().timestamp())}_{filename}"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(os.path.join(app.root_path, image_path))
        full_image_url = '/' + image_path.replace('\\', '/')

        # Crea un job asincrono: l'analisi IA gira in un thread in background
        # e la pagina di attesa fa polling dello stato. Così il POST termina
        # subito e non muore mai, nemmeno se lo schermo va in standby.
        job_id = uuid.uuid4().hex
        with _diagnosis_jobs_lock:
            diagnosis_jobs[job_id] = {
                'status': 'processing',
                'created_at': time.time(),
                'finished_at': None,
                'result': None,
                'image_url': full_image_url,
                'plant_id': plant_id,
                'plant_name': plant_name,
                'species': species,
            }
        t = threading.Thread(
            target=_run_diagnosis_job,
            args=(job_id, os.path.join(app.root_path, image_path), plant_name, species),
            daemon=True
        )
        # (plant_id e species sono già salvati nel job dict qui sopra)
        t.start()
        _prune_diagnosis_jobs()

        return redirect(url_for('diagnose_wait', job_id=job_id))

    # Avvisa se il modello scelto non può vedere le immagini (es. Gemma testo)
    _settings = get_app_settings()
    _provider = _settings.ai_provider or 'openai'
    _model = get_selected_model(_settings, _provider)
    _vision_ids = [m['id'] for m in vision_models(_provider)]
    _model_is_vision = _model in _vision_ids
    _model_name = _get_model_display_name(_model) if _model else '—'

    return render_template('diagnose.html', plants=plants,
                           model_is_vision=_model_is_vision,
                           current_model_name=_model_name)


@app.route('/diagnose/wait/<job_id>')
def diagnose_wait(job_id):
    with _diagnosis_jobs_lock:
        job = diagnosis_jobs.get(job_id)
    if job is None:
        flash("Analisi non trovata o scaduta. Ricarica la foto.", "error")
        return redirect(url_for('diagnose_page'))
    return render_template('diagnose_wait.html', job_id=job_id,
                           image_url=job['image_url'],
                           plant_name=job['plant_name'])


@app.route('/diagnose/status/<job_id>')
def diagnose_status(job_id):
    with _diagnosis_jobs_lock:
        job = diagnosis_jobs.get(job_id)
    if job is None:
        return jsonify({'status': 'missing'})
    payload = {'status': job['status']}
    # in caso di errore includiamo il messaggio per mostrarlo nella pagina di attesa
    if job['status'] == 'error' and isinstance(job.get('result'), dict):
        payload['result'] = {'message': job['result'].get('message', 'Errore sconosciuto.')}
    return jsonify(payload)


@app.route('/diagnose/choice/<job_id>')
def diagnose_choice(job_id):
    """Mostra la scelta del modello quando quello selezionato non ha risposto:
    l'app NON cambia modello da sola, chiede all'utente."""
    with _diagnosis_jobs_lock:
        job = diagnosis_jobs.get(job_id)
    if job is None:
        flash("Analisi non trovata o scaduta. Ricarica la foto.", "error")
        return redirect(url_for('diagnose_page'))
    if job['status'] == 'processing':
        return redirect(url_for('diagnose_wait', job_id=job_id))
    result = job.get('result') or {}
    if job['status'] != 'needs_choice':
        return redirect(url_for('diagnose_result_page', job_id=job_id))
    return render_template('diagnose_choice.html', job_id=job_id,
                           image_url=job['image_url'],
                           plant_name=job['plant_name'],
                           preferred_model_name=result.get('preferred_model_name', 'Modello selezionato'),
                           error_message=result.get('failed_error') or result.get('message', ''),
                           hint=result.get('message', ''),
                           alternatives=result.get('alternatives', []))


@app.route('/diagnose/retry/<job_id>', methods=['POST'])
def diagnose_retry(job_id):
    """Rilancia l'analisi usando il modello scelto esplicitamente dall'utente."""
    with _diagnosis_jobs_lock:
        job = diagnosis_jobs.get(job_id)
    if job is None:
        flash("Analisi non trovata o scaduta. Ricarica la foto.", "error")
        return redirect(url_for('diagnose_page'))

    model = (request.form.get('model') or '').strip()
    if not model:
        flash("Seleziona un modello per riprovare.", "error")
        return redirect(url_for('diagnose_choice', job_id=job_id))

    # Ricostruisce il percorso della foto dal suo URL pubblico
    image_path = os.path.join(app.root_path, job['image_url'].lstrip('/'))

    # Riporta il job in stato 'processing' e riavvia l'analisi col modello scelto
    _set_job(job_id, status='processing', result=None, finished_at=None, model_override=model)
    t = threading.Thread(
        target=_run_diagnosis_job,
        args=(job_id, image_path, job['plant_name'], job['species'], model),
        daemon=True
    )
    t.start()

    return redirect(url_for('diagnose_wait', job_id=job_id))


@app.route('/diagnose/result/<job_id>')
def diagnose_result_page(job_id):
    with _diagnosis_jobs_lock:
        job = diagnosis_jobs.get(job_id)
    if job is None:
        flash("Analisi non trovata o scaduta. Ricarica la foto.", "error")
        return redirect(url_for('diagnose_page'))
    # 'complete' ed 'error' mostrano entrambi la pagina risultato
    # (l'errore è già nel dict result); 'needs_choice' rimanda alla scelta modello
    if job['status'] == 'processing':
        return redirect(url_for('diagnose_wait', job_id=job_id))
    if job['status'] == 'needs_choice':
        return redirect(url_for('diagnose_choice', job_id=job_id))

    diagnosis = job['result']
    return render_template('diagnose_result.html',
                           diagnosis=diagnosis,
                           image_url=job['image_url'],
                           plant_id=job['plant_id'],
                           custom_plant_name=job['plant_name'],
                           species=job['species'])


@app.route('/diagnose/apply', methods=['POST'])
def apply_diagnosis():
    # Retrieve details from request
    plant_id = request.form.get('plant_id')
    plant_name = request.form.get('plant_name')
    species = request.form.get('species')
    problem = request.form.get('problem')
    details = request.form.get('details')
    solution = request.form.get('solution')
    urgency = request.form.get('urgency')
    image_url = request.form.get('image_url')
    exposure_rules = request.form.get('exposure_rules')
    watering_rules = request.form.get('watering_rules')
    
    # 1. Get or Create Plant
    plant = None
    if plant_id and plant_id != "new":
        try:
            plant = Plant.query.get(int(plant_id))
        except (TypeError, ValueError):
            plant = None
    if plant:
        # Update its details if empty or with new instructions
        if image_url:
            plant.image_url = image_url
        if exposure_rules and (not plant.exposure or plant.exposure == ""):
            plant.exposure = exposure_rules
        if watering_rules and (not plant.watering or plant.watering == ""):
            plant.watering = watering_rules
    else:
        # Create a brand new plant!
        plant = Plant(
            name=plant_name,
            species=species or "Rilevata da IA",
            exposure=exposure_rules or "Luce indiretta",
            watering=watering_rules or "Vedi diagnosi",
            care=f"Diagnosi IA: {problem}\n\nSoluzione:\n{solution}",
            image_url=image_url,
            **seasonal_care_defaults(plant_name, species)
        )
        db.session.add(plant)
        db.session.flush() # populate ID for the task creation
        
    # 2. Add Diagnosed Task to the database
    is_urgent = urgency in ["Alta", "High", "Urgente"]
    
    # Build title and desc
    task_title = f"Risolvi: {problem} ({plant.name})"
    task_desc = f"RISCONTRO DIAGNOSI:\n{details}\n\nCOSA FARE:\n{solution}"
    
    new_task = Task(
        plant_id=plant.id,
        title=task_title,
        description=task_desc,
        due_date="Subito",
        is_urgent=is_urgent,
        status='pending'
    )
    db.session.add(new_task)
    db.session.commit()
    
    # Notifica Telegram per le diagnosi urgenti (se configurata)
    if is_urgent:
        send_telegram(f"🚨 <b>Florae</b>\nDiagnosi urgente per <b>{plant.name}</b>:\n{problem}")
    
    tipo_compito = "compito urgente" if is_urgent else "compito"
    flash(f"Diagnosi applicata! Creato un {tipo_compito} per '{plant.name}' e aggiornato il database.", "success")
    return redirect(url_for('dashboard'))


@app.route('/list_models')
def list_models():
    settings = get_app_settings()
    api_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        return "Chiave API di Google non trovata. Vai in /settings e inseriscila."
    
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        model_list = []
        for m in models:
            model_list.append(f"{m.name} - Metodi: {m.supported_generation_methods}")
        return "<br>".join(model_list) if model_list else "Nessun modello trovato."
    except Exception as e:
        return f"Errore durante l'elenco dei modelli: {str(e)}"

# --- SETTINGS PAGE ---

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        ai_provider = request.form.get('ai_provider', 'openai')
        ai_model = request.form.get('ai_model', '').strip()
        openai_api_key = request.form.get('openai_api_key', '').strip()
        google_api_key = request.form.get('google_api_key', '').strip()
        openrouter_api_key = request.form.get('openrouter_api_key', '').strip()
        weather_city = request.form.get('weather_city', '').strip()
        telegram_bot_token = request.form.get('telegram_bot_token', '').strip()
        telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
        
        # Sicurezza: accettiamo solo modelli presenti nel listino del provider scelto
        valid_models = [m['id'] for m in AI_MODELS.get(ai_provider, [])]
        if ai_model not in valid_models:
            ai_model = valid_models[0] if valid_models else None
        
        settings = get_app_settings()
        settings.ai_provider = ai_provider
        settings.ai_model = ai_model
        # Le chiavi vengono aggiornate SOLO se compilate:
        # un campo lasciato vuoto non cancella la chiave già salvata
        if openai_api_key:
            settings.openai_api_key = openai_api_key
        if google_api_key:
            settings.google_api_key = google_api_key
        if openrouter_api_key:
            settings.openrouter_api_key = openrouter_api_key
        # Meteo e Telegram
        settings.weather_city = weather_city or None
        if telegram_bot_token:
            settings.telegram_bot_token = telegram_bot_token  # token aggiornato solo se compilato
        settings.telegram_chat_id = telegram_chat_id or None
        db.session.commit()
        
        flash("Configurazione salvata con successo! L'IA scelta è ora attiva (se hai inserito una chiave valida).", "success")
        return redirect(url_for('settings'))
    
    settings = get_app_settings()
    current_provider = settings.ai_provider or 'openai'
    # Aggiorna la lista dei modelli gratuiti OpenRouter (cache 6h: di solito è istantaneo)
    fetch_openrouter_free_models()
    current_model = get_selected_model(settings, current_provider)
    openai_key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY') or ""
    google_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY') or ""
    openrouter_key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY') or ""
    return render_template('settings.html', 
                           current_provider=current_provider, 
                           current_model=current_model,
                           ai_models=AI_MODELS,
                           weather_city=settings.weather_city or "",
                           telegram_chat_id=settings.telegram_chat_id or "",
                           openai_key=openai_key, 
                           google_key=google_key,
                           openrouter_key=openrouter_key)


@app.route('/settings/openrouter/refresh', methods=['POST'])
def refresh_openrouter_models():
    """Forza l'aggiornamento della lista dei modelli gratuiti OpenRouter."""
    models = fetch_openrouter_free_models(force=True)
    vision_count = len([m for m in models if m.get('vision')])
    if models:
        flash(f"Lista aggiornata: {len(models)} modelli gratuiti disponibili ({vision_count} con VISION).", "success")
    else:
        flash("Impossibile aggiornare la lista dei modelli (rete non raggiungibile).", "error")
    return redirect(url_for('settings'))


# --- CHAT COL BOTANICO IA ---

CHAT_SYSTEM_PROMPT = (
    "Sei Florae Bot, il botanico di fiducia dell'app Florae. "
    "Parli con l'utente in italiano, con tono amichevole e pratico. "
    "Le tue risposte sono brevi (massimo 150 parole) e usano elenchi puntati per i consigli operativi. "
    "Conosci le piante dell'utente elencate qui sotto e usi questi dati reali nelle risposte."
)

def _plants_context():
    plants = Plant.query.order_by(Plant.name).limit(20).all()
    if not plants:
        return "L'utente non ha ancora piante salvate nel tracker."
    lines = []
    for p in plants:
        freq = f", annaffiatura automatica ogni {p.watering_frequency_days} giorni" if p.watering_frequency_days else ""
        lines.append(f"- {p.name} ({p.species or 'specie non indicata'}){freq}")
    return "Piante reali dell'utente:\n" + "\n".join(lines)

@app.route('/chatbot')
def chatbot_page():
    history = session.get('chat_history', [])
    return render_template('chatbot.html', history=history)

@app.route('/chatbot/send', methods=['POST'])
def chatbot_send():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()[:2000]
    if not message:
        return jsonify({'reply': 'Scrivi prima una domanda 🙂'})
    
    settings = get_app_settings()
    provider, api_key = provider_api_key(settings)
    if not api_key:
        return jsonify({'reply': '⚠️ Per chattare serve una chiave API: configurala nella pagina Impostazioni.'})
    
    history = session.get('chat_history', [])
    history.append({'role': 'user', 'content': message})
    system_prompt = CHAT_SYSTEM_PROMPT + _plants_context()
    recent = history[-12:]
    
    def _ask(model_override=None):
        model_id = model_override or get_selected_model(settings, provider)
        if provider in ('openai', 'openrouter'):
            # OpenAI e OpenRouter condividono l'API chat completions
            client = get_openai_compatible_client(provider, api_key)
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{'role': 'system', 'content': system_prompt}] + recent
            )
            return resp.choices[0].message.content.strip()
        else:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_id)
            # Gemma non ha ruolo di sistema e imita ciò che vede: invece di comandi
            # meta (che riscrive nello scratchpad!), usiamo un PRIMING CONVERSAZIONALE:
            # un esempio di domanda/risposta pulita da cui il modello prende il ritmo
            seed_user = (
                f"{system_prompt}\n\n"
                f"Domanda di esempio: Devo innaffiare le mie piante oggi?\n\n"
                f"Come rispondi tu (nota lo stile: diretto, italiano, solo la risposta):"
            )
            seed_model = (
                "Controlla il terreno con il dito: se i primi 2-3 cm sono asciutti, è ora di innaffiare. "
                "Per le piante con annaffiatura programmata, segui la bacheca."
            )
            contents = [
                {'role': 'user', 'parts': [seed_user]},
                {'role': 'model', 'parts': [seed_model]},
            ]
            for h in recent:
                role = 'model' if h['role'] == 'assistant' else 'user'
                text_content = clean_chat_reply(h['content']) if h['role'] == 'assistant' else h['content']
                contents.append({'role': role, 'parts': [text_content]})
            response = model.generate_content(contents)
            return response.text.strip()
    
    try:
        reply = run_with_timeout(lambda: _ask(), timeout_seconds=CHAT_TIMEOUT_SECONDS, raise_on_error=True)
        if not reply:
            reply = ('⏱️ Non sono riuscito a rispondere entro 3 minuti. Il modello selezionato potrebbe essere '
                     'molto lento in questo momento. Riprova — oppure nelle Impostazioni scegli un modello '
                     'più rapido (i Gemini Flash rispondono in pochi secondi).')
    except Exception as e:
        err = str(e)
        chosen = get_selected_model(settings, provider)
        print(f"Chatbot errore con modello {chosen}: {err}")
        # Se il modello scelto non esiste o non è supportato dalla chiave/API,
        # riprova automaticamente con il modello consigliato del provider
        if any(k in err.lower() for k in ['not found', '404', 'is not supported', 'unsupported', 'not available']):
            fb = AI_MODELS.get(provider, [{}])[0]
            try:
                reply = run_with_timeout(lambda: _ask(fb['id']), timeout_seconds=CHAT_TIMEOUT_SECONDS, raise_on_error=True)
                reply += f"\n\n_(Risposto automaticamente con {fb['name']} perché il modello selezionato non è disponibile.)_"
            except Exception as e2:
                reply = f"❌ Il modello selezionato non è disponibile ({err[:150]}) e anche il fallback ha fallito ({str(e2)[:150]})."
        else:
            reply = f"❌ Errore dall'IA: {err[:300]}\n\nProva a scegliere un altro modello nelle Impostazioni (vedi anche /list_models per i modelli disponibili sulla tua chiave Google)."
    
    # Pulisce l'eventuale ragionamento interno leakato dal modello (es. Gemma)
    reply = clean_chat_reply(reply)
    
    history.append({'role': 'assistant', 'content': reply})
    session['chat_history'] = history[-14:]
    return jsonify({'reply': reply})

@app.route('/chatbot/clear', methods=['POST'])
def chatbot_clear():
    session.pop('chat_history', None)
    return jsonify({'ok': True})

# --- TEST NOTIFICA TELEGRAM ---

@app.route('/settings/test_telegram', methods=['POST'])
def test_telegram():
    settings = get_app_settings()
    token, cid = settings.telegram_bot_token, settings.telegram_chat_id
    if not token or not cid:
        flash("Prima salva il token del bot e il Chat ID.", "error")
        return redirect(url_for('settings'))
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': cid, 'text': '🌱 <b>Florae</b>\nCollegamento riuscito! Riceverai qui le notifiche.', 'parse_mode': 'HTML'},
            timeout=10
        )
        ok = r.json().get('ok', False)
        flash("Messaggio inviato! Controlla Telegram." if ok else f"Telegram ha rifiutato la richiesta: {r.json().get('description','errore sconosciuto')}", "success" if ok else "error")
    except Exception as e:
        flash(f"Errore Telegram: {e}", "error")
    return redirect(url_for('settings'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Migrazione leggera: aggiunge le colonne nuove se non esistono ancora
        from sqlalchemy import text
        migrations = {
            'settings': {'ai_model': 'VARCHAR(100)', 'weather_city': 'VARCHAR(100)',
                         'telegram_bot_token': 'VARCHAR(500)', 'telegram_chat_id': 'VARCHAR(100)'},
            'plant': {'watering_frequency_days': 'INTEGER'},
            'task': {'task_type': 'VARCHAR(20)', 'completed_at': 'DATETIME'},
        }
        with db.engine.connect() as conn:
            for table, cols in migrations.items():
                existing_cols = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
                if not existing_cols:
                    continue  # tabella non esiste (db vuoto): create_all l'ha già creata nuova
                for col_name, col_type in cols.items():
                    if col_name not in existing_cols:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                        print(f"Migrazione: aggiunta colonna {table}.{col_name}")
            conn.commit()
        
        # Migrazione 1.7.0: le piante create prima avevano tutte lo stesso testo
        # generico nei campi stagionali. Se i campi corrispondono esattamente al
        # vecchio default, li rigeneriamo in base alla specie della pianta.
        regenerated = 0
        for p in Plant.query.all():
            new_care = None
            if p.autumn_care == _OLD_GENERIC_DEFAULTS['autumn_care']:
                new_care = seasonal_care_defaults(p.name, p.species)
                # Sovrascrive solo i campi che contengono ancora il vecchio testo generico,
                # preservando eventuali personalizzazioni dell'utente
                if p.spring_care == _OLD_GENERIC_DEFAULTS['spring_care']:
                    p.spring_care = new_care['spring_care']
                if p.summer_care == _OLD_GENERIC_DEFAULTS['summer_care']:
                    p.summer_care = new_care['summer_care']
                p.autumn_care = new_care['autumn_care']
                if p.winter_care == _OLD_GENERIC_DEFAULTS['winter_care']:
                    p.winter_care = new_care['winter_care']
                regenerated += 1
        if regenerated:
            db.session.commit()
            print(f"Migrazione: rigenerati i consigli stagionali di {regenerated} piante in base alla specie")
        
        # Migrazione 1.7.3: ripristina le piante che puntano a foto non più
        # presenti su disco (file eliminati), così la card mostra il placeholder
        missing_fixed = 0
        for p in Plant.query.filter(Plant.image_url.isnot(None)).all():
            file_path = os.path.join(app.root_path, p.image_url.lstrip('/'))
            if not os.path.exists(file_path):
                p.image_url = None
                missing_fixed += 1
        if missing_fixed:
            db.session.commit()
            print(f"Migrazione: ripuliti {missing_fixed} riferimenti a foto non più presenti su disco")
        
        # Populate with some default plants if db is empty
        if Plant.query.count() == 0:
            p1 = Plant(
                name="Monstera Deliciosa",
                species="Monstera",
                exposure="Luce indiretta brillante. Evitare il sole diretto che brucia le foglie.",
                watering="Innaffiare abbondantemente solo quando i primi 3-4 cm di terriccio sono asciutti. Teme i ristagni d'acqua.",
                care="Spruzzare acqua sulle foglie regolarmente per mantenere l'umidità. Pulire le foglie con un panno umido ogni mese.",
                spring_care="Rinvasa se le radici escono dal vaso. Aumenta gradualmente le annaffiature e concima ogni 2 settimane.",
                summer_care="Annaffia generosamente 1-2 volte a settimana. Proteggi dai calori eccessivi e vaporizza quotidianamente.",
                autumn_care="Riduci le annaffiature. Sospendi le concimazioni. Controlla che le foglie non abbiano accumulato parassiti.",
                winter_care="Annaffia solo quando il terreno è quasi del tutto asciutto. Evita zone vicine ai termosifoni caldi."
            )
            p2 = Plant(
                name="Sansevieria",
                species="Sansevieria trifasciata (Lingua di suocera)",
                exposure="Tollera quasi ogni condizione: ottima in luce viva indiretta, sopravvive bene anche in angoli bui.",
                watering="Molto ridotto. Annaffiare solo a terreno completamente asciutto (ogni 2-3 settimane in estate, una volta al mese in inverno).",
                care="Pianta estremamente resistente. Non richiede umidità fogliare. Evitare assolutamente l'acqua stagnante nel sottovaso.",
                spring_care="Riprendi le annaffiature ogni 2 settimane. Aggiungi un concime liquido per succulente a fine primavera.",
                summer_care="Annaffia ogni 10-15 giorni. Può essere spostata all'esterno all'ombra.",
                autumn_care="Sposta nuovamente in casa. Dirada le annaffiature a una volta ogni 3 settimane.",
                winter_care="Innaffia pochissimo, circa una volta al mese. Assicurati che la temperatura non scenda sotto i 10 gradi."
            )
            db.session.add(p1)
            db.session.add(p2)
            db.session.commit()
            
            # Add a couple of initial reminders
            t1 = Task(
                plant_id=1,
                title="Pulire le foglie della Monstera",
                description="Usa un panno in microfibra umido per togliere la polvere così che possa fotosintetizzare meglio.",
                due_date="Domenica",
                is_urgent=False,
                status='pending'
            )
            t2 = Task(
                plant_id=2,
                title="Controllare umidità Sansevieria",
                description="Verificare che il terriccio sia asciutto fino in fondo prima di procedere con l'innaffiatura mensile.",
                due_date="Oggi",
                is_urgent=True,
                status='pending'
            )
            db.session.add(t1)
            db.session.add(t2)
            db.session.commit()

    # Debug attivo solo in sviluppo locale (FLASK_DEBUG non impostato);
    # nel container Docker è disattivato via ENV FLASK_DEBUG=0
    app.run(host='0.0.0.0', port=5001, debug=os.environ.get('FLASK_DEBUG', '1') == '1')
