# Knowledge Bank

Search and ask questions about your own documents, privately and offline.

Knowledge Bank indexes the folders and files you choose, finds the passages that answer your question, and shows where each answer came from. Everything runs on your computer. Your documents are never uploaded.

The interface is available in Persian and English, with full right-to-left support for Persian text.

## Features

- **Many file types:** text, Markdown, HTML, Word, PowerPoint, Excel, OpenDocument, EPUB, RTF, CSV, JSON, YAML, and PDF (text-based PDFs; scanned PDFs need OCR first).
- **Word search** with ranking, including Persian word forms and close spellings.
- **Search by meaning** (optional): finds passages that express the same idea with different words.
- **Answers with citations:** each sentence of an answer links to the passage it came from, with a percentage showing how closely that passage supports it. Before an answer is shown, each sentence is checked against the passages: a sentence needs a supporting passage, and any number in it must appear in that passage. A sentence that no passage supports is shown without a citation, and the answer is marked as only partly checked. Unsupported text is never shown as if it were sourced.
- **Always answers when passages exist:** the answer model is asked for every question that has at least one passage. A coverage measure is logged for calibration, but it never blocks an answer.
- **Labelled general answers:** if an answer is written without your documents (free mode, or no passage matched), the window says so.
- **Language matching:** answers are written in the language of your question, and a warning appears if the model still answers in another language.
- **Saved chats:** every question and answer is kept, with the passages and citations it used. Only answers that passed the support check are sent back to the model as conversation history; earlier unchecked answers stay visible but are not reused. The **Chat history** section at the top of the sidebar groups them under Today, Yesterday, and Earlier. A search box filters them by title, and Enter opens the highlighted chat. Click a chat to open it, or use **New chat**. Hover over a chat to show its icons: rename (pencil), export to Markdown (download), and delete (trash).
- **Live folders:** changes to your files are picked up automatically.
- **Simple settings** for answer length, number of passages, meaning search, match percentages, AI answers, and resource use (Light, Balanced, Full).
- **Automatic setup:** the meaning-search engine and model, the Persian font, and the Python packages it needs are downloaded in the background when missing, with retries.

## How answers are produced

Knowledge Bank is a retrieval-augmented generation (RAG) system. Everything runs on your computer.

1. **Indexing.** Each file is split into passages. Every passage gets a full-text index (SQLite FTS5 with BM25 ranking) and an embedding from Multilingual E5 Small.
2. **Retrieval.** For each question, word search and meaning search run together. Meaning search keeps the passages within `MEANING_MARGIN` of the best score. The results are merged and limited to a character budget.
3. **Coverage check.** The app measures how much of the question's vocabulary, weighted by rarity, appears in the passages, and logs the figure for calibration. It does not stop the answer: the model is called whenever a passage exists.
4. **Generation.** Qwen3.5 2B receives the numbered excerpts with rules: answer only from them, cite each sentence, and say which part is not covered.
5. **Verification.** Each sentence is linked to a passage by meaning similarity, with a small bonus for shared words, so Persian and English sentences both link. A sentence with no supporting passage, or with a number its passage does not contain, is shown without a citation, and the answer is marked as only partly checked. The answer is not replaced, and the model is not called a second time for this.

Two modes are not RAG. With AI answers off, the window shows the passages only. In free mode, the model answers from its own knowledge, and the window labels that answer as not from your documents.

## Known limits

- **Speed.** Answers take from under a minute to several minutes on a CPU. Prompt processing is the main cost. Full uses the most processor time and is the fastest setting for answers.
- **Partial answers.** Sentences the passages do not support appear without a citation. A partly checked answer is not reused as chat history.
- **Calibration.** The meaning cutoff, the coverage threshold, and the support thresholds are not yet calibrated against a set of labelled questions.
- **Format.** The small answer model does not always follow its format rules, for example one sentence when nothing is found, or a citation to an unrelated passage. The verification step catches unsupported text, not every format violation.
- **Claims without numbers.** The verification step checks words and numbers. It does not check every claim, so a sentence can use wording that is supported in general but not by the cited passage.

## Requirements

- Python 3.10 or newer (the window's PySide6 needs it), with SQLite that includes FTS5 (standard Python builds include it).
- About 1 GB of free disk space for the meaning model and the engine, plus about 0.5 GB for the answer model if you use written answers.
- Roughly 2 GB of free memory while an answer is being written.
- Linux, Windows or macOS.

## Installation

Download or clone this repository and keep all the files in one folder:

```
git clone https://github.com/Shayan-Rahmati/knowledge-bank.git
cd knowledge-bank
```

On Ubuntu or Debian, you can install the window toolkit from the system packages:

```
sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtsvg
```

Otherwise the app installs PySide6 for you with pip, into your user folder, on first start.

## Running

```
python3 kb.py
```

The first start installs anything missing and opens the window. Add a folder with **Add folder**, or drag folders onto the window.

### Command line

```
python3 kb.py --add <folder>       index a folder and exit, without opening the window
python3 kb.py --install            install PySide6, numpy and pypdf
python3 kb.py --pip-index <url>    use a package mirror
python3 kb.py --wheels <folder>    install packages from downloaded wheel files
```

## Reading files

The source viewer shows a file as its own structure: headings, paragraphs, list items, tables and code blocks. Each block takes its direction from its own text, so a Persian paragraph is right-to-left and an English one is left-to-right, even inside the same document. Search matches are highlighted and the view opens at the first one.

The text is the file's own text. Characters are not rewritten; search normalises its own copy when it matches words. Files indexed before this change keep their old text until you remove and add them again.

## The window

The sidebar leads with your chats, followed by the **Library**: sources, meaning search, data files, and the developer card. Each file and source row has a trash icon at its end. Removing a file takes it out of the bank and leaves the file on disk; removing a source takes the whole source out, after you confirm. The conversation fills the rest of the window. An empty conversation offers starter questions, and clicking one puts it in the input.

Under each question: copy and edit. Editing a question keeps the earlier version and asks the new one, which starts a second branch. A `‹ 2 / 2 ›` switcher moves between the versions, and each version keeps its own answers. Under each answer: copy and regenerate. Regenerating writes the answer again from the same passages. The model samples its replies, so the wording changes each time; the sources do not.

Short messages appear at the bottom of the window after copying, renaming, deleting, exporting, or removing a source. They fade away on their own.

## Answer settings

Open **Answer settings** from the top bar. Changes apply to the next question.

| Setting | Choices | What it does |
|---|---|---|
| Length | Short, Medium, Detailed | How long written answers are |
| How many passages | Few, Standard, Many | How many passages a search returns |
| Search by meaning | On, Off | Use meaning search as well as words |
| Match percentage | On, Off | Show how closely each citation matches |
| AI answers | On, Off | Write an AI answer for every question |
| Speed and resources | Light, Balanced, Full | How much of the processor the work may use |

Light keeps the computer responsive while indexing, which takes longer. Answers still use two processor threads on every setting, at the lowest priority on Light. Full is fastest and uses most of the processor. Balanced is the default.

## Models and privacy

Knowledge Bank uses two small models, both run locally by the official [llama.cpp](https://github.com/ggml-org/llama.cpp) server:

- **Multilingual E5 Small** (about 126 MB), for search by meaning.
- **Qwen3.5 2B Q4_K_M** (about 1.28 GB), for written answers. It is downloaded only when you want written answers.

Models and the engine are downloaded once and stored in the `data` folder, so the app works offline afterwards. The only network use is for these downloads, the Python packages, and the Persian font. Your documents, questions and answers stay on your computer.

## Data and files

Everything the app keeps is in the `data` folder next to `kb.py`:

- `data/bank/` — the index database and the extracted text.
- `data/models/` — the models.
- `data/engine/` — the llama.cpp engine.
- `data/vendor/` — the Python packages downloaded by the app.
- `data/logs/` — the most recent answer, for troubleshooting.

Deleting `data` resets the app completely; your documents are never modified.

## Project files

| File | What it does |
|---|---|
| `kb.py` | Entry point. Run this. |
| `kb_config.py` | Paths, the model catalog and constants |
| `kb_text.py` | Persian text handling, tokens and language checks |
| `kb_extract.py` | Reading documents |
| `kb_store.py` | The database and the search index |
| `kb_net.py` | Downloads, proxies and the download manager |
| `kb_engine.py` | Runs the llama.cpp engine |
| `kb_core.py` | Application logic |
| `kb_chat.py` | Chat history, and the recent messages sent to the model |
| `kb_ui.py` | The window, the document list, the Downloads window and the settings panel |
| `kb_eval.py` | Optional: checks search accuracy against your own questions |
| `tests/` | Automated tests; run with `python3 tests/run_tests.py` |

## Calibrating meaning search

Relevance is decided in four places: the meaning cutoff below (for meaning search), the coverage check (logged only; it never blocks an answer), the support check (each sentence is linked to the passage it matches, and unlinked sentences are marked), and the number check (each number in an answer sentence must appear in its passage). The thresholds for the coverage and support checks are logged in `data/logs/kb.log` (`coverage`, `cite.link`, `grounding.partial`) so they can be set from your own questions.

Meaning search keeps the passages whose score is within `MEANING_MARGIN` (0.02, in `kb_config.py`) of the best score for the question. Scores of unrelated and related passages overlap, so no fixed cutoff separates them; the margin keeps only the close matches. Set `MEANING_MARGIN = 1.0` to turn the margin off. `MIN_MEANING_SIM` is an absolute floor, off at -1.0. Each question's best score is written to `data/logs/similarity.txt`. Check the margin with `kb_trace.py` on your own questions before relying on it.

## Checking search accuracy

Edit the question list at the top of `kb_eval.py` to match your own documents, then run:

```
python3 kb_eval.py <folder with your documents>
```

It reports whether each question is answered from the right file. It uses a temporary database, so your real data is not changed.

## Running the tests

```
python3 tests/run_tests.py
```

The tests run offline, with a temporary data folder and no background downloads.

To also run the real engine test, unpack the llama.cpp release (the same version the app downloads) and give its folder to the runner:

```
KB_ENGINE_SRC=/path/to/folder/with/llama-server python3 tests/run_tests.py
```

The font test checks that Vazirmatn reaches the headers when the font arrives after the window opens. Give it the font file:

```
KB_FONT_FILE=/path/to/Vazirmatn-Regular.ttf python3 tests/run_tests.py
```

That test starts `llama-server` with tiny random models, so it checks the plumbing (start, embeddings, chat, meaning index, shutdown), not answer quality. The full end-to-end test drives the real window through the same engine: indexing, search, asking, editing, switching versions, regenerating with AI answers on and off, and reopening after a restart. They cover a static check of the code (undefined names, duplicate definitions), the prompt budget, chat storage, indexing and answers (with the model stubbed), and the window (headless).

## Troubleshooting

- **The window does not open:** check the terminal. A missing PySide6 is installed on first start, or use the apt command above.
- **Downloads fail:** open **Downloads & models**, check the reason shown, and use a proxy if your network needs one. The app uses your system proxy automatically.
- **Answers are slow:** choose Short or Medium length in Answer settings, since a long answer is most of the wait; then Full, which gives answers the most processor time. A smaller number of passages also helps.
- **Sharing a log for a bug report:** start the app with `KB_REDACT=1 python3 kb.py` to hide question and answer text in `data/logs/kb.log`, or remove those lines by hand before sending.
- **Answers come in the wrong language, or a warning appears:** the model did not follow the instruction. Try a different length setting or ask again.
- **The engine says it did not start:** update the engine from **Downloads & models**.

## Status

This is an early release. The core features are tested with automated checks, but the window, the models and downloads are still being checked on different systems. Bug reports with your system details and the terminal output are very welcome.

## Developer

Created by [Shayan Rahmati](https://github.com/Shayan-Rahmati) ([LinkedIn](http://www.linkedin.com/in/shayan-rahmati)). Also see [Primee](https://primee.ir).

## License

To be decided by the author.
