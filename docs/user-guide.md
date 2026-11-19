# User guide

## Intended workflow

1. Highlight something worth remembering in the browser.
2. Press the floating **Save** button beside the selection. `Alt+Shift+S` and the right-click menu remain backup methods.
3. Continue reading; atomic extraction runs in the background.
4. Later, open **Ask your library** and ask the question in your own words. Nodecast returns compact evidence cards with links back to their exact sources.
5. If you assign a **Recall synthesis** model in Settings → AI, Nodecast can produce a short answer whose sections link to the evidence that supports them. If AI is unavailable, local results and Sources still work without synthesis.
6. Use Concepts and the focused Graph to inspect connections created across different saves.

Saving a whole page with HTML queues deterministic extraction of its useful text. A highlight is indexed even when no HTML snapshot is supplied. A metadata-only bookmark is kept as a source reference and is not advertised as indexed text.

Connect and configure the extension from **Settings → Extension** in Nodecast Core. The page detects an installed extension without relying on a fixed browser extension ID. Connecting uses a short-lived, single-use pairing code; the resulting API token stays inside the extension and is never exposed to page JavaScript. Floating-button state, minimum selection length, notification position and default project are stored per Nodecast account and synchronized to the extension.

AI is optional. Saving and local source search do not need a provider, API key or subscription. Providers are configured under Settings → AI; assign models for optional extraction enrichment and Recall synthesis; entity extraction and aggregate creation remain available for later enrichment. Local OpenAI-compatible providers such as LM Studio and Ollama can keep processing on the user's machine. **ChatGPT subscription** connects an eligible Plus or Pro account without copying an API key. It does not expose ChatGPT conversations or Memory to Nodecast; only evidence selected for the current Nodecast operation is sent.

Each feature has its own provider and model selector. For ChatGPT subscription, Nodecast
loads the connected account's eligible model catalog and displays the official model names.

The **Web Search** workspace can be used as a browser start page. Under **Settings → Search**, choose the engine that receives the query after Enter and, independently, the provider that supplies type-ahead suggestions. DuckDuckGo, Google, Bing, Brave, Startpage and a custom `{query}` URL template are supported as redirect targets; suggestions can come from DuckDuckGo, Google, Bing or be disabled. Nodecast never proxies the final result page.

Useful queries include normal keyword search and `/entities`, `/facts`, `/compare`, `/sources`, `/timeline`, `/table`, and `/markdown`. Some specialized views remain roadmap work; the atomic card/search view is the current baseline.


## First-use tour and community

A member account sees a short workspace tour the first time it opens the workspace.
Choose **Skip tour**, **×**, or Escape on any step to close it immediately, including the first popup.
Completion or dismissal is stored for that account. Another member has a separate preference.
Replay it anytime from **Settings → Overview → Replay quick tour**.

The tour explains where Settings is, how to connect the browser extension, save a passage,
switch **Web** to **Ask**, and follow saved evidence back to its source. It does not create
sample captures, configure AI, or change your search mode.

**Join the [Nodecast Discord community](https://discord.gg/tFAM5JST4U)** for help and feedback.
The invite opens the rules channel. The same link is available in Settings → Overview
and the final tour popup.

## Check the basic workflow without AI

1. Sign in with a Library member account that has no AI providers configured.
2. Connect the extension from Settings → Extension.
3. Save a distinctive passage from a page you can revisit. Wait briefly for background indexing.
4. In Nodecast, switch Web to Ask and search for a distinctive phrase from that passage.
5. Confirm that the saved excerpt and source link appear. No AI setup should be required.
6. Open the original source and compare the excerpt with the saved text.

Older unindexed captures with saved selection text or HTML are eligible for the background
processor, including jobs skipped by the older no-HTML processor. Existing indexed captures
are left alone. Automatic recovery follows the existing processing interval and does not run
when that interval is disabled. Explicit **Re-extract** rebuilds derived atomics, retaining raw
capture files; metadata-only sources without text or HTML cannot be extracted.
