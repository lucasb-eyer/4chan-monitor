from os.path import join as pjoin
from collections import OrderedDict
from time import time

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import requests
from bs4 import BeautifulSoup


def threads(board='b', pages=[1]):
    """
    - `board`: The name of the board, without the slashes. E.g. 'b'
    - `pages`: A list or set of page-numbers indicating which pages to include. `None` for all.
    """
    r = requests.get("http://a.4cdn.org/{board}/threads.json".format(board=board))
    return {
        thread['no']: Thread(board, thread['no'])
        for page in r.json() if pages is None or page['page'] in pages
        for thread in page['threads']
    }


class Thread:
    def __init__(self, board, no):
        self.no = no
        self.board = board
        self.url = "http://a.4cdn.org/{board}/thread/{no}.json".format(board=board, no=no)
        self.done = False
        self.posts = OrderedDict()
        self.lastupd8 = 0

    def update(self):
        # Only check at most once per second.
        if self.done or time() - self.lastupd8 < 1000:
            return
        self.lastupd8 = time()

        r = requests.get(self.url)
        if r.status_code == 404:
            self._close()
            return
        elif r.status_code != 200:
            print("Warning: return code {code} for {url}".format(r.status_code, self.url))
            return

        # Add any new posts
        posts = r.json()['posts']
        for p in posts:
            if p['no'] not in self.posts:
                self.posts[p['no']] = Post(self.board, self.no, p)

        # Update the OP's meta-info.
        op = posts[0]
        self.posts[op['no']].update(op)

        # Archiving boards don't delete a thread, but close is. This is marked in the OP.
        if self.posts[op['no']].closed:
            self._close()

    def _close(self):
        self.done = True

    def json(self):
        return {'no': self.no, 'posts': list(self.posts)}


class Post:
    def __init__(self, board, threadno, pi):
        """
        - `pi` stands for "postinfo" which is what you get from a thread's json.
        """
        # Normalize!
        pi.setdefault('com', '')

        self.threadno = threadno
        self.info = pi
        self.closed = False

        # Get all things into attributes for easier access.
        for k,v in pi.items():
            setattr(self, k, v)

        # And make a few even more accessible:
        # (StringIO because otherwise bs4 may warn about "looks like URL")
        self.com = BeautifulSoup(StringIO(self.com), "html.parser")
        self.text = '\n'.join(self.com.strings)

        # Note: not using 'resto' here since that's always only one!
        self.quotes = [self.quotelink(a['href']) for a in self.com.findAll('a', class_='quotelink')]
        self.quotes = list(filter(None, self.quotes))

    def update(self, pi):
        """
        Only useful for OP: update meta-info such as #uniques.
        """
        self.images = pi['images']
        self.replies = pi['replies']
        self.unique_ips = pi['unique_ips']

        if pi.get('closed', 0) == 1:
            self.closed = True

    def json(self):
        return {
            'no': self.no,
            'closed': self.closed,
            'text': self.text,
            'quotes': self.quotes,
            'info': self.info,
        }

    def quotelink(self, href):
        try:
            return int(href.split('#')[-1][1:])
        except ValueError:
            if href[0] == href[-1] == '/':
                pass  # Ignore link to other board. There's no other indicator.
            # elif 'catalog#s=' in href:
                # pass  # Also ignore links to searches in the board.
            else:
                print("Can't handle quote:", href, "encountered in", self.threadno)
            return None
