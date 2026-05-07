<p align="center">
![Logo](https://i.postimg.cc/PxLbTvCX/9302f3e1-ad66-4197-87fa-f9372e76a239.png)
</p>

<h1 align="center">VTUBER IA</h1>

<p align="center">
Sistema VTuber con IA, voz y Twitch
</p>


<p align="center">
VTUBER IA busca crear una plataforma accesible y modular para VTubers con inteligencia artificial, permitiendo interacción en tiempo real con usuarios de Twitch mediante voz, chat e IA conversacional.
siendo un sistema VTuber con integración de IA, voz TTS, interacción con Twitch y soporte para prompts personalizados.
El objetivo principal es combinar:
</p>

🤖 Inteligencia artificial
🔊 Síntesis de voz
🎤 Reconocimiento de voz
💬 Integración con Twitch
🎭 Personalidades dinámicas

para crear una experiencia de VTuber más interactiva, autónoma y personalizable.

Además, el proyecto busca servir como base para futuras funciones como:

Expresiones automáticas
Integración con modelos VRM
Memoria conversacional
Reacciones emocionales
Automatización de stream
Sistemas de recompensas y eventos

La meta es desarrollar una VTuber IA capaz de interactuar con la comunidad de forma natural y entretenida, manteniendo una arquitectura abierta y fácil de expandir.

Proyecto creado por Manuel0084


-------------------------------------------------------------------------------------------------
✨ Características
🤖 Integración con IA usando Groq
🔊 Text To Speech (TTS)
🎤 Speech To Text (STT)
💬 Integración con chat de Twitch
🎭 Sistema de prompts personalizables
🎧 Selección de dispositivos de audio
⌨️ Push To Talk (F9)
🖥️ Interfaz gráfica con CustomTkinter
🔥 Arquitectura modular

-------------------------------------------------------------------------------------------------
📦 Tecnologías utilizadas
Python
CustomTkinter
Edge-TTS
Groq API
Twitch IRC
Speech Recognition
PyAudio

-------------------------------------------------------------------------------------------------
📁 Estructura del proyecto
VTUBER-IA/
│
├── PROMT/
├── audio.py
├── config.py
├── devices.py
├── ia.py
├── main.py
├── ptt.py
├── stt.py
├── twitch_bot.py
└── requirements.txt

-------------------------------------------------------------------------------------------------
⚙️ Requisitos
🐍 Python
Se recomienda:

Python 3.11

-------------------------------------------------------------------------------------------------
🔧 Instalación
1️⃣ Clonar repositorio

git clone https://github.com/manuel00084/VTUBER-IA-.git

cd VTUBER-IA-

-------------------------------------------------------------------------------------------------
3️⃣ Instalar dependencias
pip install -r requirements.txt

📦 Dependencias importantes

Si alguna falla manualmente:

pip install customtkinter
pip install edge-tts
pip install requests
pip install keyboard
pip install pyaudio
pip install SpeechRecognition

-------------------------------------------------------------------------------------------------
🎤 Configuración de audio
La aplicación permite seleccionar:

🔊 Bot Speaker
🤖 Voz IA
🎧 Monitor/Auriculares

Para mejores resultados se recomienda:

VB-CABLE
VoiceMeeter Banana

-------------------------------------------------------------------------------------------------
🤖 API Groq

Necesitas una API Key de Groq

Sitio oficial:
👉 https://console.groq.com/

-------------------------------------------------------------------------------------------------
▶️ Ejecutar aplicación
python main.py

🎭 Prompts personalizados

Los prompts se almacenan en:

PROMT/

Puedes crear archivos .txt para cambiar la personalidad de la IA.

Ejemplo:

Eres una VTuber divertida y energética.

-------------------------------------------------------------------------------------------------
🧠 Funciones IA

Conversación en tiempo real
Respuestas por voz
Personalidad configurable
Integración con chat
-------------------------------------------------------------------------------------------------

⚠️ Problemas comunes
❌ PyAudio no instala

Windows suele necesitar wheel manual.

Puedes descargarlo aquí:
👉 https://www.lfd.uci.edu/~gohlke/pythonlibs/

❌ Twitch no conecta

Verificar:

OAuth válido
Canal correcto
Internet activo
❌ No se escucha audio

Revisar:

Dispositivo seleccionado
VB-CABLE
VoiceMeeter
