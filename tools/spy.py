#!/usr/bin/env python3.7
import asyncio
import argparse
import datetime
import struct
import sh
import ast
from io import StringIO
from os import path
import numpy.random

colors = {
    'client': '\x1B[1;32m',
    'server': '\x1B[1;36m',
    'drop':   '\x1B[1;31m',
    'delay':  '\x1B[1;35m',
    'reset':  '\x1B[0m',
}

def print_with_color(cmdargs, color, *args, **kwargs):
    if cmdargs.color:
        print(colors[color], end='')
    print(*args, **kwargs)
    if cmdargs.color:
        print(colors['reset'], end='')

def dump_protobuf(args, proto_type, proto_file, data, indent=8, slurp_diff=False):
    mosh_source = args.mosh_source.replace('$MOSHMODEM_TOOLS_DIR',
        path.dirname(path.realpath(__file__)))
    protobufs_path = path.join(mosh_source, 'src/protobufs')
    proto_file_path = path.join(protobufs_path, proto_file)

    dump = sh.protoc('--proto_path', protobufs_path,
              '--decode', proto_type,
              proto_file_path,
              _in=data)

    ret = None
    for ln in dump.splitlines():
        if slurp_diff and ln.startswith('diff: '):
            ret = ast.literal_eval(ln[6:])
        else:
            print(' '*indent + ln)

    return ret

def bytes_to_hex(data, sep):
    return sep.join('{:02X}'.format(x) for x in data)

def print_packet(args, sender, data):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print_with_color(args, sender,
        '%s: %5d bytes from %-6s' % (timestamp, len(data), sender.upper()))

    idx = 0
    def field(n):
        nonlocal idx
        x = data[idx:idx+n]
        idx += n
        return x

    if args.hexdump:
        if args.parse:
            print('    Nonce    |', bytes_to_hex(field(8), ''))
            print('    Tag      |', bytes_to_hex(field(16), ''))
            print('    Times    | %5d / %5u' % struct.unpack('!HH', field(4)))
            print('    Inst. ID | %d' % struct.unpack('!Q', field(8)))
            frag_num = struct.unpack('!H', field(2))[0]
            frag_final = bool(frag_num & 0x8000)
            frag_num &= 0x7FFF
            print('    Fragment | %d (%s)' % (frag_num, 'final' if frag_final else 'continued'))
            print('    Body:')
            data = data[idx:]

        if args.parse and args.parse_protobufs:
            diff = dump_protobuf(args, 'TransportBuffers.Instruction',
                          'transportinstruction.proto',
                          data)
            #print(repr(diff))
            #if diff is not None:
            #    proto_type, proto_file = ('ClientBuffers.UserMessage', 'userinput.proto') \
            #        if sender == 'client' else ('HostBuffers.HostMessage', 'hostinput.proto')

            #    dump_protobuf(args, proto_type, proto_file, diff, indent=12)

        else:
            width = 16  # bytes
            for i in range(0, len(data), width):
                print('       ', bytes_to_hex(data[i:i+width], ' '))

class SharedData(object):
    def __init__(self, args):
        self.args = args

        # These should be futures, but it's tricky because you can't
        # 'await' inside the protocol callbacks. Doing it this way
        # risks a race condition, I think.
        self.ctos = None
        self.stoc = None

        self.loop = asyncio.get_running_loop()
        self.on_con_lost = self.loop.create_future()

class Proxy(object):
    def __init__(self, shared):
        self.shared = shared

    def interfere_and_send(self, transport, data, addr):
        args = self.shared.args

        if numpy.random.uniform() < args.drop:
            # Whoops! Butterfingers!
            if args.interfere_verbose:
                print_with_color(args, 'drop', '    DROPPED this packet')
            return

        gaussian_lag = numpy.random.normal(args.lag_mean, args.lag_stddev)
        if gaussian_lag < 0.0:
            gaussian_lag = 0.0

        bitrate_lag = 0.0
        if args.bitrate is not None:
            bitrate_lag = 8.0 * len(data) / args.bitrate

        lag = gaussian_lag + bitrate_lag
        if args.interfere_verbose and lag > 0.0:
            print_with_color(args, 'delay', '    DELAYED by %.4f sec' % (lag,))

        self.shared.loop.call_later(lag,
            lambda: transport.sendto(data, addr))

    def connection_lost(self, exc):
        self.shared.on_con_lost.set_result(True)

class ClientToServer(Proxy):
    def __init__(self, shared):
        super().__init__(shared)
        shared.ctos = self

    def connection_made(self, transport):
        print('Listening for client on %s port %d' %
            (self.shared.args.listen_host, self.shared.args.listen_port))
        self.transport = transport

    def datagram_received(self, data, addr):
        self.client_addr = addr
        args = self.shared.args
        print_packet(self.shared.args, 'client', data)
        self.interfere_and_send(self.shared.stoc.transport,
            data, (args.connect_host, args.connect_port))

class ServerToClient(Proxy):
    def __init__(self, shared):
        super().__init__(shared)
        shared.stoc = self

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        print_packet(self.shared.args, 'server', data)
        ctos = self.shared.ctos
        self.interfere_and_send(ctos.transport, data, ctos.client_addr)

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

    network = parser.add_argument_group('Network options')

    network.add_argument('--listen-host',
        type    = str,
        metavar = 'ADDRESS',
        default = '127.0.0.1',
        help    = 'listen for Mosh client on this address')

    network.add_argument('--listen-port',
        type    = int,
        metavar = 'PORT',
        default = 1337,
        help    = 'listen for Mosh client on this port')

    network.add_argument('--connect-host',
        type    = str,
        metavar = 'ADDRESS',
        default = '127.0.0.1',
        help    = 'connect to Mosh server on this address')

    network.add_argument('--connect-port',
        type    = int,
        metavar = 'PORT',
        default = 60001,
        help    = 'connect to Mosh server on this port')

    output = parser.add_argument_group('Output formatting')

    output.add_argument('-d', '--hexdump',
        default = False,
        action  = 'store_true',
        help    = 'print a full hexdump of each packet')

    output.add_argument('-p', '--parse',
        default = False,
        action  = 'store_true',
        help    = 'parse header fields before dumping (for unencrypted fork)')

    output.add_argument('-b', '--parse-protobufs',
        default = False,
        action  = 'store_true',
        help    = 'parse protobufs too (BUGGY, requires protoc and Mosh source code)')

    output.add_argument('--mosh-source',
        type    = str,
        default = '$MOSHMODEM_TOOLS_DIR/../../moshmodem-mosh',
        help    = 'path to Mosh source directory')

    output.add_argument('-c', '--color',
        default = False,
        action  = 'store_true',
        help    = 'use colors in output')

    interfere = parser.add_argument_group('Interfering with packets')

    interfere.add_argument('--interfere-verbose',
        default = False,
        action  = 'store_true',
        help    = 'print a message when interfering with packets')

    interfere.add_argument('--drop',
        default = 0.0,
        type    = float,
        help    = 'fraction of packets to randomly drop')

    interfere.add_argument('--lag-mean',
        default = 0.0,
        type    = float,
        help    = 'mean induced packet lag (seconds)')

    interfere.add_argument('--lag-stddev',
        default = 0.0,
        type    = float,
        help    = 'std. dev. of induced packet lag (seconds)')

    interfere.add_argument('--bitrate',
        default = None,
        type    = float,
        help    = 'delay packets to simulate limited bitrate (bps)')

    return parser

asyncio.run(main())
