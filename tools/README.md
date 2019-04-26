# `spy.py`

`spy.py` sits in between a Mosh client and server, providing information about
the packets flowing between them, and optionally messing with those packets.
Currently it has no ability to decrypt packets, so you will only see metadata
unless you are using an unencrypted fork of Mosh.

Pass `--help` for a full list of features.

Requirements: Python 3.7, [sh](https://amoffat.github.io/sh/), [NumPy](https://www.numpy.org/)

## Examples

Start a Mosh server:

```
$ mosh-server

MOSH CONNECT 60001 ZamjOTD89MCqH8wzyr7onQ
[...]
```

Start a Mosh client, pointed at `spy.py`'s default listen port of
[1337](https://www.urbandictionary.com/define.php?term=1337). You can do this
before starting `spy.py` because UDP is connectionless.

```
$ MOSH_KEY=ZamjOTD89MCqH8wzyr7onQ mosh-client 127.0.0.1 1337
```

Then start `spy.py` in another terminal and have fun!

```
$ ./spy.py -v
Listening for client on 127.0.0.1 port 1337
2019-04-25 12:49:18:    82 bytes from CLIENT
        00 00 00 00 00 00 00 13 2E 0C D5 D4 60 C7 02 8C
        24 CE 34 36 1A 24 7F 83 32 00 7C FD B1 FB F2 9C
        A7 E6 A4 BD 4C 82 15 7C 52 CF 37 AB AE 31 66 21
        33 3C 32 04 69 79 C8 35 AB 59 0E 4C 6B 03 D2 E5
        C9 96 A7 67 2B 85 4B 81 D3 05 60 2F 60 29 DD 0A
        33 5D
         |   min |   med |   max |      avg |      dev
    -----+-------+-------+-------+----------+---------
    size |    82 |    82 |    82 |    82.00 |     0.00

2019-04-25 12:49:18:   112 bytes from SERVER
        80 00 00 00 00 00 00 00 9C 2F E8 67 73 8C C2 E4
        05 7E F5 D9 40 D3 AD 12 A9 91 81 30 F6 06 27 36
        27 9D AA 94 80 6C 30 D0 C3 FE 04 85 17 E9 4E 19
        22 ED EF 6A 80 5F A4 11 C1 2C 7F 64 51 1C 2D 95
        74 80 6F 04 04 47 EF 95 E3 22 25 49 09 A8 44 7A
        47 B7 B2 52 4A 54 F5 C9 C4 C8 EE 51 2C 56 08 85
        14 0A 1C 7D 11 1C CD F1 9E AE 05 7B 78 21 E9 87
         |   min |   med |   max |      avg |      dev
    -----+-------+-------+-------+----------+---------
    size |   112 |   112 |   112 |   112.00 |     0.00
```

The beauty of a UDP-based protocol: You can restart `spy.py` to change settings
without restarting Mosh. Relive the glory days of the 9600 bps modem and marvel
at the fact that Mosh still sort of works!

```
$ ./spy.py --interfere-verbose --drop 0.25 --bitrate 9600 --max-in-flight 1
Listening for client on 127.0.0.1 port 1337

2019-04-25 12:55:15:    62 bytes from CLIENT
    DELAYED by 0.0517 sec
2019-04-25 12:55:15:    75 bytes from SERVER
    DROPPED this packet
2019-04-25 12:55:17:    75 bytes from CLIENT
    DELAYED by 0.0625 sec
2019-04-25 12:55:17:   110 bytes from SERVER
    DELAYED by 0.0917 sec
```
