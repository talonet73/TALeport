<!-- version: 1 -->
# system
Extract from a source the points that are useful for the author's goal. Use only what is in the source: add nothing of your own.
Answer in {{output_language}}, only with a valid JSON object, with no text before or after and no code blocks.

# user
Author's goal:
<<<
{{goal}}
>>>

Source ({{kind}}): {{title}}
<<<
{{content}}
>>>

Extract up to 15 points useful for the goal. For each point give its kind: "notion", "rule", "example", "experience" (a story someone tells), "mistake" (to avoid), "quote" (word for word), "data" (a number or figure). If the text has [mm:ss] timestamps, put in "time" the moment it is discussed. Add a 2-3 sentence summary.

Format:
{"summary": "", "points": [{"kind": "rule", "text": "", "time": ""}]}

# retry
The previous answer was not valid JSON for the required schema ({{error}}). Answer again only with the correct JSON object.
