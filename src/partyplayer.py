#!/usr/bin/env python3

import http.client
import http.server
import os
import random
import select
import signal
import urllib.parse
import socketserver

PORT = 8000
LCD_PORT = 8001
MUSIC_ROOT = "/nfs/geluid/mp3"

def set_lcd(lines):
    d = {}
    for n, l in enumerate(lines):
        d['line' + str(n + 1)] = l

    params = urllib.parse.urlencode(d)
    conn = http.client.HTTPConnection('localhost', LCD_PORT)
    conn.request("GET", '/?' + params)
    conn.getresponse() # flush response

def update_lcd_for_file(next_file):
    if not LCD_PORT:
        return

    try:
        lines = [ ]
        for l in next_file.split('/'):
            if not l:
                continue
            if l.startswith('['): # remove '[....] ' prefix
                n = l.find(']')
                if n > 0:
                    l = l[n + 1:]
            elif l[0].isdigit(): # remove 'nn - ' prefix
                n = l.find(' - ')
                if n > 0:
                    l = l[n + 3:]

                n = l.rfind('.mp3') # strip extension
                if n > 0:
                    l = l[:n]
            lines.append(l.strip())
        set_lcd(lines)
    except:
        pass

class Playlist:
        _current_file = None

        def __init__(self, playlist_fname, state_fname):
                # read the playlist files
                self._files = [ ]
                with open(playlist_fname, 'rt') as f:
                        for s in f:
                                s = s.strip()
                                self._files.append(s)

                # read the state
                self._state = {}
                self._state_fname = state_fname
                try:
                        with open(self._state_fname, 'rt') as f:
                                for s in f:
                                        s = s.strip().split()
                                        self._state[s[0]] = int(s[1])
                except FileNotFoundError:
                        self._state = {
                                'seed': random.randrange(0, 9223372036854775807),
                                'count': 0,
                        }

                # XXX we actually want a local random seed
                random.seed(self._state['seed'])

                # shuffle the files and throw away the amount that we already played
                self._files = random.sample(self._files, len(self._files))
                self._files = self._files[self._state['count']:]

        def write_state(self):
                with open(self._state_fname, 'wt') as f:
                        for k, v in self._state.items():
                                f.write('%s %s\n' % (k, v))

        def advance(self):
                self._state['count'] += 1
                self.write_state()

                self._current_file = self._files[0]
                self._files = self._files[1:]
                return self._current_file

        def get_current(self):
                return self._current_file

class Player:
        _pid = None

        def __init__(self, playlist):
                self._playlist = playlist

        def play(self):
                next_file = self._playlist.advance()

                print('playing "%s"' % next_file)
                update_lcd_for_file(next_file)
                newpid = os.fork()
                if newpid == 0:
                        #os.execvp("/usr/bin/mplayer", [ "mplayer", "-quiet", "-nolirc", "-really-quiet", os.path.join(MUSIC_ROOT, next_file) ])
                        os.execvp("/usr/bin/mpg321", [ "mpg321", "-quiet", os.path.join(MUSIC_ROOT, next_file) ])
                        #os.execvp("/bin/sleep", [ "sleep", "10" ])
                self._pid = newpid

        def stop(self):
                os.kill(self._pid, signal.SIGTERM)

class httpHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
                global playlist, player, need_next

                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()

                reply = "Request not understood"
                if self.path == "/":
                        reply = 'Playing <b>%s</b><br/>' % playlist.get_current()
                        reply += '<a href="/next">skip</a>'
                elif self.path == "/next":
                        need_next = True
                        # force a redirect
                        reply = '<meta http-equiv="refresh" content="0; url=/" />'

                self.wfile.write(reply.encode('utf-8'))

        # ping is used to drop out of the select(2) loop; for whatever reason,
        # python keeps restarting calls after a signal
        def do_PING(self):
                self.send_response(200)
                self.end_headers()

def on_sigchld(signum, frame):
        global got_sigchld, clien
        got_sigchld = True
        client.request("PING", "/") # force out of the loop

# load files, redistribute them and start at count
playlist = Playlist('files.txt', 'state.txt')
player = Player(playlist)

# handle HTTP side of things
got_sigchld = False
need_next = False

signal.signal(signal.SIGCHLD, on_sigchld)
httpd = socketserver.TCPServer(("", PORT), httpHandler)
client = http.client.HTTPConnection("localhost:%d" % PORT)
player.play()
while True:
        if need_next:
                player.stop() # sigchld should pick this up further
                need_next = False

        if got_sigchld:
                # wait for zombie to die
                os.waitpid(0, os.WNOHANG)
                # advance to next track
                client.getresponse() # to flush the response
                player.play()
                got_sigchld = False
        httpd.handle_request()

httpd.server_close()
