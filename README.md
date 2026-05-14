# Mas que una VTuber Con Inteligencia Artificial Real para TODOS, una compañera Gamer.
<p align="center">
  <img src="https://i.postimg.cc/PxLbTvCX/9302f3e1-ad66-4197-87fa-f9372e76a239.png" width="220" alt="Karin VTuber IA Logo">
</p>

<h1 align="center">Karin VTuber -IA-</h1>

<p align="center">
  <strong>Asistente VTuber con Inteligencia Artificial para videojuegos y streaming.</strong>
</p>

<p align="center">
  OCR • OpenCV • IA Conversacional • Vision AI • TTS • Twitch • Automatización
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-beta-orange">
  <img src="https://img.shields.io/badge/version-v0.9.0-blue">
  <img src="https://img.shields.io/badge/python-3.10+-green">
  <img src="https://img.shields.io/badge/license-MIT-purple">
</p>

---

# 📌 ¿Qué es Karin VTuber -IA-?

Karin VTuber -IA- es un proyecto experimental de VTuber con inteligencia artificial diseñado para:

* Analizar videojuegos en tiempo real
* Leer texto mediante OCR
* Detectar movimiento y contexto visual
* Generar comentarios automáticos usando IA
* Hablar mediante síntesis de voz (TTS)
* Integrarse con Twitch
* Funcionar como comentarista IA interactiva

El proyecto combina múltiples tecnologías modernas como:

* OpenCV
* EasyOCR
* Groq Vision
* Cerebras
* edge-tts
* Vosk
* customtkinter
* Sistemas de reglas contextuales

Todo enfocado en crear una VTuber IA modular y extensible.

---

# ✨ Características Principales

## 🎮 Comentarista IA Gamer

Sistema capaz de analizar lo que ocurre en pantalla y generar comentarios automáticos contextuales.

### Modos disponibles:

| Modo              | Descripción                                 |
| ----------------- | ------------------------------------------- |
| OCR               | Solo lectura de texto detectado             |
| OpenCV + OCR + IA | Detección contextual avanzada               |
| Groq Vision       | Análisis visual completo mediante IA Vision |

---

## 👁️ OCR en Tiempo Real

* EasyOCR
* Tesseract OCR
* Lectura automática de texto
* Detección de keywords
* Comentarios basados en eventos

---

## 🧠 Inteligencia Artificial

Integración con modelos IA para generar:

* comentarios naturales
* reacciones dinámicas
* análisis del juego
* interacción en Twitch
* personalidad configurable

### APIs utilizadas

* Cerebras
* Groq
* Groq Vision

---

## 🎤 Audio y Voz

Sistema completo de entrada y salida de audio:

* edge-tts
* ecualizador de voz
* reproducción MP3
* Vosk Speech-To-Text
* sounddevice

---

## 📺 Twitch Integration

* OAuth2
* Chat IA
* Comandos personalizados
* Detección automática de videojuegos
* Integración con streaming

---

## 🔒 Seguridad

* Configuración separada
* Encriptación Fernet AES
* Protección de secretos
* Configuración modular

---

# 🧱 Arquitectura del Proyecto

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KARIN VTUBER -IA-  v0.9.0-beta                      │
│                         Asistente VTuber con IA                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │               UI                   │
                    │         (customtkinter)            │
                    │   7 pestañas + sidebar             │
                    └─────────────────┬─────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
   ┌────────────────┐      ┌──────────────────┐      ┌──────────────────┐
   │    TWITCH      │      │   CORE / SEGURIDAD│      │     AUDIO        │
   │                │      │                   │      │                  │
   │  • OAuth2      │      │  config.txt       │      │  edge-tts (TTS)  │
   │  • !comandos   │      │  (no sensible)    │      │  sounddevice     │
   │  • Chat IA     │      │                   │      │  ecualizador EQ  │
   │  • Detectar    │      │  secrets.enc      │      │  Vosk (STT)      │
   │    juego       │      │  (Fernet AES)     │      │  play_file(MP3)  │
   └────────┬───────┘      └────────┬──────────┘      └────────┬─────────┘
            │                      │                          │
            └──────────────────────┼──────────────────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │         COMENTARISTA         │
                    │   (3 modos de análisis)      │
                    └─────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │  OCR            │  │ OpenCV+OCR+IA   │  │ Groq Vision     │
   │  (Solo Lectura) │  │ (Recomendado)   │  │ (Máxima Exp)    │
   │                 │  │                 │  │                 │
   │ EasyOCR → TTS   │  │ EasyOCR → TTS   │  │ Captura →       │
   │ (sin análisis)  │  │ + Motion        │  │ base64 →        │
   │                 │  │ + Color         │  │ Groq Vision API │
   │                 │  │ + Background    │  │ → TTS           │
   │                 │  │ + Cerebras/Groq │  │                 │
   │                 │  │ + Prompts       │  │                 │
   └─────────────────┘  └─────────────────┘  └─────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
           ┌──────────────────┐        ┌──────────────────┐
           │  SENSORES OPENCV │        │  IA (Cerebras)   │
           │                  │        │                  │
           │  • Tesseract OCR │        │  ask_cerebras()  │
           │  • Motion Detect │        │  + prompt perso- │
           │  • Color HSV     │        │  nalidad         │
           │  • Background    │        │  → comentario    │
           │    Subtraction   │        │  natural         │
           └────────┬─────────┘        └────────┬─────────┘
                    ▼                          ▼
           ┌────────────────────────────────────────┐
           │         SISTEMA DE REGLAS              │
           │                                        │
           │  1. Keywords OCR → alerta inmediata    │
           │  2. Background + rojo → combate        │
           │  3. Objetos → comentario contextual    │
           │  4. Colores → ambientación             │
           │  5. Texto detectado → leer directamente│
           │  6. Color dominante → fallback         │
           └────────────────┬───────────────────────┘
                            ▼
                   ┌────────────────┐
                   │  TTS (voz)     │
                   │  edge-tts      │
                   │  + ecualizador │
                   └────────────────┘
```

---

# 🖥️ Interfaz

La interfaz principal está desarrollada con:

* customtkinter
* sidebar moderna
* múltiples pestañas
* sistema modular
* configuración integrada

## Incluye:

* panel OCR
* panel IA
* panel Twitch
* configuración de voz
* configuración de APIs
* sistema de comentarista
* herramientas de debug

---

# 🧩 Tecnologías Utilizadas

| Área              | Tecnología          |
| ----------------- | ------------------- |
| UI                | customtkinter       |
| OCR               | EasyOCR / Tesseract |
| Visión            | OpenCV              |
| Vision AI         | Groq Vision         |
| IA Conversacional | Cerebras / Groq     |
| TTS               | edge-tts            |
| STT               | Vosk                |
| Audio             | sounddevice         |
| Seguridad         | Fernet AES          |
| Streaming         | Twitch API          |

---

# ⚡ Instalación

## 1. Clonar repositorio

```bash
git clone https://github.com/manuel00084/Karin-VTuber--IA-.git
cd Karin-VTuber--IA-
```

---

## 2. Crear entorno virtual

```bash
python -m venv venv
```

### Windows

```bash
venv\Scripts\activate
```

### Linux / Mac

```bash
source venv/bin/activate
```

---

## 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## 4. Ejecutar aplicación

```bash
python main.py
```

---

# 📂 Estructura del Proyecto

```text
Karin-VTuber--IA-
│
├── assets/
├── audio/
├── config/
├── core/
├── ocr/
├── twitch/
├── vision/
├── ui/
├── secrets/
├── main.py
├── requirements.txt
└── README.md
```

---

# 🚧 Estado del Proyecto

⚠️ Proyecto experimental en desarrollo activo.

Algunas funciones aún están en fase beta.

## Estado actual:

* ✅ OCR funcional
* ✅ Sistema TTS
* ✅ Twitch integrado
* ✅ OpenCV funcionando
* ✅ Vision AI experimental
* ✅ Comentarista IA
* ⚠️ Optimización pendiente
* ⚠️ Compatibilidad Linux/Mac parcial
* ⚠️ Sistema VRM en evolución

---

# 🛣️ Roadmap

## v1.0

* [ ] Mejor estabilidad
* [ ] Sistema VRM completo
* [ ] Optimización OCR
* [ ] Mejoras de rendimiento
* [ ] Sistema de plugins

## Futuro

* [ ] Live2D
* [ ] Memoria conversacional
* [ ] Integración Twitch avanzada
* [ ] Soporte Linux
* [ ] Soporte MacOS
* [ ] Modo streamer autónomo
* [ ] IA emocional
* [ ] Integración multi-modelo

---

# 📸 Capturas

## Interfaz principal

```text
(Aquí puedes poner screenshots de la UI)
```

## Sistema OCR

```text
(Aquí puedes poner ejemplos del OCR)
```

## Comentarista IA

```text
(Aquí puedes poner imágenes del comentarista)
```

---

# 🤝 Contribuciones

Las contribuciones son bienvenidas.

Puedes ayudar con:

* optimización
* corrección de bugs
* soporte multiplataforma
* mejoras UI
* nuevas integraciones IA
* documentación

---

# 📜 Licencia

Este proyecto está bajo licencia MIT.

---

# ⭐ Objetivo del Proyecto

Karin VTuber -IA- busca explorar el futuro de:

* VTubers autónomas
* comentaristas IA
* análisis visual en videojuegos
* interacción en streaming
* companions IA en tiempo real

Combinando visión computacional, OCR y modelos de lenguaje modernos.

---

# ❤️ Créditos

Proyecto creado por:

## Manuel Montes de Oca

GitHub:

[https://github.com/manuel00084](https://github.com/manuel00084)
