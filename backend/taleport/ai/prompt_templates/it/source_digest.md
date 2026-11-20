<!-- version: 1 -->
# system
Estrai da una fonte i punti utili all'obiettivo dell'autore. Usa solo quello che c'è nella fonte: non aggiungere niente di tuo.
Rispondi in {{output_language}}, solo con un oggetto JSON valido, senza testo prima o dopo e senza blocchi di codice.

# user
Obiettivo dell'autore:
<<<
{{goal}}
>>>

Fonte ({{kind}}): {{title}}
<<<
{{content}}
>>>

Estrai fino a 15 punti utili all'obiettivo. Per ogni punto indica il tipo: "notion" (nozione), "rule" (regola), "example" (esempio), "experience" (esperienza raccontata), "mistake" (errore da evitare), "quote" (frase da citare, parola per parola), "data" (numero o dato). Se il testo ha i tempi [mm:ss], indica in "time" il momento in cui se ne parla. Aggiungi un riassunto di 2-3 frasi.

Formato:
{"summary": "", "points": [{"kind": "rule", "text": "", "time": ""}]}

# retry
La risposta precedente non era un JSON valido per lo schema richiesto ({{error}}). Rispondi di nuovo solo con l'oggetto JSON corretto.
