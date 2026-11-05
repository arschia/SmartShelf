"""Linux-only QA runner: kernel filter blocks Internet sockets before importing tests.

This only removes permissions from this process and its children. It never changes
the application's runtime network policy or requests elevated permissions.
"""
import ctypes
import errno
import platform
import runpy
import socket
import sys
from pathlib import Path
import os
import faulthandler


def block_network():
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This QA filter only supports Linux x86_64; no tests were started.")
    class Instruction(ctypes.Structure):
        _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_=[('len',ctypes.c_ushort),('filter',ctypes.POINTER(Instruction))]
    allow=0x7fff0000
    denied=0x00050000|errno.EPERM
    # seccomp_data: nr at 0, arch at 4, first syscall argument at 16.
    # Accept local Unix sockets only. Imports and child processes start after
    # this filter, so the runtime cannot create Internet TCP or UDP sockets.
    # Keep local IPC syscalls available to the test harness.
    instructions=[
        (0x20,0,0,4), (0x15,1,0,0xc000003e), (0x06,0,0,denied),
        (0x20,0,0,0), (0x15,0,4,41),
        (0x20,0,0,16), (0x15,0,1,socket.AF_UNIX),
        (0x06,0,0,allow), (0x06,0,0,denied),
        (0x20,0,0,0),
    ]
    # Deny alternate x32 ABI calls as well.
    instructions += [(0x35,0,1,0x40000000),(0x06,0,0,denied),(0x06,0,0,allow)]
    array=(Instruction*len(instructions))(*(Instruction(*row) for row in instructions))
    program=Program(len(instructions),array)
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),"Could not remove privilege escalation capability")
    if libc.prctl(22,2,ctypes.byref(program),0,0)!=0:
        raise OSError(ctypes.get_errno(),"Could not install network-denial filter; tests will not run")


def self_check():
    for family in (socket.AF_INET,socket.AF_INET6):
        for kind in (socket.SOCK_STREAM,socket.SOCK_DGRAM):
            try:
                connection=socket.socket(family,kind)
            except PermissionError:
                continue
            connection.close()
            raise RuntimeError("Network-denial self-check failed; tests will not run")
    left,right=socket.socketpair()
    left.close();right.close()
    print("QA network isolation verified: IPv4/IPv6 TCP/UDP sockets denied by kernel; local socketpair works.",flush=True)


if __name__=='__main__':
    block_network()
    self_check()
    if sys.argv[1:]!=['--self-check']:
        os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
        faulthandler.dump_traceback_later(30,repeat=True)
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
        sys.argv=['pytest',*sys.argv[1:]]
        runpy.run_module('pytest',run_name='__main__')
