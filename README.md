# VTUBER-IA-
Vtuber IA para Twitch 
Hola a todos Bienvenido esta pequeña aplicacion podra ayudarte a tener una Vtuber con IA (Inteligencia atificial) con el que podras usar con cualquier programa de Vtuber de tu eleccion atraves del microfono virtual, esta aplicacion solo es el intermediario entre une ENTRE tu cuenta de TWICH, LA IA Y EL TTS DE TU PC, para que funcione tendras que leer las instruciones y poder configurarlo con tus datos abajo esta las instruciones, mil disculpa no soy un buen programador mi nivel de novato. todo fue hecho en PYTHON, asi cual quiera pueda revisarlo y tener la confianza de que no hay nada raro y nada oculto. Quien quiera modeficarlo y mejorarlo son libres de hacerlo.

entre sus fuciones principales opciones son 
Bot speaker; para poder escuchar lo que nos platica el chat
!.- Voz neutral.
2.- poder usar Voz de hombre.
3.- poder usar voz de mujer.

Bot de IA; la principal funcion, siempre maneJara voz de Mujer. (se puede cambiar pero tendrias que mover el CODIGO)
1.- Nuestro chat de Twich podra interactuar platicar. 
2.- PROMPTS para darle personalidad a nuestra IA. 
3.- Un boton para poder comunicarnos con Nuestra IA atraves de nuestro microfono, por ahora solo funciona con el boton de la ventana.
4.- selecionar nuestra salida de Audio. 

===============================Instalaciones y configurar la aplicacion==================================================== 

Primero nececitaremos Instalar unas cosas y poder conseguir unas llaves y tokenspara poder usar la aplicacion, 


ARCHIVO CONFIG.TXT
Primero para que puedas Usar la aplicacion sin problemas Vas a tener que configurar la aplicacion esto lo aremos atraves del archivo config.txt dentro Basicamente bamos a poner llaves y token para poder conectar con twitch Y GROQ.
TRANQUIL@ aqui te enseñare a donde conseguir estos datos que nececitas.

Lo primero sera Bajar e instalar python nos vamos a esta pagina https://www.python.org/downloads/

continuamos ingresaremos a este sitio web https://dev.twitch.tv a que nos vamos inscribir  para obtener nuestras primeras llaves.
ya inscrito y logeado ve al dashboard dentro del dashboard en la parte izquirda ve a donde dice aplicaciones a tu derecha se vera una lista vacia daremos click en registra tu aplicacion
te saldra una paguina que te dira consola regrisra tu aplicacion.
NOmbre El que Gustes (MiVTuber)
URL de redireccionamiento de OAuth, Aqui vas a poner esto, copia y pega lo que esta entre comillas "http://localhost:3000" 
Categoria pon Aplication Integration.
Tipo de cliente, pones confidencial.
Y precionas el boton crear

ahora veras que la lista TU aplicacion creada, damos click en adminitrar
dentro obtener ID de cliente eso lo copiamos y lo colocamos en CLIENT_ID=akco617q7tr120************* Nota no debe exitir espacio ejemplo (CLIENT_ID=akco617q7tr120*************) si nopodra leer la llave y dara error.
abajo econtraremos nuestro numero secreto. damos click al boton y nos mostrara letras y numero copiamos y ahora lo pondremos en CLIENT_SECRET=diptiwoo5ms********

Ahora toca obtener el token de TWITCH abrimremos esta paguina https://twitchtokengenerator.com
dentro de la paguina nos saldra un ventana con un robot que dice bot chat token y carita con manos custom scope token, seleccionamos el robot "chat chat token" se abrira una nueva paguina en este caso de TWITCH solicitando Autorizacion, Damos Click para autorizar, abrira otra paguina nos saldra una ventana para resolver capthcap para confirmar que no somos un robot la ReSuelves, abajo en la paguina donde dice Generated Tokens encontraremos ACCESS TOKEN y copiamos y pegamos en TWITCH_TOKEN=7dmpcbreyv8kcjes3t6iidnrq19*********************** 
CHANNEL= Aqui colocamos el nombre del canal de tu canal de TWITCH, Pongo un ejemplo en este casi podre mi canal como emjempl ohttps://www.twitch.tv/manuel0084 por lo tanto pondre CHANNEL=manuel0084
NICK= Tu NicK de TWICH, por lo general biene siendo el nombre del canal a menos que Tu lo cambiaras, poniendo denuevo como ejemplo  NICK=manuel0084
guardemos nuestro archivo txt

Ahora vAmos a Conseguir nuestra Api de GROQ que era nuestra IA principal para todo, iremos a esta pagina https://console.groq.com/home  Yo me inscribi usando mi cuenta de google
ya cuando estes logeado en la parte de arriba a tu derecha hay una opcion que dice claro API KEY le damos click Ahora le damos al boton de crear api key nos saldra una ventana donde colocaremos el nombre pueser lo que keras lo que gustes  y abajo un tiempo de vida para nuestra api key selecciona la que gustes. y nos abrira una ventana nueva copia el texto que te da ya que esa es tu api key no la cierres por que no podremos recuperrla.
en caso de que cerrates y no copiates tendras que volver hacer la apikey.
donde la colocaremos en nuestra nuestro archivo de texto GROQ_API_KEY=

OK ya casi estamos listo ya tenemos lo principal.

PAra que podamos balar con nuestra IA vamos a esta paguina https://alphacephei.com/vosk/models
dentro de la paguina buscamos- Spanish- vosk-model-small-es-0.42 39M 16.02 (cv test) 16.72 (mtedx test) 11.21 (mls)
https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip

Descargamos el archivo .zip aqui es importante que lo que descargemos quede en una carpeta con el nombre vosk-model-small-es-0.42 esta carpeta lo moveremos a donde esta nuesta aplicacion.

En caso de que tengas problemas para ejecutar El archivo Main.py
abre en windows el CMD o simbolo de sistemas y iremos instalando estos archivos uno por uno 

pip install PyAudio
pip install SpeechRecognition
pip install edge-tts sounddevice soundfile
pip install customtkinter edge-tts sounddevice soundfile requests
pip install SpeechRecognition
pip install keyboard

Con esto nuestra aplicacion debera funcionar sin problemas.

===========================CONTENIDO DE LA APLICACION Y FUNCIONAMIENTO==========================================

ya que configurates el programa con "TUS DATOS" vamos con la funciones y como usar.

-------------BOT SPEAKER---------------
Esta funcion es muy secilla ya que con la funcion de TTS nos va leer el chat, para poder ser leidos susara estos 3 comandos 
!sp  usara unavos Neutra 
!sph Usara Voz de Hombre
!sp usara voz de mujer

------------BOT IA--------------------
La funcion principal de nuestra aplicacion, nuestro bot leera un comando que mandara la IA de GROQ a su ves nos respondera y la aplicacion Nops va leer el texto con Un TTS de nuestra PC.
POR DEFAULT LA VOZ POR EL TTS USARA VOZ DE MUJER.
!IA comando para hablar con la IA 

la aplicacion cuenta con una funcion de PROMPTS  que le dara mas personalidad a nuestra Vtuber ya trae por defecto unas 3 para seleccionar, pero puedes cear tus propias PROMPTS para que le des tu toque personal usando un bloc de notas de windows crear un archivo TXT con tus personalizacion Y lo pones en la carpeta de PROMT

Otra funcion es poder comunicarnos con nuestra IA Atraves del microfono STT esto solo podremos hacerlo atraves de la ventana pulsado el boton
