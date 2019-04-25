#!/usr/bin/env python3.7
import asyncio
import argparse
import datetime

colors = {
    'client': '\x1B[1;32m',
    'server': '\x1B[1;36m',
    'reset':  '\x1B[0m',
}

def print_packet(args, sender, data):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if args.color:
        print(colors[sender], end='')
    print('%s: %5d bytes from %-6s' % (timestamp, len(data), sender.upper()))
    if args.color:
        print(colors['reset'], end='')

    if args.hexdump:
        width = 16  # bytes
        for i in range(0, len(data), width):
            print('    ', ' '.join('{:02X}'.format(x) for x in data[i:i+width]))

class SharedData(object):
    def __init__(self, args):
        self.args = args

        # These should be futures, but it's tricky because you can't
        # 'await' inside the protocol callbacks. Doing it this way
        # risks a race condition, I think.
        self.ctos = None
        self.stoc = None

        loop = asyncio.get_running_loop()
        self.on_con_lost = loop.create_future()

class ClientToServer(object):
    def __init__(self, shared):
        self.shared = shared
        shared.ctos = self

    def connection_made(self, transport):
        print('Listening for client on %s port %d' %
            (self.shared.args.listen_host, self.shared.args.listen_port))
        self.transport = transport

    def datagram_received(self, data, addr):
        self.client_addr = addr
        print_packet(self.shared.args, 'client', data)
        self.shared.stoc.transport.sendto(data,
            (self.shared.args.connect_host, self.shared.args.connect_port))

    def connection_lost(self, exc):
        self.shared.on_con_lost.set_result(True)

class ServerToClient(object):
    def __init__(self, shared):
        self.shared = shared
        shared.stoc = self

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        print_packet(self.shared.args, 'server', data)
        ctos = self.shared.ctos
        ctos.transport.sendto(data, ctos.client_addr)

    def connection_lost(self, exc):
        self.shared.on_con_lost.set_result(True)

async def main():
    shared = SharedData(make_arg_parser().parse_args())

    loop = asyncio.get_running_loop()
    ctos_future, stoc_future, on_con_lost = (loop.create_future() for _ in range(3))

    await loop.create_datagram_endpoint(
        lambda: ClientToServer(shared),
        local_addr=(shared.args.listen_host, shared.args.listen_port))

    await loop.create_datagram_endpoint(
        lambda: ServerToClient(shared),
        remote_addr=(shared.args.connect_host, shared.args.connect_port))

    # loop runs

    await shared.on_con_lost

def make_arg_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument('--listen-host',
        type    = str,
        metavar = 'ADDRESS',
        default = '127.0.0.1',
        help    = 'listen for Mosh client on this address')

    parser.add_argument('--listen-port',
        type    = int,
        metavar = 'PORT',
        default = 1337,
        help    = 'listen for Mosh client on this port')

    parser.add_argument('--connect-host',
        type    = str,
        metavar = 'ADDRESS',
        default = '127.0.0.1',
        help    = 'connect to Mosh server on this address')

    parser.add_argument('--connect-port',
        type    = int,
        metavar = 'PORT',
        default = 60001,
        help    = 'connect to Mosh server on this port')

    parser.add_argument('-d', '--hexdump',
        default = False,
        action  = 'store_true',
        help    = 'print a full hexdump of each packet')

    parser.add_argument('-c', '--color',
        default = False,
        action  = 'store_true',
        help    = 'use colors in output')

    return parser

asyncio.run(main())
