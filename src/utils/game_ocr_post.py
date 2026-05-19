"""
game_ocr_post.py - Post-procesador avanzado
Corrige errores de OCR + detecta idioma + corrector ortografico ligero
Idiomas: espanol, ingles, japones, chino, coreano
"""
import re

# ── DETECTOR DE IDIOMA ──

def detectar_idioma(texto):
    """
    Detecta el idioma del texto basado en rangos Unicode.
    Retorna: 'es', 'en', 'ja', 'zh', 'ko' o 'unknown'
    """
    if not texto:
        return 'unknown'

    # Contar caracteres por rango
    rangos = {
        'ko': [(0xAC00, 0xD7AF)],  # Hangul
        'ja': [(0x3040, 0x309F), (0x30A0, 0x30FF)],  # Hiragana, Katakana
        'zh': [(0x4E00, 0x9FFF)],  # CJK unificados
        'es': [(0x00C0, 0x00FF), (0x00A1, 0x00BF)],  # Latin extended + espanol
    }

    scores = {'es': 0, 'en': 0, 'ja': 0, 'zh': 0, 'ko': 0}

    for c in texto:
        cp = ord(c)
        for lang, ranges in rangos.items():
            for start, end in ranges:
                if start <= cp <= end:
                    scores[lang] += 1
                    break

    # Palabras clave en espanol (si no hay caracteres especiales)
    if scores['es'] == 0 and scores['ja'] == 0 and scores['zh'] == 0 and scores['ko'] == 0:
        palabras_es = ['el', 'la', 'los', 'las', 'de', 'del', 'en', 'con', 'por', 'para',
                       'que', 'es', 'son', 'esta', 'hay', 'no', 'si', 'un', 'una',
                       'y', 'e', 'o', 'a', 'ante', 'bajo', 'se', 'le', 'les', 'nos']
        palabras_en = ['the', 'is', 'are', 'was', 'were', 'have', 'has', 'been',
                       'will', 'would', 'could', 'should', 'may', 'might', 'this',
                       'that', 'with', 'from', 'your', 'our', 'their', 'there']

        texto_lower = texto.lower()
        score_es = sum(1 for p in palabras_es if re.search(r'\b' + p + r'\b', texto_lower))
        score_en = sum(1 for p in palabras_en if re.search(r'\b' + p + r'\b', texto_lower))

        if score_es >= score_en and score_es > 0:
            scores['es'] += score_es * 2
        elif score_en > 0:
            scores['en'] += score_en * 2

    # Devolver el idioma con mayor puntuacion
    mejor = max(scores, key=scores.get)
    return mejor if scores[mejor] > 0 else 'unknown'


# ── CORRECTOR ORTOGRAFICO LIGERO (basado en diccionario de palabras de juegos) ──

# Palabras comunes en juegos por idioma
_PALABRAS_JUEGO = {
    # Espanol
    'ataque', 'defensa', 'habilidad', 'inventario', 'mochila', 'equipo',
    'personaje', 'enemigo', 'aliado', 'jefe', 'nivel', 'experiencia',
    'moneda', 'oro', 'plata', 'poder', 'velocidad', 'resistencia',
    'inteligencia', 'destreza', 'carisma', 'suerte', 'salud', 'mana',
    'energia', 'dano', 'curar', 'pocion', 'mision', 'objetivo',
    'tutorial', 'configuracion', 'opcion', 'guardar', 'cargar',
    'cancelar', 'confirmar', 'aceptar', 'rechazar', 'saltar',
    'cerrar', 'volver', 'regresar', 'salir', 'continuar',
    'juego', 'jugador', 'pantalla', 'mundo', 'mapa', 'tesoro',
    'cofre', 'puerta', 'llave', 'palanca', 'interruptor', 'boton',
    # Ingles
    'attack', 'defense', 'skill', 'inventory', 'health', 'damage',
    'heal', 'mana', 'level', 'experience', 'quest', 'objective',
    'player', 'enemy', 'boss', 'ally', 'npc', 'character',
    'settings', 'options', 'save', 'load', 'cancel', 'confirm',
    'accept', 'decline', 'continue', 'exit', 'back', 'menu',
    'play', 'start', 'pause', 'resume', 'restart', 'quit',
    'loading', 'saving', 'connecting', 'waiting', 'ready',
    'single', 'multiplayer', 'campaign', 'tutorial', 'training',
    'chest', 'door', 'key', 'switch', 'lever', 'portal',
}

_PALABRAS_FRECUENTES = {
    'es': {'que', 'de', 'en', 'la', 'el', 'los', 'las', 'con', 'por', 'para',
           'del', 'una', 'un', 'mas', 'pero', 'como', 'esta', 'este', 'entre',
           'todo', 'nada', 'algo', 'cada', 'muy', 'as', 'oir', 'sin', 'sobre',
           'tambien', 'cuando', 'donde', 'quien', 'nunca', 'siempre'},
    'en': {'the', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'been',
           'can', 'will', 'may', 'would', 'could', 'should', 'must', 'might',
           'this', 'that', 'these', 'those', 'with', 'without', 'from', 'into',
           'over', 'under', 'between', 'through', 'during', 'before', 'after'},
}


def corregir_ortografia(texto, idioma='es'):
    """
    Corrector ortografico ligero basado en diccionario.
    Busca palabras mal escritas y las corrige con la mas similar del diccionario.
    """
    palabras = texto.split()
    corregidas = []

    for palabra in palabras:
        p_clean = palabra.strip('.,!?¡¿:;-\'"()[]{}').lower()
        if len(p_clean) < 3:
            corregidas.append(palabra)
            continue

        # Verificar si la palabra ya es correcta
        if p_clean in _PALABRAS_JUEGO or p_clean in _PALABRAS_FRECUENTES.get(idioma, set()):
            corregidas.append(palabra)
            continue

        # Buscar la palabra mas similar en el diccionario
        mejor_dist = 999
        mejor_sim = 0
        mejor_palabra = palabra

        for dict_palabra in _PALABRAS_JUEGO:
            # Distancia simple: caracteres en comun / longitud
            comunes = sum(1 for c in p_clean if c in dict_palabra)
            max_len = max(len(p_clean), len(dict_palabra))
            if max_len == 0:
                continue
            similitud = comunes / max_len
            dist = abs(len(p_clean) - len(dict_palabra))

            # Si es muy similar y misma longitud, es probable correccion
            if similitud > 0.7 and dist <= 2:
                if dist < mejor_dist or (dist == mejor_dist and similitud > mejor_sim):
                    mejor_dist = dist
                    mejor_palabra = dict_palabra
                    mejor_sim = similitud

        # Mantener mayuscula original si aplica
        if palabra[0].isupper() and mejor_palabra != palabra:
            mejor_palabra = mejor_palabra.capitalize()
        corregidas.append(mejor_palabra)

    return ' '.join(corregidas)


# ── CORRECCIONES ESPECIFICAS (mantenidas del original) ──
PATRONES_PALABRAS = [
    (r'\bSSTAR[Dd][Ii][Vv][Ee]\b', 'STARDIVE'),
    (r'\bConaeo\b',  'Conejo'),
    (r'\bdisfmssr\b',  'disfrutar'),
    (r'\bdisfrussr\b', 'disfrutar'),
    (r'\bdisfrursr\b', 'disfrutar'),
    (r'\bexcerienc[3ia]\b', 'experiencia'),
    (r'\bexceriencia\b', 'experiencia'),
    (r'\bNctificacion\b', 'Notificacion'),
    (r'\bmonstmos?\b', 'monstruos'),
    (r'\bmonsmuitos?\b', 'monstruos'),
    (r'\bcame\b', 'carne'),
    (r'\bcames\b', 'carnes'),
    (r'\bfngor[i]fic[oó]\b', 'frigorifico'),
    (r'\bCargand[oó]\.\.\d+%\b', 'Cargando'),
    (r'\bCsrganda\b', 'Cargando'),
    (r'\bCegendo\b', 'Cargando'),
    (r'\bestais\b', 'estais'),
    (r'\bestas\b', 'estas'),
    (r'\bmas\b', 'mas'),
    (r'\bDistnto\b', 'Distrito'),
    (r'\bDistnta\b', 'Distrito'),
    (r'\bTutonal\b', 'Tutorial'),
    (r'\bTutnrial\b', 'Tutorial'),
    (r'\bDrdenador\b', 'Ordenador'),
    (r'\bavenado\b', 'averiado'),
    (r'\bavenisdo\b', 'averiado'),
    (r'\bMensaj[3e]\b', 'Mensaje'),
    (r'\bSelecciona[r]\b', 'Seleccionar'),
    (r'\bContinu[3a]r\b', 'Continuar'),
    (r'\bGuard[3a]r\b', 'Guardar'),
    (r'\bConfig[u]r[3a]ci[oó]n\b', 'Configuracion'),
    (r'\bPers[oó]n[3a]j[3e]\b', 'Personaje'),
    (r'\bHistori[3a]\b', 'Historia'),
    (r'\bNiv[3e]l\b', 'Nivel'),
    (r'\bSal[ií]r\b', 'Salir'),
    (r'\bOpci[oó]n\b', 'Opcion'),
    (r'\bInven[t]ari[oó]\b', 'Inventario'),
    (r'\bMochil[3a]\b', 'Mochila'),
    (r'\bEquip[oO]\b', 'Equipo'),
    (r'\bHabilid[3a]d\b', 'Habilidad'),
    (r'\bAtaqu[e]\b', 'Ataque'),
    (r'\bDefen[d]er\b', 'Defender'),
    (r'\bHechiz[oO]\b', 'Hechizo'),
    (r'\bMag[ií]a\b', 'Magia'),
    (r'\bFuerz[3a]\b', 'Fuerza'),
    (r'\bVid[3a]\b', 'Vida'),
    (r'\bMisi[oó]n\b', 'Mision'),
    (r'\bObjetiv[oO]\b', 'Objetivo'),
    (r'\bTutorial\b', 'Tutorial'),
    (r'\bArchiv[oO]\b', 'Archivo'),
    (r'\bJugador\b', 'Jugador'),
    (r'\bEnemig[oO]\b', 'Enemigo'),
    (r'\bAliad[oO]\b', 'Aliado'),
    (r'\bJef[e]\b', 'Jefe'),
    (r'\bExperienci[3a]\b', 'Experiencia'),
    (r'\bMoned[3a]\b', 'Moneda'),
    (r'\bCancelar\b', 'Cancelar'),
    (r'\bConfirmar\b', 'Confirmar'),
    (r'\bAceptar\b', 'Aceptar'),
    (r'\bDesconectado\b', 'Desconectado'),
    (r'\bMostrar m[á]s\b', 'Mostrar mas'),
    (r'\bCanales en vivo\b', 'Canales en vivo'),
    # Ingles
    (r'\bContin[ue]\b', 'Continue'),
    (r'\bOpti[o]n[s]?\b', 'Options'),
    (r'\bPaus[3e]\b', 'Pause'),
    (r'\bResum[3e]\b', 'Resume'),
    (r'\bInventory\b', 'Inventory'),
    (r'\bCharacter\b', 'Character'),
    (r'\bSettings\b', 'Settings'),
    (r'\bGraphics\b', 'Graphics'),
    (r'\bResolution\b', 'Resolution'),
    (r'\bLanguage\b', 'Language'),
    (r'\bControls\b', 'Controls'),
    (r'\bKeyboard\b', 'Keyboard'),
    (r'\bGamepad\b', 'Gamepad'),
    (r'\bMultiplayer\b', 'Multiplayer'),
    (r'\bCampaign\b', 'Campaign'),
    (r'\bDifficulty\b', 'Difficulty'),
]


def corregir_texto_juego(texto):
    """Corrige texto aplicando patrones especificos + ortografia."""
    t = texto
    for pat, rep in PATRONES_PALABRAS:
        try:
            t = re.sub(pat, rep, t, flags=re.IGNORECASE)
        except:
            pass
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def filtrar_texto_valido(texto, confianza, conf_min=0.3):
    """Filtra basura."""
    texto = texto.strip()
    if len(texto) < 2:
        return False
    if confianza < conf_min:
        return False
    if re.match(r'^[\W_]+$', texto):
        return False
    buenos = ' .,!?¡¿:;-\'"áéíóúüñÁÉÍÓÚÜÑabcdefghijklmnñopqrstuvwxyz'
    s = sum(1 for c in texto if c.isalnum() or c in buenos or ord(c) > 255)
    if len(texto) > 3 and s / len(texto) < 0.3:
        return False
    return True


def post_procesar_ocr(resultados, conf_min=0.3):
    """Post-procesa resultados: filtra, corrige, detecta idioma y corrige ortografia."""
    # Detectar idioma del primer texto con suficiente longitud
    idioma_detectado = 'unknown'
    for r in resultados:
        if len(r['text']) > 5:
            idioma_detectado = detectar_idioma(r['text'])
            if idioma_detectado != 'unknown':
                break

    out = []
    for r in resultados:
        if not filtrar_texto_valido(r['text'], r['score'], conf_min):
            continue
        t = corregir_texto_juego(r['text'])
        if idioma_detectado in ('es', 'en'):
            t = corregir_ortografia(t, idioma_detectado)
        if t.strip():
            out.append({'text': t, 'score': r['score'], 'box': r['box']})
    return out