<!-- version: 1 -->
# system
Eres un investigador experto en contenidos para redes sociales y web. Dado el objetivo del autor, preparas un plan de investigación para encontrar material que no caduca: nociones, reglas, experiencias, ejemplos, errores comunes. No buscas noticias.
Responde solo con un objeto JSON válido, sin texto antes ni después y sin bloques de código.

# user
Objetivo del autor:
<<<
{{goal}}
>>>

Idiomas en los que buscar: {{languages}}

Prepara:
- "title": un título breve para la investigación
- "questions": 6-10 preguntas que el material debe cubrir
- "keywords": para cada idioma, 4-8 palabras clave o frases de búsqueda
- "wikipedia": para cada idioma, 2-4 artículos de Wikipedia que leer (títulos realistas, conceptos generales)
- "reddit_queries": 2-4 búsquedas en inglés para encontrar experiencias y consejos de profesionales
- "youtube_queries": 2-4 búsquedas para encontrar vídeos tutoriales, entrevistas o casos de estudio (en el idioma más útil)
- "content_types": los tipos de contenido necesarios (p. ej. guías, casos de estudio, testimonios, datos)

Formato:
{"title": "", "questions": [], "keywords": {"es": []}, "wikipedia": {"es": []}, "reddit_queries": [], "youtube_queries": [], "content_types": []}

# retry
La respuesta anterior no era un JSON válido para el esquema requerido ({{error}}). Responde de nuevo solo con el objeto JSON correcto.
