<!-- version: 1 -->
# system
Extrae de una fuente los puntos útiles para el objetivo del autor. Usa solo lo que hay en la fuente: no añadas nada propio.
Responde en {{output_language}}, solo con un objeto JSON válido, sin texto antes ni después y sin bloques de código.

# user
Objetivo del autor:
<<<
{{goal}}
>>>

Fuente ({{kind}}): {{title}}
<<<
{{content}}
>>>

Extrae hasta 15 puntos útiles para el objetivo. Para cada punto indica el tipo: "notion" (noción), "rule" (regla), "example" (ejemplo), "experience" (experiencia contada), "mistake" (error que evitar), "quote" (frase para citar, palabra por palabra), "data" (número o dato). Si el texto tiene tiempos [mm:ss], indica en "time" el momento en que se habla de ello. Añade un resumen de 2-3 frases.

Formato:
{"summary": "", "points": [{"kind": "rule", "text": "", "time": ""}]}

# retry
La respuesta anterior no era un JSON válido para el esquema requerido ({{error}}). Responde de nuevo solo con el objeto JSON correcto.
