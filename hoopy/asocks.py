# logging
from binascii import hexlify
from logging import warning, info, error
import logging

# implementation
from socket import inet_ntoa, gethostname
import asyncio
import struct


class Socks:
    def __init__(self, host, port, log=False):
        self._host, self._port = host, port
        self._log = log

        if log:
            logging.basicConfig(level=logging.INFO)
        else:
            logging.basicConfig(level=logging.CRITICAL)

    def start(self):
        info(f'starting socks4 server at {self._host}:{self._port}')
        asyncio.run(self._start(self._host, self._port))

    async def _start(self, host, port):
        server = await asyncio.start_server(
            self._serve, host, port)

        async with server:
            await server.serve_forever()

    async def _serve(self, reader, writer):
        req = await reader.read(9)

        # for now do not handle ident
        if len(req) < 8:
            return

        vn, cd, port, ip = struct.unpack('!BBHI', req[:8])
        addr = inet_ntoa(struct.pack('!I', ip))

        try:
            sreader, swriter = await asyncio.open_connection(addr, port)
        except:
            error(f'failed to connect to {addr}:{port}')
            writer.write(b'\x00\x5B\xFF\xFF\xFF\xFF\xFF\xFF')
            await writer.drain()
            writer.close()
            return

        info(f'setting up relays for {addr}:{port}')
        writer.write(b'\x00\x5A\xFF\xFF\xFF\xFF\xFF\xFF')
        await writer.drain()
        
        asyncio.create_task(self._relay(reader, swriter))
        asyncio.create_task(self._relay(sreader, writer))

    async def _relay(self, reader, writer):
        fm = await reader.read(1 << 12)
        while fm:
            try:
                writer.write(fm)
                await writer.drain()
            except:
                break
            fm = await reader.read(1 << 12)


def run():
    import argparse

    parser = argparse.ArgumentParser('socks4 proxy server')
    parser.add_argument('-i', '--ip', default=gethostname(),
        help='serve on which host')
    parser.add_argument('-p', '--port', default=8080,
        help='serve on which port')
    parser.add_argument('-l', '--log', action='store_const', const=True, default=False)
    args = parser.parse_args()

    Socks(args.ip, args.port, args.log).start()

