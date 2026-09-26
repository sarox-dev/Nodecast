# User guide

## Intended workflow

1. Highlight something worth remembering in the browser.
2. Press the floating **Save** button beside the selection. `Alt+Shift+S` and the right-click menu remain backup methods.
3. Continue reading; atomic extraction runs in the background.
4. Later, search in Nodecast and read compact Memory Cards with links back to their exact sources.
5. Nodecast selects List, Focus, Compare or Problem output for the query. If AI is unavailable, local results and Sources still work without synthesis.
6. Use Concepts and the focused Graph to inspect connections created across different saves.

Saving without a highlight creates a bookmark. It preserves where to return but does not claim that the whole page is useful knowledge.

Connect and configure the extension from **Settings → Extension** in Nodecast Core. The page detects an installed extension without relying on a fixed browser extension ID. Connecting uses a short-lived, single-use pairing code; the resulting API token stays inside the extension and is never exposed to page JavaScript. Floating-button state, minimum selection length, notification position and default project are stored per Nodecast account and synchronized to the extension.

AI providers are configured under Settings → AI. Assign models to atomic extraction, entity extraction and aggregate creation. Local OpenAI-compatible providers such as LM Studio and Ollama can keep processing on the user's machine.

The **Web Search** workspace can be used as a browser start page. Under **Settings → Search**, choose the engine that receives the query after Enter and, independently, the provider that supplies type-ahead suggestions. DuckDuckGo, Google, Bing, Brave, Startpage and a custom `{query}` URL template are supported as redirect targets; suggestions can come from DuckDuckGo, Google, Bing or be disabled. Nodecast never proxies the final result page.

Useful queries include normal keyword search and `/entities`, `/facts`, `/compare`, `/sources`, `/timeline`, `/table`, and `/markdown`. Some specialized views remain roadmap work; the atomic card/search view is the current baseline.
