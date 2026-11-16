"""Shows, step by step, what the search does for each question.

    python3 kb_trace.py "your question" "another question"

Uses your real data folder (data/). Prints, for each question: the words it searched, how many passages
matched the words, the best meaning scores with the same cutoff the app uses (kept or not), the files
returned, and the answer's first sentence if an answer model is running. Nothing is changed in your bank."""
import sys
from kb_core import App
from kb_config import MIN_MEANING_SIM, MEANING_MARGIN
from kb_text import query_terms


def main():
    qs = sys.argv[1:]
    if not qs:
        print(__doc__)
        return 1
    app = App()
    import time
    t0 = time.time()
    while not app.booted and time.time() - t0 < 120:
        time.sleep(0.2)
    print("bank: %d passages, %d with meaning vectors, meaning floor %.2f, margin %.2f" % (
        app.ix.N, int(app.ix.have.sum()) if app.ix.have is not None else 0, MIN_MEANING_SIM, MEANING_MARGIN))
    for q in qs:
        print("\n=== " + q)
        terms = app.ix.content_terms(query_terms(q))
        print("words searched: %s" % terms)
        groups = app.ix.expand(terms)
        bm = app.ix.bm25(terms, 200, groups=groups)
        print("passages matching any word: %d" % len(bm))
        r = app.retrieve(q, app.result_count())
        print("result mode: %s  note: %s" % (r["mode"], r["note"] or "-"))
        for i in r["ids"]:
            path, idx, text = r["info"][i]
            print("  -> %s (passage %d): %s" % (path.split("/")[-1], idx, text[:120].replace("\n", " ")))
        if not r["ids"]:
            print("  -> nothing returned")
        if r["qv"] is not None and app.ix.mat is not None:
            import numpy as np
            sims = np.where(app.ix.have, app.ix.mat @ r["qv"], -1.0)
            # same rule as Index.vector_hits: keep scores within the margin of the best, and never below the floor
            floor = max(MIN_MEANING_SIM, float(sims.max()) - MEANING_MARGIN)
            for j in np.argsort(-sims)[:5]:
                kept = bool(sims[j] >= floor and sims[j] > -0.9999)
                print("     meaning %.3f %s %s" % (sims[j], "KEPT" if kept else "dropped",
                                                   app.ix.paths[int(j)].split("/")[-1]))
    app.engine.stop()
    app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
