try:
    import cPickle as pickle
except ImportError:
    import pickle

import os
import sys
import time
import json

# For some reason I have yet to understand (but is probably obvious),
# updates don't work across processes, but do across threads.
# from multiprocessing import Pool
from multiprocessing.pool import ThreadPool as Pool

import chan4


board = 'b'
basedir = '/work/lucas/data/4chin'

def update(t):
    t.update()


if __name__ == '__main__':
    threads = {}
    done = set()
    pool = Pool(4)

    tdir = "{}/{}/threads".format(basedir, board)
    pdir = "{}/{}/posts".format(basedir, board)

    os.makedirs(tdir, exist_ok=True)
    os.makedirs(pdir, exist_ok=True)

    tstart = time.time()

    while True:
        t0 = time.time()
        threads.update(chan4.threads(board, pages=[1]))

        pool.map(update, threads.values())

        donenow = set()
        for t in threads.values():
            # Save the thread once it's done.
            if t.done:
                with open('{}/{}.json'.format(tdir, t.no), 'w+') as f:
                    json.dump(t.json(), f)
                for p in t.posts.values():
                    with open('{}/{}.json'.format(pdir, p.no), 'w+') as f:
                        json.dump(p.json(), f)
                donenow.add(t.no)

        for t in donenow:
            del threads[t]
            done.add(t)

        t = time.time() - t0
        sys.stdout.write("\rMonitoring {} threads in {:.1f}s/cycle ({:.2f}s/thread). Completed {} threads in {:.0f}s.".format(len(threads), t, t/len(threads), len(done), time.time() - tstart))
        sys.stdout.flush()

        if t < 1:
            time.sleep(1-t)
