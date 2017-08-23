try:
    import cPickle as pickle
except ImportError:
    import pickle

import os
import sys
import time
import json
import logging
from getopt import getopt
from itertools import count

# For some reason I have yet to understand (but is probably obvious),
# updates don't work across processes, but do across threads.
# from multiprocessing import Pool
from multiprocessing.pool import ThreadPool as Pool

import chan4


def update(t):
    try:
        t.update()
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        # Log any other exceptions, but continue business.
        logging.exception("Problem updating thread at {}".format(t.url))

    return t.no if t.done else None

if __name__ == '__main__':
    # Parse cmdline arguments
    optlist, boards = getopt(sys.argv[1:], 'ho:j:p:')
    opts = dict(optlist)

    if '-h' in opts or len(boards) == 0:
        print("Usage: {} [-o OUTDIR] [-j NJOBS] [-p NPAGES] board1 board2 ...".format(os.path.basename(sys.argv[0])))
        sys.exit(0)

    # Dictionary mapping boards to dictionaries mapping tids to threads.
    # Gotta love that variable name ;)
    everything = {b: {} for b in boards}
    ntdone, npdone = 0, 0

    pool = Pool(opts.get('-j'))

    # Create any necessary directories and define utilities for later.
    basedir = opts.get('-o', os.getcwd())
    tdir = lambda board: os.path.join(basedir, board, "threads")
    pdir = lambda board: os.path.join(basedir, board, "posts")
    for board in boards:
        os.makedirs(tdir(board), exist_ok=True)
        os.makedirs(pdir(board), exist_ok=True)

    npages = int(opts.get('-p', 1))

    tstart = time.time()

    for e in count():
        t0 = time.time()

        for board, threads in everything.items():
            # Get new threadlist for this board.
            front_threads = chan4.threads(board, pages=range(1,npages+1) if e > 0 else None)

            # Keep track of new threads.
            for tno in front_threads.keys() - threads.keys():
                threads[tno] = front_threads[tno]

            # Update all known threads in this board.
            # NOTE: They have some backoff pausing implemented.
            done = pool.map(update, threads.values())
            done = [threads[tno] for tno in done if tno is not None]

            # Save and remove the threads that 404ed.
            for t in done:
                with open('{}/{}.json'.format(tdir(board), t.no), 'w+') as f:
                    json.dump(t.json(), f)
                for p in t.posts.values():
                    with open('{}/{}.json'.format(pdir(board), p.no), 'w+') as f:
                        json.dump(p.json(), f)
            ntdone += len(done)
            for t in done:
                del threads[t.no]
                npdone += len(t.posts)

        # Status report
        t = time.time() - t0
        nthreads = sum(map(len, everything.values()))
        sys.stdout.write("\rMonitoring {nthread} threads ({npost} posts) from {nboard} boards in {ct:.1f}s/cycle ({tt:.3f}s/thread). Completed {ntdone} threads ({npdone} posts) in {t:.0f}s ({e}ep).".format(
            nboard=len(everything),
            nthread=nthreads,
            npost=sum(len(t.posts) for ts in everything.values() for t in ts.values()),
            ntdone=ntdone, npdone=npdone,
            ct=t, tt=t/nthreads, t=time.time() - tstart, e=e)
        )
        sys.stdout.flush()

        if t < 1:
            time.sleep(1-t)
