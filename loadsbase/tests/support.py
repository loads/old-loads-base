import os
import functools
import sys
import StringIO
import subprocess
import atexit

from loadsbase.util import logger


_processes = []


def start_process(cmd, *args):
    devnull = open('/dev/null', 'w')
    args = list(args)
    process = subprocess.Popen([sys.executable, '-m', cmd] + args,
                               stdout=devnull, stderr=devnull)
    _processes.append(process)
    return process


def stop_process(proc):
    proc.terminate()
    if proc in _processes:
        _processes.remove(proc)


def stop_processes():
    for proc in _processes:
        try:
            proc.terminate()
        except OSError:
            pass

    _processes[:] = []


atexit.register(stop_processes)


def get_tb():
    """runs an exception and return the traceback information"""
    try:
        raise Exception('Error message')
    except Exception:
        return sys.exc_info()


def hush(func):
    """Make the passed function silent."""
    @functools.wraps(func)
    def _silent(*args, **kw):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO.StringIO()
        sys.stderr = StringIO.StringIO()
        debug = []

        def _debug(msg):
            debug.append(str(msg))

        old_debug = logger.debug
        logger.debug = _debug
        try:
            return func(*args, **kw)
        except:
            sys.stdout.seek(0)
            print(sys.stdout.read())
            sys.stderr.seek(0)
            print(sys.stderr.read())
            print('\n'.join(debug))
            raise
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            logger.debug = old_debug
    return _silent


_files = []


def rm_onexit(path):
    _files.append(path)


def cleanup_files():
    for _file in _files:
        if os.path.exists(_file):
            os.remove(_file)


atexit.register(cleanup_files)


# taken from http://emptysqua.re/blog/undoing-gevents-monkey-patching/
def patch_socket(aggressive=True):
    """Like gevent.monkey.patch_socket(), but stores old socket attributes for
    unpatching.
    """
    from gevent import socket
    _socket = __import__('socket')

    old_attrs = {}
    for attr in (
        'socket', 'SocketType', 'create_connection', 'socketpair', 'fromfd'
    ):
        if hasattr(_socket, attr):
            old_attrs[attr] = getattr(_socket, attr)
            setattr(_socket, attr, getattr(socket, attr))

    try:
        from gevent.socket import ssl, sslerror
        old_attrs['ssl'] = _socket.ssl
        _socket.ssl = ssl
        old_attrs['sslerror'] = _socket.sslerror
        _socket.sslerror = sslerror
    except ImportError:
        if aggressive:
            try:
                del _socket.ssl
            except AttributeError:
                pass

    return old_attrs


def unpatch_socket(old_attrs):
    """Take output of patch_socket() and undo patching."""
    _socket = __import__('socket')

    for attr in old_attrs:
        if hasattr(_socket, attr):
            setattr(_socket, attr, old_attrs[attr])
