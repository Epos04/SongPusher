import json
import logging
import threading
import time
import concurrent.futures

from flask import Flask, request, jsonify, render_template
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# ----------------------------
# App & Logging
# ----------------------------
app = Flask(__name__, template_folder='templates', static_folder='static')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ----------------------------
# Datenhaltung
# ----------------------------
DATA_FILE = 'song_data.json'
PIN_FILE = 'pin_config.json'
DATA_LOCK = threading.Lock()

# Globale Variablen für den Abbruch-Mechanismus
CANCELLATION_TOKENS = set()
CANCELLATION_LOCK = threading.Lock()

def load_json(file_path, default=None):
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return default if default is not None else {}

def save_json(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# ----------------------------------------------------
# --- ZURÜCK ZUR BEWÄHRTEN SELENIUM-LOGIK ---
# ----------------------------------------------------

def get_driver():
    """Initialisiert einen WebDriver, der für die Docker-Umgebung konfiguriert ist."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument("--disable-gpu")
    
    # Feste Pfade innerhalb unseres Docker-Containers
    options.binary_location = "/usr/bin/google-chrome"
    service = Service(executable_path="/usr/local/bin/chromedriver-linux64/chromedriver")
    
    driver = webdriver.Chrome(service=service, options=options)
    
    location = {
        "latitude": 51.04720663792256,
        "longitude": 13.708293558601138,
        "accuracy": 100
    }
    driver.execute_cdp_cmd("Emulation.setGeolocationOverride", location)

    return driver


def vote_once_as_single_visitor(pin: str, song_id: str, song_title: str) -> bool:
    """
    Diese Funktion ist der Kern des Erfolgs: Sie simuliert EINEN kompletten Besuch.
    Browser starten -> Einloggen -> Suchen -> Voten -> Browser schließen.
    """
    # PRÜFUNG: Wurde der Song zum Abbruch markiert?
    with CANCELLATION_LOCK:
        if song_id in CANCELLATION_TOKENS:
            logging.warning(f"Thread {threading.get_ident()}: Vote für '{song_title}' (ID: {song_id}) wird wegen Abbruchs übersprungen.")
            return False # Zählt als nicht erfolgreicher Vote und stoppt die Ausführung hier

    driver = None
    logging.info(f"Thread {threading.get_ident()}: Neuer 'Besucher' startet für '{song_title}'.")
    try:
        driver = get_driver()
        wait = WebDriverWait(driver, 30)

        # 1. Einloggen
        driver.get("https://musikwunschapp.de/login")
        wait.until(EC.element_to_be_clickable((By.ID, "eventPinInput"))).send_keys(pin)
        wait.until(EC.element_to_be_clickable((By.ID, "loginButton"))).click()
        
        # 2. Suchen
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.title"))).click()
        search_input = wait.until(EC.presence_of_element_located((By.ID, "searchTerm")))
        search_input.send_keys(song_title)
        search_input.submit()

        # 3. Voten (mit der robusten ActionChains-Methode aus dem alten Code)
        vote_element = wait.until(EC.presence_of_element_located((By.ID, song_id)))
        # Scrollen und Warten auf Klickbarkeit ist der Schlüssel
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", vote_element)
        wait.until(EC.element_to_be_clickable(vote_element))
        
        ActionChains(driver).move_to_element(vote_element).click().perform()
        
        time.sleep(1.5) # Kurze Pause, damit der Vote registriert wird
        logging.info(f"Thread {threading.get_ident()}: Vote für '{song_title}' wurde erfolgreich registriert.")
        return True

    except Exception as e:
        logging.error(f"Thread {threading.get_ident()}: Ein 'Besucher' ist fehlgeschlagen. Fehler: {e}")
        return False
    finally:
        if driver:
            driver.quit()

# ----------------------------
# Worker-Logik
# ----------------------------
worker_state = {'is_running': False, 'current_song_id': None}
worker_lock = threading.Lock()

def process_song_in_parallel(song_id):
    """Verwaltet die 'Besucher' und wiederholt fehlgeschlagene Versuche."""
    with DATA_LOCK:
        all_songs = load_json(DATA_FILE, [])
        song_to_process = next((s for s in all_songs if s['id'] == song_id), None)
        pin = load_json(PIN_FILE).get('pin')

    if not song_to_process: return

    speed_map = {'slow': 2, 'medium': 5, 'fast': 10}
    speed = song_to_process.get('speed', 'medium')
    max_workers = speed_map.get(speed, 5)
    total_votes = int(song_to_process.get('votes', 1))
    song_title = song_to_process.get('title')
    completed_votes = 0

    logging.info(f"Starte Verarbeitung: {total_votes} 'Besucher' für '{song_title}' (max. {max_workers} gleichzeitig).")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Erstelle eine Liste aller zu erledigenden "Besuche"
        futures = {executor.submit(vote_once_as_single_visitor, pin, song_id, song_title) for _ in range(total_votes)}

        for future in concurrent.futures.as_completed(futures):
            if future.result():
                completed_votes += 1
            
            with DATA_LOCK:
                # Fortschritt aktualisieren
                current_data = load_json(DATA_FILE, [])
                target_song = next((s for s in current_data if s['id'] == song_id), None)
                if target_song:
                    target_song['progress'] = (completed_votes / total_votes) * 100
                    save_json(current_data, DATA_FILE)

    # Finale Statusaktualisierung
    with DATA_LOCK:
        final_data = load_json(DATA_FILE, [])
        target_song = next((s for s in final_data if s['id'] == song_id), None)
        if target_song:
            target_song['status'] = 'completed'
            target_song['progress'] = 100
            target_song['completedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            save_json(final_data, DATA_FILE)

    with worker_lock:
        worker_state['is_running'] = False
        worker_state['current_song_id'] = None
    
    # Token nach Abschluss der Verarbeitung entfernen, um die Liste sauber zu halten
    with CANCELLATION_LOCK:
        CANCELLATION_TOKENS.discard(song_id)
        
    logging.info(f"Verarbeitung für '{song_title}' beendet. Erfolgreiche Votes: {completed_votes}/{total_votes}.")

# --- (Der Rest der Datei: queue_worker, Flask-Routen, etc. bleibt unverändert) ---
def queue_worker():
    while True:
        with worker_lock:
            if worker_state['is_running']:
                time.sleep(3)
                continue
        next_song = None
        with DATA_LOCK:
            all_songs = load_json(DATA_FILE, [])
            next_song = next((s for s in all_songs if s.get('status') == 'queued'), None)
        if next_song:
            with worker_lock:
                worker_state['is_running'] = True
                worker_state['current_song_id'] = next_song['id']
            with DATA_LOCK:
                data = load_json(DATA_FILE, [])
                song = next((s for s in data if s['id'] == next_song['id']), None)
                if song: song['status'] = 'voting'
                save_json(data, DATA_FILE)
            threading.Thread(target=process_song_in_parallel, args=(next_song['id'],)).start()
        time.sleep(3)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search_songs():
    search_term = request.json.get('term')
    if not search_term: return jsonify({"error": "Suchbegriff fehlt"}), 400
    pin = load_json(PIN_FILE).get('pin')
    if not pin: return jsonify({"error": "PIN nicht gesetzt"}), 400
    driver = None
    try:
        driver = get_driver()
        wait = WebDriverWait(driver, 20)
        driver.get("https://musikwunschapp.de/login")
        wait.until(EC.element_to_be_clickable((By.ID, "eventPinInput"))).send_keys(pin)
        wait.until(EC.element_to_be_clickable((By.ID, "loginButton"))).click()
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.title"))).click()
        search_input = wait.until(EC.presence_of_element_located((By.ID, "searchTerm")))
        search_input.send_keys(search_term)
        search_input.submit()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "mw-app-mw-item")))
        results = []
        song_elements = driver.find_elements(By.CSS_SELECTOR, "mw-app-mw-item")
        for element in song_elements:
            try:
                song_id = element.find_element(By.CSS_SELECTOR, "div.item").get_attribute('id')
                title = element.find_element(By.CSS_SELECTOR, ".title").text
                artist = element.find_element(by=By.CSS_SELECTOR, value=".sub-title").text
                if song_id and title:
                    results.append({"id": song_id, "title": title, "artist": artist})
            except:
                continue
        return jsonify(results)
    except Exception as e:
        logging.error(f"Fehler bei der Song-Suche: {e}")
        return jsonify({"error": "Suche fehlgeschlagen"}), 500
    finally:
        if driver:
            driver.quit()

@app.route('/api/data', methods=['GET', 'POST'])
def handle_data():
    with DATA_LOCK:
        if request.method == 'GET':
            return jsonify(load_json(DATA_FILE, []))
        if request.method == 'POST':
            new_data = request.get_json()
            new_ids = {s['id'] for s in new_data}

            # Finde heraus, welche laufenden Songs entfernt wurden
            current_data = load_json(DATA_FILE, [])
            # Wir interessieren uns nur für Songs, die gerade im "voting"-Status sind
            active_voting_ids = {s['id'] for s in current_data if s.get('status') == 'voting'}
            
            deleted_ids = active_voting_ids - new_ids
            
            if deleted_ids:
                with CANCELLATION_LOCK:
                    for song_id in deleted_ids:
                        logging.info(f"Song {song_id} wurde entfernt. Signal zum Abbruch wird gesetzt.")
                        CANCELLATION_TOKENS.add(song_id)

            save_json(new_data, DATA_FILE)
            return jsonify({"status": "ok"})

@app.route('/api/pin', methods=['GET', 'POST'])
def handle_pin():
    with DATA_LOCK:
        if request.method == 'GET':
            return jsonify(load_json(PIN_FILE, {}))
        if request.method == 'POST':
            save_json(request.get_json(), PIN_FILE)
            return jsonify({"status": "ok"})

# Den Hintergrund-Worker für die Warteschlange sofort beim Laden der App starten
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()
logging.info("Hintergrund-Worker für die Warteschlange wurde gestartet.")

# Dieser Block wird jetzt nur noch für lokales Testen mit 'python app.py' benötigt
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)