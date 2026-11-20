<!-- version: 1 -->
# system
Haz una búsqueda en la web para el autor. Busca material que no caduca (guías, artículos de expertos, casos de estudio, entrevistas, investigaciones), no noticias del día. Usa la búsqueda web e informa solo de lo que has leído de verdad, con el enlace.
Responde en {{output_language}}, solo con un objeto JSON válido, sin texto antes ni después.

# user
Objetivo del autor:
<<<
{{goal}}
>>>

Preguntas que cubrir:
{{questions}}

Idiomas de las fuentes: {{languages}}

Encuentra 6-12 fuentes fiables y para cada una indica 3-8 puntos útiles para el objetivo (nociones, reglas, ejemplos, experiencias, errores, datos, citas palabra por palabra).

Formato:
{"sources": [{"title": "", "url": "https://...", "author": "", "points": [""]}]}

# retry
La respuesta anterior no era un JSON válido para el esquema requerido ({{error}}). Responde de nuevo solo con el objeto JSON correcto.
