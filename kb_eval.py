"""Checks search accuracy against questions you write yourself.

Edit QUESTIONS below. Each entry is (question, the file that should answer it, text that must appear in that file's best passage). Then run:

    python3 kb_eval.py <folder with your documents>

It indexes the folder in a temporary bank, asks every question, and reports whether the right file is among the top results."""
import os, sys, tempfile, time, shutil

QUESTIONS = [
    ("When was Python released?", "a.txt", "1991"),
    ("What is photosynthesis?", "x.docx", "Photosynthesis"),
    ("Which river is the largest by discharge?", "b.epub", "Amazon"),
    ("What happened to the revenue in the third quarter?", "s.pptx", "revenue"),
]
# Questions the bank must not answer. Any passage returned is a false match.
NEGATIVE = [
    "What is the boiling point of mercury on Mars?",
]
TOP_K = 3


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    folder = os.path.abspath(sys.argv[1])
    tmp = tempfile.mkdtemp(prefix="kb_eval_")
    os.environ["KB_DATA"] = tmp        # set before the app loads, so the real bank is left alone
    app = None
    try:
        import kb_core
        app = kb_core.App()
        app.add_source(folder)
        app.sync(force=True)
        while not app.booted:
            time.sleep(0.05)
        passed = 0
        for question, expected_file, expected_text in QUESTIONS:
            result = app.ask(question)
            top_files = [h["name"] for h in result["hits"][:TOP_K]]
            found_file = expected_file in top_files
            found_text = any(expected_text.lower() in h["text"].lower() for h in result["hits"][:TOP_K]
                             if h["name"] == expected_file)
            ok = found_file and found_text
            passed += ok
            print("%s  %s" % ("PASS" if ok else "FAIL", question))
            if not ok:
                print("      expected %s in the top %d, got: %s" % (expected_file, TOP_K, ", ".join(top_files) or "nothing"))
        false_matches = 0
        from kb_config import MIN_MEANING_SIM
        no_floor = MIN_MEANING_SIM <= -1.0
        for question in NEGATIVE:
            if no_floor:
                # With no absolute floor, meaning search always returns its best passage, so "found nothing"
                # cannot happen. Reporting FAIL here would be misleading; the test needs a floor first.
                print("SKIP  %s (MIN_MEANING_SIM is off; set an absolute floor in kb_config.py to test this)" % question)
                continue
            hits = app.ask(question)["hits"]
            ok = not hits
            false_matches += not ok
            print("%s  %s (should find nothing)" % ("PASS" if ok else "FAIL", question))
            if not ok:
                print("      false match: %s" % ", ".join(h["name"] for h in hits[:TOP_K]))
        print("\n%d / %d questions answered from the right file" % (passed, len(QUESTIONS)))
        if no_floor:
            print("no-match questions: skipped (no absolute floor set)")
        else:
            print("%d / %d no-match questions correctly found nothing" % (len(NEGATIVE) - false_matches, len(NEGATIVE)))
        return 0
    finally:
        # runs even when a question raises, so the engine and database are released before the folder is removed
        if app is not None:
            app.engine.stop()
            app.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
