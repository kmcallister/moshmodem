#!/usr/bin/env python3.7
import asyncio
import argparse
import datetime
import struct
import sh
import ast
from io import StringIO
from os import path

colors = {
    'client': '\x1B[1;32m',
    'server': '\x1B[1;36m',
    'reset':  '\x1B[0m',
}

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
    if args.color:
        print(colors[sender], end='')
    print('%s: %5d bytes from %-6s' % (timestamp, len(data), sender.upper()))
    if args.color:
        print(colors['reset'], end='')

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
        help    = 'parse protobufs too (requires protoc and Mosh source code)')

    output.add_argument('--mosh-source',
        type    = str,
        default = '$MOSHMODEM_TOOLS_DIR/../../moshmodem-mosh',
        help    = 'path to Mosh source directory')

    output.add_argument('-c', '--color',
        default = False,
        action  = 'store_true',
        help    = 'use colors in output')

    return parser

asyncio.run(main())
