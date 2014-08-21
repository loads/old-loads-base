import logging
from logging import handlers
import os
import sys
import time
import socket
import zipfile
from StringIO import StringIO
import json
import urlparse
import math
import datetime
import fnmatch
import hashlib
import random

logger = logging.getLogger('loads')


def total_seconds(td):
    # works for 2.7 and 2.6
    diff = (td.seconds + td.days * 24 * 3600) * 10 ** 6
    return (td.microseconds + diff) / float(10 ** 6)


class DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return total_seconds(obj)
        else:
            return super(DateTimeJSONEncoder, self).default(obj)


def set_logger(debug=False, name='loads', logfile='stdout'):
    # setting up the logger
    logger_ = logging.getLogger(name)
    logger_.setLevel(logging.DEBUG)

    if logfile == 'stdout':
        ch = logging.StreamHandler()
    else:
        ch = handlers.RotatingFileHandler(logfile, mode='a+')

    if debug:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)

    formatter = logging.Formatter('[%(asctime)s][%(process)d] %(message)s')
    ch.setFormatter(formatter)
    logger_.addHandler(ch)

    # for the tests
    if 'TESTING' in os.environ:
        fh = logging.FileHandler('/tmp/loads.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)


GIGA = 1024. * 1024. * 1024.
# let's just make the assumption it won't change
# once loads is started
_HOST = None


def get_hostname():
    global _HOST
    if _HOST is None:
        _HOST = socket.gethostname()
    return _HOST


if sys.platform == "win32":
    timer = time.clock      # pragma: nocover
else:
    timer = time.time


def decode_params(params):
    """Decode a string into a dict. This is mainly useful when passing a dict
    trough the command line.

    The params passed in "params" should be in the form of key:value, separated
    by a pipe, the output is a python dict.
    """
    output_dict = {}
    for items in params.split('|'):
        key, value = items.split(':', 1)
        output_dict[key] = value
    return output_dict


def encode_params(intput_dict):
    """Convert the dict given in input into a string of key:value separated
    with pipes, like spam:yeah|eggs:blah

    The keys and values MUST be strings.
    """
    return '|'.join([':'.join(i) for i in intput_dict.items()])


def timed(debug=False):
    def _timed(func):
        def __timed(*args, **kw):
            start = timer()
            try:
                res = func(*args, **kw)
            finally:
                duration = timer() - start
                if debug:
                    logger.debug('%.4f' % duration)
            return duration, res
        return __timed
    return _timed


def split_endpoint(endpoint):
    """Returns the scheme, the location, and maybe the port.
    """
    res = {}
    parts = urlparse.urlparse(endpoint)
    res['scheme'] = parts.scheme

    if parts.scheme == 'tcp':
        netloc = parts.netloc.rsplit(':')
        if len(netloc) == 1:
            netloc.append('80')
        res['ip'] = netloc[0]
        res['port'] = int(netloc[1])
    elif parts.scheme == 'ipc':
        res['path'] = parts.path
    else:
        raise NotImplementedError()

    return res


_DNS_CACHE = {}


def null_streams(streams):
    """Set the given outputs to /dev/null to be sure we don't store their
    content in memory.

    This is useful when you want to spawn new processes and don't care about
    their outputs. The other approach, using subprocess.PIPE can slow down
    things and uses memory without any rationale.
    """
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        for stream in streams:
            if not hasattr(stream, 'fileno'):
                # we're probably dealing with a file-like
                continue
            try:
                stream.flush()
                os.dup2(devnull, stream.fileno())
            except IOError:
                # some streams, like stdin - might be already closed.
                pass
    finally:
        os.close(devnull)


def dict_hash(data, omit_keys=None):
    """Useful to identify a data mapping.
    """
    if omit_keys is None:
        omit_keys = []

    hash = hashlib.md5()

    for key, value in data.items():
        if key in omit_keys:
            continue
        hash.update(str(key))
        hash.update(str(value))
        hash.update('ENDMARKER')

    return hash.hexdigest()


def dns_resolve(url):
    """Resolve hostname in the given url, using cached results where possible.

    Given a url, this function does DNS resolution on the contained hostname
    and returns a 3-tuple giving:  the URL with hostname replace by IP addr,
    the original hostname string, and the resolved IP addr string.

    The results of DNS resolution are cached to make sure this doesn't become
    a bottleneck for the loadtest.  If the hostname resolves to multiple
    addresses then a random address is chosen.
    """
    parts = urlparse.urlparse(url)
    netloc = parts.netloc.rsplit(':')
    if len(netloc) == 1:
        netloc.append('80')

    original = netloc[0]
    addrs = _DNS_CACHE.get(original)
    if addrs is None:
        addrs = socket.gethostbyname_ex(original)[2]
        _DNS_CACHE[original] = addrs

    resolved = random.choice(addrs)
    netloc = resolved + ':' + netloc[1]
    parts = (parts.scheme, netloc) + parts[2:]
    return urlparse.urlunparse(parts), original, resolved


# taken from distutils2
def resolve_name(name):
    """Resolve a name like ``module.object`` to an object and return it.

    This functions supports packages and attributes without depth limitation:
    ``package.package.module.class.class.function.attr`` is valid input.
    However, looking up builtins is not directly supported: use
    ``__builtin__.name``.

    Raises ImportError if importing the module fails or if one requested
    attribute is not found.
    """

    # Depending how loads is ran, "" can or cannot be present in the path. This
    # adds it if it's missing.
    if len(sys.path) < 1 or sys.path[0] not in ('', os.getcwd()):
        sys.path.insert(0, '')

    if '.' not in name:
        # shortcut
        __import__(name)
        return sys.modules[name]

    # FIXME clean up this code!
    parts = name.split('.')
    cursor = len(parts)
    module_name = parts[:cursor]
    ret = ''

    while cursor > 0:
        try:
            ret = __import__('.'.join(module_name))
            break
        except ImportError:
            cursor -= 1
            module_name = parts[:cursor]

    if ret == '':
        raise ImportError(parts[0])

    for part in parts[1:]:
        try:
            ret = getattr(ret, part)
        except AttributeError, exc:
            raise ImportError(exc)

    return ret


def get_quantiles(data, quantiles):
    """Computes the quantiles for the data array you pass along.

    :param data: the input array
    :param quantiles: a list of quantiles you want to compute.

    This is an adapted version of an implementation by Ernesto P.Adorio Ph.D.
    UP Extension Program in Pampanga, Clark Field.

    Warning: this implentation is probably slow. We are using this atm to avoid
    depending on scipy, who have a much better and faster version, see
    scipy.stats.mstats.mquantiles

    References:
       http://reference.wolfram.com/mathematica/ref/Quantile.html
       http://wiki.r-project.org/rwiki/doku.php?id=rdoc:stats:quantile
       http://adorio-research.org/wordpress/?p=125

    """
    def _get_quantile(q, data_len):
        a, b, c, d = (1.0 / 3, 1.0 / 3, 0, 1)
        g, j = math.modf(a + (data_len + b) * q - 1)
        if j < 0:
                return data[0]
        elif j >= data_len:
                return data[data_len - 1]
        j = int(math.floor(j))

        if g == 0 or j == len(data) - 1:
            return data[j]
        else:
            return data[j] + (data[j + 1] - data[j]) * (c + d * g)

    data = sorted(data)
    data_len = len(data)

    return [_get_quantile(q, data_len) for q in quantiles]


def try_import(*packages):
    failed_packages = []
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            failed_packages.append(package)
    if failed_packages:
        failed_packages = " ".join(failed_packages)
        raise ImportError('You need to run "pip install %s"' % failed_packages)


def glob(patterns, location='.'):
    for pattern in patterns:
        basedir, pattern = os.path.split(pattern)
        basedir = os.path.abspath(os.path.join(location, basedir))
        for file_ in os.listdir(basedir):
            if fnmatch.fnmatch(file_, pattern):
                yield os.path.join(basedir, file_)


def pack_include_files(include_files, location='.'):
    """Package up the specified include_files into a zipfile data bundle.

    This is a convenience function for packaging up data files into a binary
    blob, that can then be shipped to the different agents.  Unpack the files
    using unpack_include_files().
    """
    file_data = StringIO()
    zf = zipfile.ZipFile(file_data, "w", compression=zipfile.ZIP_DEFLATED)

    def store_file(name, filepath):
        info = zipfile.ZipInfo(name)
        info.external_attr = os.stat(filepath).st_mode << 16L
        with open(filepath) as f:
            zf.writestr(info, f.read())

    for basepath in glob(include_files, location):
        basedir, basename = os.path.split(basepath)
        if not os.path.isdir(basepath):
            store_file(basename, basepath)
        else:
            for root, dirnames, filenames in os.walk(basepath):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    store_file(filepath[len(basedir):], filepath)

    zf.close()
    return file_data.getvalue().encode('base64')


def maybe_makedirs(dirpath):
    """Like os.makedirs, but no error if the final directory exists."""
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath)


def unpack_include_files(file_data, location='.'):
    """Unpack a blob of include_files data into the specified directory.

    This is a convenience function for unpackaging data files from a binary
    blob, that can be used on the different agents.  It accepts data in the
    format produced by pack_include_files().
    """
    file_data = str(file_data).decode('base64')
    zf = zipfile.ZipFile(StringIO(file_data))

    for itemname in zf.namelist():
        itempath = os.path.join(location, itemname.lstrip("/"))
        if itemname.endswith("/"):
            maybe_makedirs(itempath)
        else:
            maybe_makedirs(os.path.dirname(itempath))
            with open(itempath, "w") as f:
                f.write(zf.read(itemname))
            mode = zf.getinfo(itemname).external_attr >> 16L
            if mode:
                os.chmod(itempath, mode)
    zf.close()
