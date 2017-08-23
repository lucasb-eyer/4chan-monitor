from os.path import join as pjoin
from collections import OrderedDict
from time import time
from logging import warning

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import requests
import socket  # Just for the `timeout` exception :(
from bs4 import BeautifulSoup


def safeget_json(url):
    """
    Get a json while nicely handling (warning about) any types of weird
    behaviors that can come from the server in real-life.

    Returns `None` for "nothing here, but try again later", `404` for a
    thread that 404ed and any other json object if the response is good.
    """
    try:
        r = requests.get(url, timeout=(3.5, 5))
    except (requests.Timeout, socket.timeout, TimeoutError) as e:
        warning("timeout for {url} (exception type: {et})".format(url=url, et=str(type(e))))
        return
    except ConnectionError:
        warning("other connection error for {url}".format(url=url))
        return

    if r.status_code == 404:
        return 404
    elif r.status_code != 200:
        warning("return code {code} for {url}".format(code=r.status_code, url=url))
        return

    try:
        json = r.json()
        if json is None:
            raise ValueError()
    except ValueError:
        warning("got invalid JSON for {url}".format(url=url))
        return

    return json


def threads(board='b', pages=[1]):
    """
    - `board`: The name of the board, without the slashes. E.g. 'b'
    - `pages`: A list or set of page-numbers indicating which pages to include. `None` for all.
    """
    url = "http://a.4cdn.org/{board}/threads.json".format(board=board)
    json = safeget_json(url)
    return {
        thread['no']: Thread(board, thread['no'])
        for page in json if pages is None or page['page'] in pages
        for thread in page['threads']
    } if json is not None and json != 404 else {}


class Thread:
    def __init__(self, board, no):
        self.no = no
        self.board = board
        self.url = "http://a.4cdn.org/{board}/thread/{no}.json".format(board=board, no=no)
        self.done = False
        self.posts = OrderedDict()

        # For being gentle.
        self.lastupd8 = 0
        self.backoff = 1

    def update(self):
        # Only check at most once per second.
        if self.done or time() - self.lastupd8 < self.backoff:
            return
        self.lastupd8 = time()

        json = safeget_json(self.url)
        if json is None:
            return
        elif json == 404:
            self._close()
            return

        posts = json['posts']

        # If there are no new posts, wait twice longer next time.
        self.backoff = 1 if len(posts) > len(self.posts) else 1.5*self.backoff

        # Add any new posts
        for p in posts:
            # I've once had a post without number in /mu/.
            # Not sure what that was, but let's agree to just skip.
            if 'no' in p and p['no'] not in self.posts:
                self.posts[p['no']] = Post(self.board, self.no, p)

        # It sometimes happens that the first post is only half-complete, probably race-condition.
        # It's missing most basic stuff like. In that case, we just skip it and
        # it will be updated later on. Note it's also been skipped above.
        if 'no' not in posts[0]:
            warning("Skipping half-complete OP at {}".format(self.url))
            return

        # Update the OP's meta-info.
        op = posts[0]
        self.posts[op['no']].update(op)

        # Archiving boards don't delete a thread, but close it. This is marked in the OP.
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

        self.board = board
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
        # This one disappears once a thread gets archived.
        # It also may shrink sometimes (albeit rarely and usually just by one),
        # so we'll just track the peak!
        self.unique_ips = max(getattr(self, 'unique_ips', 0), pi.get('unique_ips', 0))

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
            elif 'catalog#s=' in href:
                pass  # That's mostly caused by idiots writing /r/eddit or /t/umblr.
            elif href == '/mu/catalog':
                pass  # In /mu/'s sticky.
            else:
                warning("Can't handle quote: {} encountered in thread {} post {}".format(href, self.threadno, self.no))
            return None
