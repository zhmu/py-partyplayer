#!/usr/bin/env python3

import gpiozero
import http.server
import socketserver
import time
import urllib.parse

PORT = 8001

class LCD:
    _si = gpiozero.OutputDevice(2)
    _rck = gpiozero.OutputDevice(3)
    _sck = gpiozero.OutputDevice(4)

    _E = (1 << 0)
    _RS = (1 << 1)
    _SHIFT_DELAY = 0 #1e-3
    _E_DELAY = 0.010 # 100ms

    def __init__(self):
        # ensure shift register is empty
        self._shiftin_byte(0)

        self._si.off()
        self._rck.off()
        self._sck.off()

        self._init_4()
        self._send_byte(0x28, 0) # function set, DL=0, N=1, F=0
        #self._send_byte(0x08, 0) # display control, D=0, C=0, B=0
        self._send_byte(0x1, 0) # clear display
        #self._send_byte(0x7, 0) # entry mode set: I/D=1, S=1
        #self._send_byte(0x80, 0) # cursor to start of first line

        #self._send_byte(0x0f, 0) # display control, D=1, C=1, B=1
        self._send_byte(0x0c, 0) # display control, D=1, C=0, B=0

    def _shiftin_byte(self, b):
            for v in range(0, 8):
                    if b & (1 << (7 - v)):
                            self._si.on()
                    else:
                            self._si.off()
                    self._sck.on()
                    self._sck.off()
            self._rck.on()
            self._rck.off()

    # sends bits 4..7 of byte 'b' to the HD44780
    # along with rs bit (do not set E)
    def _send_nibble(self, b, rs):
            if b & self._E:
                    raise Exception("E set")
            self._shiftin_byte(b)
            self._shiftin_byte(b | self._E | rs)
            time.sleep(self._E_DELAY) # wait for command to complete
            self._shiftin_byte(b | rs)
            time.sleep(self._E_DELAY) # wait for command to complete

    # sends a whole byte to the HD44780
    def _send_byte(self, b, rs):
            # high nibble
            data = (b & 0xf0)
            self._send_nibble(data, rs)
            # low nibble
            data = (b & 0x0f) << 4
            self._send_nibble(data, rs)

    def _init_4(self):
            self._send_nibble(0x30, 0)   # 0011
            time.sleep(0.02)    # 20ms
            self._send_nibble(0x30, 0)   # 0011
            time.sleep(0.01)    # 10ms
            self._send_nibble(0x30, 0)   # 0011
            time.sleep(0.001)   # 1ms

            self._send_nibble(0x28, 0)   # 0010 - sets to 4 bit mode

    def set(self, lines):
        line_addrs = [ 0x80, 0xc0, 0x90, 0xd0 ]
        self._send_byte(0x1, 0) # clear display
        for n, line in enumerate(lines):
            self._send_byte(line_addrs[n], 0)
            for s in line[0:16]: # clip
                self._send_byte(ord(s), self._RS)

class httpHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            global lcd
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()

            qc = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            lines = [ qc[k][0] for k in sorted(qc.keys()) ]
            lcd.set(lines)

            self.wfile.write(b'ok')

lcd = LCD()
lcd.set([ '0123456789abcdefABCDEFGHIJKL', 'world', 'some', 'test' ])

print('LCD daemon ready')
httpd = socketserver.TCPServer(("", PORT), httpHandler)
httpd.serve_forever()
