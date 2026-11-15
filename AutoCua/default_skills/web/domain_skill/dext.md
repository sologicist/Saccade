# Dext operations

For an explicitly requested invoice analysis, execute this sequence:
download once -> wait for trusted confirmation -> call Scribe -> show its result -> stop.
Read the current trusted download status in call_function's description and tool
results. If pending, use wait and observe again, without another download click.
When complete, pass the exact reported filename to call_function, version 1,
name dext.scribe, arguments pdf, the active registered client_id, sens achat/vente
(string is null). The host resolves the absolute path. Invoke this native tool;
do not search GitHub, other chats, chrome://downloads or the console for Scribe.
For unconfirmed or failed downloads, report the exact state and stop that attempt.
Saving/printing dialogs, filenames and chat claims cannot prove a completed PDF.

Use the existing Web screenshot, DOM and native navigation tools. Identify the
current client explicitly from operator registration and the observed UI; the
hostname identifies Dext, never the accounting client. Do not silently switch
client references when the screen and active registration disagree.

Navigate purchases, sales or banking using the controls actually observed.
Open the requested document and inspect its identity. Distinguish invoices,
credit notes and quotations; do not infer accounting amounts from filenames.
If controls are missing or changed, observe again and report the uncertainty.
Do not invent selectors, coordinates, private endpoints or workflow steps.

Download documents with the normal browser interaction. Use only the exact
filename reported by the browser/tool result as a local lookup key, including
Chrome's collision suffix. A chat statement or successful click is not proof of
a downloaded file. The host must resolve a fresh, completed PDF in the configured
Downloads folder. Missing, stale, ambiguous or partial files must stop analysis.

Use call_function with dext.scribe(pdf, client_id, sens): pdf is the actual local
absolute PDF path resolved by the trusted application; an exact reported filename
may be submitted for host resolution. sens is achat for purchases or vente for
sales. The function reads the entire matching client reference and the PDF.
Gemini analysis is a separate external transfer of that PDF and reference;
an explicit user request to analyze this document authorizes that analysis. Never invent a path or result.

Use dext.bank(string, client_id) for an observed banking label and the active
client's bank reference. Null or uncertain results require review. Check every
function response and show the validated proposal to the operator. Never submit,
save or post accounting entries automatically. Private rules belong only in the
client reference files, never in this skill or logs.
