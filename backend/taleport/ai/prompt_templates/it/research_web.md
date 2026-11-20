<!-- version: 1 -->
# system
Fai una ricerca sul web per l'autore. Cerca materiale che non scade (guide, articoli di esperti, casi studio, interviste, ricerche), non notizie del giorno. Usa la ricerca web e riporta solo quello che hai letto davvero, con il link.
Rispondi in {{output_language}}, solo con un oggetto JSON valido, senza testo prima o dopo.

# user
Obiettivo dell'autore:
<<<
{{goal}}
>>>

Domande da coprire:
{{questions}}

Lingue delle fonti: {{languages}}

Trova 6-12 fonti affidabili e per ognuna riporta 3-8 punti utili all'obiettivo (nozioni, regole, esempi, esperienze, errori, dati, citazioni parola per parola).

Formato:
{"sources": [{"title": "", "url": "https://...", "author": "", "points": [""]}]}

# retry
La risposta precedente non era un JSON valido per lo schema richiesto ({{error}}). Rispondi di nuovo solo con l'oggetto JSON corretto.
