from binascii import hexlify
from logging import warning, info, error
import logging

from socket import inet_ntoa, inet_aton, gethostname
import asyncio
import struct


class Socks:
    def __init__(self, host, port, log=False):
        self._host, self._port = host, port
        self._log = log

        if log: logging.basicConfig(level=logging.INFO)
        else: logging.basicConfig(level=logging.CRITICAL)

    def start(self):
        info(f'starting socks4 server at {self._host}:{self._port}')
        asyncio.run(self._start(self._host, self._port))

    async def _start(self, host, port):
        '''@brief server main coroutine.
        '''
        
        server = await asyncio.start_server(
            self._serve, host, port)

        async with server:
            await server.serve_forever()

    async def _serve(self, reader, writer):
        '''@brief serve a new client

        @details recognize request method and call appropriate
        coroutine to handle client. methods:
            - CONNECT: 1
            - BIND: 2

        @param reader readable client transport
        @param writer writable client transport
        '''

        _bufsize = 1 << 12
        req = await reader.read(_bufsize)

        # for now do not handle ident
        if len(req) < 8:
            error(f'request badly formed: {hexlify(req)}')
            return

        vn, cd, port, ip = struct.unpack('!BBHI', req[:8])
        addr = inet_ntoa(struct.pack('!I', ip))

        if cd == 1:    # CONNECT method
            await self._connect(reader, writer, addr, port)
        elif cd == 2:  # BIND method
            await self._bind(reader, writer, addr, port)
        else:
            error(f'incorrect SOCKS4 method: {cd}')

    async def _connect(self, reader, writer, addr, port):
        '''@brief handle CONNECT request by client

        @details attempt to open connection to requested server.
        if this attempt fails, report it to client and close
        connection with client. if this attempt succeeds, set up
        a relay between the client and the server with `Socks._relay`.

        @param reader readable client transport
        @param writer writable client transport
        @param addr address of requested server
        @param port port of requested server
        '''

        try:
            sreader, swriter = await asyncio.open_connection(addr, port)
        except:
            error(f'failed to connect to {addr}:{port}')
            writer.write(b'\x00\x5B\xFF\xFF\xFF\xFF\xFF\xFF')
            await writer.drain()
            writer.close()
            return

        # reply success
        info(f'setting up relays for {addr}:{port}')
        writer.write(b'\x00\x5A\xFF\xFF\xFF\xFF\xFF\xFF')
        await writer.drain()
        
        # set up relays
        asyncio.create_task(self._relay(reader, swriter))
        asyncio.create_task(self._relay(sreader, writer))

    async def _bind(self, reader, writer, addr, port):
        '''@brief handle BIND request by client

        @details attempt to bind with os assigned port. if this
        attempt fails, report failure to client and close
        connection with client. if this attempt succeeds, send
        our hostname and os assigned port to client, and wait
        for the server with address `addr` to connect.

        @param reader readable client transport
        @param writer writable client transport
        @param addr expected server addr
        @param port expected server port
        '''

        try:  # try to bind
            server = await asyncio.start_server(
                self._bound(reader, writer, addr, port),
                gethostname(), 0)  # os assigned port
        except:
            writer.write(b'\x00\x5B\xFF\xFF\xFF\xFF\xFF\xFF')
            await writer.drain()
            error(f'could not bind to wait for {addr}:{port}')
            return

        # reply to client
        saddr, sport = server.get_extra_info('sockname')
        writer.write(b'\x00\x5A' + \
            sport.to_bytes(2, 'big') + \
            inet_aton(saddr).to_bytes(4, 'big'))
        await writer.drain()

        # start waiting for server's connection
        async with server:
            await server.serve_forever()

    def _bound(self, reader, writer, addr, port):
        '''@brief wait for server to connect

        @details expect server with address `addr` to connect.
        when it does, check the address and set up a relay
        between the server and the client.

        @param reader readable client transport
        @param writer writable client transport
        @param addr expected server address
        @param port expect server port
        '''

        async def handler(sreader, swriter):
            raddr, _ = sreader.get_extra_info('peername')
            if raddr != addr:  # make sure this is the right server
                error(f'wrong server connecting to BIND: {raddr}')
                return

            # set up relays
            asyncio.create_task(self._relay(reader, swriter))
            asyncio.create_task(self._relay(sreader, writer))

    async def _relay(self, reader, writer):
        '''@brief forward all bytes read from reader to writer
        '''

        fm = await reader.read(1 << 12)
        while fm:
            try:
                writer.write(fm)
                await writer.drain()
            except:
                break
            fm = await reader.read(1 << 12)
        writer.close()


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

