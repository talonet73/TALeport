<!-- version: 1 -->
# system
Do a web search for the author. Look for evergreen material (guides, expert articles, case studies, interviews, research), not today's news. Use web search and report only what you actually read, with the link.
Answer in {{output_language}}, only with a valid JSON object, with no text before or after.

# user
Author's goal:
<<<
{{goal}}
>>>

Questions to cover:
{{questions}}

Languages of the sources: {{languages}}

Find 6-12 reliable sources and for each give 3-8 points useful for the goal (notions, rules, examples, experiences, mistakes, data, word-for-word quotes).

Format:
{"sources": [{"title": "", "url": "https://...", "author": "", "points": [""]}]}

# retry
The previous answer was not valid JSON for the required schema ({{error}}). Answer again only with the correct JSON object.
