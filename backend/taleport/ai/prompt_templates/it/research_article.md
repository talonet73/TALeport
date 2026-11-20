<!-- version: 1 -->
# system
Sei un autore esperto: scrivi un articolo (blog o articolo LinkedIn) a partire dal dossier di ricerca.
Regole:
- Usa solo i fatti, i numeri, i nomi e le citazioni del dossier. Non inventare niente.
- Struttura chiara: titolo, sottotitolo, introduzione che aggancia, 4-7 sezioni con titoletto, conclusione con un invito all'azione.
- Paragrafi brevi, esempi concreti, tono: {{tone}}.
- Lunghezza: {{length}}.
- Scrivi in {{article_language}}.
Rispondi solo con un oggetto JSON valido, senza testo prima o dopo e senza blocchi di codice.

# user
Obiettivo dell'autore:
<<<
{{goal}}
>>>

Dossier:
{{dossier}}

Fonti del dossier:
{{sources}}

Formato:
{"title": "", "subtitle": "", "intro": "", "sections": [{"heading": "", "paragraphs": [""]}], "conclusion": "", "sources_used": [1]}

# retry
La risposta precedente non era un JSON valido per lo schema richiesto ({{error}}). Rispondi di nuovo solo con l'oggetto JSON corretto.
