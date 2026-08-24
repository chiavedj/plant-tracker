import os
import re
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import json
import google.generativeai as genai

__version__ = "1.1.1"  # Fonte unica della versione (vedi CHANGELOG.md)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Modelli IA disponibili, suddivisi per provider
AI_MODELS = {
    'openai': [
        {'id': 'gpt-4o-mini', 'name': 'GPT-4o mini', 'desc': 'Economico e veloce (consigliato)', 'icon': 'fa-feather'},
        {'id': 'gpt-4.1-nano', 'name': 'GPT-4.1 nano', 'desc': 'Il più economico in assoluto', 'icon': 'fa-seedling'},
        {'id': 'gpt-4.1-mini', 'name': 'GPT-4.1 mini', 'desc': 'Buon compromesso qualità/prezzo', 'icon': 'fa-scale-balanced'},
        {'id': 'gpt-4o', 'name': 'GPT-4o', 'desc': 'Massima qualità, più costoso', 'icon': 'fa-gem'},
    ],
    'google': [
        {'id': 'models/gemini-3.6-flash', 'name': 'Gemini 3.6 Flash', 'desc': 'Veloce ed economico (consigliato)', 'icon': 'fa-feather'},
        {'id': 'models/gemini-2.5-flash', 'name': 'Gemini 2.5 Flash', 'desc': 'Più intelligente, costo moderato', 'icon': 'fa-scale-balanced'},
        {'id': 'models/gemini-flash-latest', 'name': 'Gemini Flash Latest', 'desc': 'Ultima versione flash disponibile', 'icon': 'fa-wand-magic-sparkles'},
    ]
}

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ai_provider = db.Column(db.String(50), default='openai')
    ai_model = db.Column(db.String(100), nullable=True)  # Modello scelto dall'utente
    openai_api_key = db.Column(db.String(500), nullable=True)
    google_api_key = db.Column(db.String(500), nullable=True)
    openrouter_api_key = db.Column(db.String(500), nullable=True)

# Helper to get the AI model chosen by the user for a given provider
def get_selected_model(settings, provider):
    """Restituisce il modello scelto dall'utente, oppure il primo consigliato."""
    saved = (settings.ai_model or '').strip()
    valid_ids = [m['id'] for m in AI_MODELS.get(provider, [])]
    if saved in valid_ids:
        return saved
    # Default: primo modello della lista (sempre quello economico/consigliato)
    return valid_ids[0] if valid_ids else None

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
        current_month=get_italian_month()
    )

# Helper for AI Analysis
def analyze_plant_image(image_path, plant_name, species_hint=""):
    settings = get_app_settings()
    ai_provider = settings.ai_provider or 'openai'
    
    if ai_provider == 'openai':
        api_key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY')
    elif ai_provider == 'google':
        api_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY')
    else:  # openrouter
        api_key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY')
    
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

        if ai_provider == 'openai':
            import openai
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')

            selected_model = get_selected_model(settings, 'openai')
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=selected_model,
                messages=[
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
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            result = json.loads(response.choices[0].message.content)
        
        else: # Google Gemini / Gemma
            genai.configure(api_key=api_key)
            
            # Il modello scelto dall'utente viene provato per primo,
            # poi eventuali fallback nello stesso listino
            preferred = get_selected_model(settings, 'google')
            models_to_try = [preferred] + [
                m for m in [
                    'models/gemini-3.6-flash',
                    'models/gemini-2.5-flash', 
                    'models/gemini-flash-latest'
                ] if m != preferred
            ]
            
            result = None
            last_error = ""
            
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            for model_name in models_to_try:
                try:
                    print(f"Trying model: {model_name}...")
                    model = genai.GenerativeModel(model_name)
                    with open(image_path, "rb") as image_file:
                        image_data = image_file.read()
                    
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
                        result["model_used"] = model_name
                        print(f"Success with model: {model_name}")
                        break
                except Exception as e:
                    last_error = str(e)
                    print(f"Model {model_name} failed: {last_error}")
                    continue
            
            if result is None:
                raise Exception(f"Tutti i modelli provati hanno fallito. Ultimo errore: {last_error}")

        # Nota: niente 'return' anticipato nel ramo Google,
        # così is_mock viene impostato correttamente per TUTTI i provider
        result["is_mock"] = False
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
        
        if ai_provider == 'openai':
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=get_selected_model(settings, 'openai'),
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
        
        else: # Google Gemini / Gemma
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(get_selected_model(settings, 'google'))
            response = model.generate_content(prompt)
            return response.text.strip()
            
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
    
    if not api_key:
        return default_suggestions

    try:
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
        
        if ai_provider == 'openai':
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=get_selected_model(settings, 'openai'),
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            suggestions = data.get("suggestions", [])
            return suggestions if suggestions else default_suggestions
        
        else: # Google Gemini
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(get_selected_model(settings, 'google'))
            response = model.generate_content(prompt)
            data = json.loads(clean_ai_json(response.text))
            suggestions = data.get("suggestions", [])
            return suggestions if suggestions else default_suggestions
            
    except Exception as e:
        print(f"Errore get_seasonal_suggestions: {str(e)}")
        return default_suggestions


# --- ROUTES ---

@app.route('/')
def dashboard():
    # Fetch all tasks grouped by status and urgency
    urgent_tasks = Task.query.filter_by(status='pending', is_urgent=True).order_by(Task.created_at.desc()).all()
    pending_tasks = Task.query.filter_by(status='pending', is_urgent=False).order_by(Task.created_at.desc()).all()
    completed_tasks = Task.query.filter_by(status='completed').order_by(Task.created_at.desc()).limit(5).all()
    
    # Plants count
    plants_count = Plant.query.count()
    pending_count = Task.query.filter_by(status='pending').count()
    
    # Simple list of all plants to show care tips for the current season
    plants = Plant.query.all()
    
    return render_template('dashboard.html', 
                           urgent_tasks=urgent_tasks, 
                           pending_tasks=pending_tasks, 
                           completed_tasks=completed_tasks,
                           plants_count=plants_count,
                           pending_count=pending_count,
                           plants=plants)


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
    
    spring_care = (request.form.get('spring_care') or '').strip() or "Ricomincia a concimare una volta al mese. Innaffia con più regolarità."
    summer_care = (request.form.get('summer_care') or '').strip() or "Innaffia frequentemente, controllando che il terreno non si secchi del tutto. Proteggi dai raggi solari troppo intensi."
    autumn_care = (request.form.get('autumn_care') or '').strip() or "Riduci gradualmente le annaffiature. Sospendi le concimazioni. Riporta in casa se la pianta soffre il freddo."
    winter_care = (request.form.get('winter_care') or '').strip() or "Innaffia solo sporadicamente. Assicurati che la stanza sia luminosa e lontana dai termosifoni."
    
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
        image_url=image_url
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
        spring_care="Ricomincia a concimare una volta al mese. Innaffia con più regolarità.",
        summer_care="Innaffia frequentemente, controllando che il terreno non si secchi del tutto. Proteggi dai raggi solari troppo intensi.",
        autumn_care="Riduci gradualmente le annaffiature. Sospendi le concimazioni. Riporta in casa se la pianta soffre il freddo.",
        winter_care="Innaffia solo sporadicamente. Assicurati che la stanza sia luminosa e lontana dai termosifoni."
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


# --- AI DIAGNOSIS ---

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
        
        # Analyze using our helper
        diagnosis = analyze_plant_image(os.path.join(app.root_path, image_path), plant_name, species)
        
        # Pass variables to template for confirm/apply step
        return render_template('diagnose_result.html', 
                               diagnosis=diagnosis, 
                               image_url=full_image_url,
                               plant_id=plant_id,
                               custom_plant_name=plant_name,
                               species=species)

    return render_template('diagnose.html', plants=plants)


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
            spring_care="Ricomincia a concimare una volta al mese. Innaffia con più regolarità.",
            summer_care="Innaffia frequentemente, controllando che il terreno non si secchi del tutto. Proteggi dai raggi solari troppo intensi.",
            autumn_care="Riduci gradualmente le annaffiature. Sospendi le concimazioni. Riporta in casa se la pianta soffre il freddo.",
            winter_care="Innaffia solo sporadicamente. Assicurati che la stanza sia luminosa e lontana dai termosifoni."
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
        db.session.commit()
        
        flash("Configurazione salvata con successo! L'IA scelta è ora attiva (se hai inserito una chiave valida).", "success")
        return redirect(url_for('settings'))
    
    settings = get_app_settings()
    current_provider = settings.ai_provider or 'openai'
    current_model = get_selected_model(settings, current_provider)
    openai_key = settings.openai_api_key or os.environ.get('OPENAI_API_KEY') or ""
    google_key = settings.google_api_key or os.environ.get('GOOGLE_API_KEY') or ""
    openrouter_key = settings.openrouter_api_key or os.environ.get('OPENROUTER_API_KEY') or ""
    return render_template('settings.html', 
                           current_provider=current_provider, 
                           current_model=current_model,
                           ai_models=AI_MODELS,
                           openai_key=openai_key, 
                           google_key=google_key,
                           openrouter_key=openrouter_key)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Migrazione leggera: aggiunge la colonna ai_model se non esiste ancora
        from sqlalchemy import text
        with db.engine.connect() as conn:
            columns = [row[1] for row in conn.execute(text("PRAGMA table_info(settings)"))]
            if 'ai_model' not in columns:
                conn.execute(text("ALTER TABLE settings ADD COLUMN ai_model VARCHAR(100)"))
                conn.commit()
        
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
