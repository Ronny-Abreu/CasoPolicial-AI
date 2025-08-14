from dotenv import load_dotenv
import os, time, csv, glob, json, requests

load_dotenv()

FOLDER = os.getenv("INPUT_FOLDER", "./imagenes_secretas")
OUT_CSV = os.getenv("OUT_CSV", "./salida/salida_caso.csv")

#Variables
VISION_ENDPOINT = os.getenv("VISION_ENDPOINT").rstrip("/")
VISION_KEY = os.getenv("VISION_KEY")
LANG_ENDPOINT = os.getenv("LANG_ENDPOINT")
LANG_KEY = os.getenv("LANG_KEY")
LANG_CODE = os.getenv("LANG_CODE", "es")
#----------------------------------------------


def ocr_image(path):
    url = VISION_ENDPOINT + "/vision/v3.2/read/analyze"
    headers = {"Ocp-Apim-Subscription-Key": VISION_KEY,
               "Content-Type": "application/octet-stream"}
    with open(path, "rb") as f:
        r = requests.post(url, headers=headers, data=f.read())
    if r.status_code not in (200, 202):
        return ""

    op_loc = r.headers.get("Operation-Location")
    if not op_loc:
        return ""

    for _ in range(60):
        poll = requests.get(op_loc, headers={"Ocp-Apim-Subscription-Key": VISION_KEY})
        data = poll.json()
        if data.get("status") == "succeeded":
            lines = []
            for page in data["analyzeResult"]["readResults"]:
                for ln in page["lines"]:
                    lines.append(ln["text"])
            return "\n".join(lines)

        elif data.get("status") == "failed":
            return ""
        time.sleep(1)
    return ""

def text_api(endpoint, text):
    if not text.strip():
        return None
    
    base_url = LANG_ENDPOINT.rstrip("/")
    
    # Versión más reciente de Text Analytics
    if endpoint == "keyPhrases":
        url = f"{base_url}/text/analytics/v3.1/keyPhrases"

    elif endpoint == "entities/recognition/general":
        url = f"{base_url}/text/analytics/v3.1/entities/recognition/general"

    else:
        url = f"{base_url}/text/analytics/v3.1/{endpoint}"
    
    headers = {"Ocp-Apim-Subscription-Key": LANG_KEY,
               "Content-Type": "application/json"}
    payload = {"documents":[{"id":"1","language":LANG_CODE,"text":text[:5000]}]}
    
    print(f"[DEBUG] Intentando endpoint: {url}")
    r = requests.post(url, headers=headers, json=payload)
    try:
        data = r.json()
    except Exception:
        return None
    
    print(f"[DEBUG] Status code: {r.status_code}")
    if r.status_code != 200 or "documents" not in data:
        print(f"[LANGUAGE ERROR] {endpoint} -> Status: {r.status_code}")
        print(f"[LANGUAGE ERROR] Respuesta: {json.dumps(data, ensure_ascii=False)}")
        return None
    
    print(f"[DEBUG] {endpoint} exitoso")
    return data

# Verificar carpeta salida/ exista
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

# Debug: Verifica que las credenciales se estén cargando
# print(f"Vision Endpoint: {VISION_ENDPOINT}")
# print(f"Language Endpoint: {LANG_ENDPOINT}")
# print(f"Language Key configurada: {'Sí' if LANG_KEY else 'No'}")
# print(f"Vision Key configurada: {'Sí' if VISION_KEY else 'No'}")
# print("-" * 50)

files = sorted(glob.glob(os.path.join(FOLDER, "caso_sec_img_*.*")))
if not files:
    print("No se encontraron imágenes en", FOLDER)

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    # Organización campos de sálida
    fieldnames = [
        "IMAGEN", 
        "TEXTO_OCR", 
        "PALABRAS_CLAVE", 
        "PERSONAS_IDENTIFICADAS",
        "ORGANIZACIONES", 
        "UBICACIONES",
        "FECHAS_HORARIOS",
        "CANTIDADES_MONTOS",
        "ENLACES_WEB",
        "OTRAS_ENTIDADES"
    ]
    
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    
    for path in files:
        print("Procesando:", os.path.basename(path))
        txt = ocr_image(path)
        keyp_data = text_api("keyPhrases", txt)
        ents_data = text_api("entities/recognition/general", txt)

        keyp = keyp_data["documents"][0]["keyPhrases"] if keyp_data else []
        ents = ents_data["documents"][0]["entities"] if ents_data else []

        # Organizar entidades por categoría
        personas = [e["text"] for e in ents if e.get("category") == "Person"]
        organizaciones = [e["text"] for e in ents if e.get("category") == "Organization"]
        ubicaciones = [e["text"] for e in ents if e.get("category") == "Location"]
        fechas = [e["text"] for e in ents if e.get("category") == "DateTime"]
        numeros = [e["text"] for e in ents if e.get("category") == "Quantity"]
        urls = [e["text"] for e in ents if e.get("category") == "URL"]
        otras = [e["text"] for e in ents if e.get("category") not in ["Person", "Organization", "Location", "DateTime", "Quantity", "URL"]]

        # Formatear texto para mejor legibilidad
        texto_formateado = txt.replace('\n', ' ').replace('  ', ' ').strip()
        texto_formateado = texto_formateado[:300] + "..." if len(texto_formateado) > 300 else texto_formateado

        w.writerow({
            "IMAGEN": os.path.basename(path),
            "TEXTO_OCR": texto_formateado,
            "PALABRAS_CLAVE": "; ".join(keyp[:10]),  # Máximo 10 palabras clave
            "PERSONAS_IDENTIFICADAS": "; ".join(personas),
            "ORGANIZACIONES": "; ".join(organizaciones),
            "UBICACIONES": "; ".join(ubicaciones),
            "FECHAS_HORARIOS": "; ".join(fechas),
            "CANTIDADES_MONTOS": "; ".join(numeros),
            "ENLACES_WEB": "; ".join(urls),
            "OTRAS_ENTIDADES": "; ".join(otras)
        })
        time.sleep(3)

#Debug para ver si se guardo correctamente el salida_caso.csv
print("Listo. Archivo guardado en:", OUT_CSV)

# Archivo de resumen para ver desde consola y sea más legible
resumen_file = OUT_CSV.replace('.csv', '_RESUMEN.txt')
with open(resumen_file, "w", encoding="utf-8") as f:
    f.write("="*80 + "\n")
    f.write("📊 RESUMEN DEL ANÁLISIS DE IMÁGENES - CASO POLICIAL\n")
    f.write("="*80 + "\n\n")
    
    for path in files:
        filename = os.path.basename(path)
        f.write(f"🔍 IMAGEN: {filename}\n")
        f.write("-" * 50 + "\n")
        
        # Leer datos del CSV para crear resumen
        with open(OUT_CSV, "r", encoding="utf-8") as csv_file:
            lines = csv_file.readlines()
            if len(lines) > 1:
                for line in lines[1:]:
                    if filename in line:
                        data = line.strip().split(',')
                        if len(data) >= 10:
                            f.write(f"📝 TEXTO EXTRAÍDO: {data[1][:200]}...\n")
                            f.write(f"🔑 PALABRAS CLAVE: {data[2]}\n")
                            f.write(f"👥 PERSONAS: {data[3]}\n")
                            f.write(f"🏢 ORGANIZACIONES: {data[4]}\n")
                            f.write(f"📍 UBICACIONES: {data[5]}\n")
                            f.write(f"📅 FECHAS: {data[6]}\n")
                            f.write(f"🔢 CANTIDADES: {data[7]}\n")
                            f.write(f"🌐 URLs: {data[8]}\n")
                            f.write(f"🔍 OTRAS: {data[9]}\n")
                        break
        f.write("\n" + "="*80 + "\n\n")

print(f"📄 Resumen creado en: {resumen_file}")

# Crear un resumen de los datos extraídos
print("\n" + "="*60)
print("📊 RESUMEN DE EXTRACCIÓN DE DATOS")
print("="*60)

for path in files:
    filename = os.path.basename(path)
    print(f"\n🔍 {filename}:")
    
    # Leer la última fila del CSV para mostrar el resumen
    with open(OUT_CSV, "r", encoding="utf-8") as f:
        lines = f.readlines()
        if len(lines) > 1:  # Hay datos además del header
            last_line = lines[-1].strip()
            if filename in last_line:
                print(f"   Procesado correctamente")
                print(f"   Texto extraído: {len(last_line.split(',')[1])} caracteres")
                print(f"   Palabras clave: {len(last_line.split(',')[2].split(' | ')) if ' | ' in last_line.split(',')[2] else 1} encontradas")
                print(f"   Personas: {len(last_line.split(',')[3].split(' | ')) if ' | ' in last_line.split(',')[3] else 0} identificadas")
                print(f"   Organizaciones: {len(last_line.split(',')[4].split(' | ')) if ' | ' in last_line.split(',')[4] else 0} encontradas")
                print(f"   Ubicaciones: {len(last_line.split(',')[5].split(' | ')) if ' | ' in last_line.split(',')[5] else 0} detectadas")
                print(f"   Fechas: {len(last_line.split(',')[6].split(' | ')) if ' | ' in last_line.split(',')[6] else 0} extraídas")
                print(f"   Números: {len(last_line.split(',')[7].split(' | ')) if ' | ' in last_line.split(',')[7] else 0} identificados")
                print(f"   URLs: {len(last_line.split(',')[8].split(' | ')) if ' | ' in last_line.split(',')[8] else 0} encontradas")

print("\n" + "="*60)
print("🎯 Análisis completado exitosamente")
print("="*60)
