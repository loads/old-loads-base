from tempfile import mkstemp, mkdtemp
import datetime
import mock
import os
import unittest2 as unittest2
import sys
import StringIO
import shutil

from loadsbase import util
import loadsbase
from loadsbase.util import (resolve_name, set_logger, logger, dns_resolve,
                            DateTimeJSONEncoder, try_import, split_endpoint,
                            null_streams, get_quantiles, pack_include_files,
                            unpack_include_files, dict_hash)


class FakeStdout(object):
    def fileno(self):
        return 1

    def flush(self):
        pass

    def write(self, data):
        pass


class TestUtil(unittest2.TestCase):
    def setUp(self):
        util._DNS_CACHE = {}
        self.stdout = sys.stdout
        sys.stdout = FakeStdout()

    def tearDown(self):
        sys.stdout = self.stdout

    def test_resolve(self):
        ob = resolve_name('loadsbase.tests.test_util.TestUtil')
        self.assertTrue(ob is TestUtil)
        ob = resolve_name('loadsbase')
        self.assertTrue(ob is loadsbase)

        self.assertRaises(ImportError, resolve_name, 'xx.cc')
        self.assertRaises(ImportError, resolve_name, 'xx')
        self.assertRaises(ImportError, resolve_name, 'loads.xx')

    @mock.patch('sys.path', [])
    def test_resolve_adds_path(self):
        ob = resolve_name('loadsbase.tests.test_util.TestUtil')
        self.assertTrue(ob is TestUtil)
        self.assertTrue('' in sys.path)
        old_len = len(sys.path)

        # And checks that it's not added twice
        ob = resolve_name('loadsbase.tests.test_util.TestUtil')
        self.assertEquals(len(sys.path), old_len)

    def test_set_logger(self):
        before = len(logger.handlers)
        set_logger()
        self.assertTrue(len(logger.handlers), before + 1)

        fd, logfile = mkstemp()
        os.close(fd)
        set_logger(debug=True)
        set_logger(logfile=logfile)
        os.remove(logfile)

    def test_split_endpoint(self):
        res = split_endpoint('tcp://12.22.33.45:12334')
        self.assertEqual(res['scheme'], 'tcp')
        self.assertEqual(res['ip'], '12.22.33.45')
        self.assertEqual(res['port'], 12334)

        res = split_endpoint('ipc:///here/it/is')
        self.assertEqual(res['scheme'], 'ipc')
        self.assertEqual(res['path'], '/here/it/is')

        self.assertRaises(NotImplementedError, split_endpoint,
                          'wat://ddf:ff:f')

    def test_datetime_json_encoder(self):
        encoder = DateTimeJSONEncoder()
        date = datetime.datetime(2013, 5, 30, 18, 35, 11, 550482)
        delta = datetime.timedelta(0, 12, 126509)
        self.assertEquals(encoder.encode(date), '"2013-05-30T18:35:11.550482"')
        self.assertEquals(encoder.encode(delta), '12.126509')
        self.assertRaises(TypeError, encoder.encode, os)

    def test_try_import(self):
        try_import("loadsbase")
        try_import("loadsbase.util", "loadsbase.tests")
        with self.assertRaises(ImportError):
            try_import("loadsbase.nonexistent1", "loadsbase.nonexistent2")

    def test_get_quantiles(self):
        data = range(100)
        quantiles = 0, 0.1, 0.5, 0.9, 1
        res = get_quantiles(data, quantiles)
        self.assertEqual(len(res), 5)

    def test_nullstreams(self):
        stream = StringIO.StringIO()
        null_streams([stream, sys.stdout])
        stream.write('ok')
        sys.stdout.write('ok')

    def test_dns_resolve(self):
        resolved = dns_resolve('http://ziade.org')
        self.assertEqual(resolved[1], 'ziade.org')
        self.assertTrue('ziade.org' in util._DNS_CACHE)


class TestIncludeFileHandling(unittest2.TestCase):

    def setUp(self):
        self.workdir = mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.workdir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.workdir)

    def test_include_of_single_file(self):
        with open("test1.txt", "w") as f:
            f.write("hello world")
        filedata = pack_include_files(["test1.txt"])
        os.makedirs("outdir")
        os.chdir("outdir")
        unpack_include_files(filedata)
        self.assertEquals(os.listdir("."), ["test1.txt"])

    def test_include_of_single_file_with_explicit_location(self):
        os.makedirs("indir")
        os.makedirs("outdir")
        with open("indir/test1.txt", "w") as f:
            f.write("hello world")
        filedata = pack_include_files(["*.txt"], "./indir")
        unpack_include_files(filedata, "./outdir")
        self.assertEquals(os.listdir("outdir"), ["test1.txt"])

    def test_preservation_of_file_mode(self):
        with open("test1.sh", "w") as f:
            f.write("#!/bin/sh\necho 'hello world'\n")
        os.chmod("test1.sh", 0755)
        with open("private.txt", "w") as f:
            f.write("TOP SECRET DATA\n")
        os.chmod("private.txt", 0600)
        filedata = pack_include_files(["*.*"])
        os.unlink("test1.sh")
        os.unlink("private.txt")
        unpack_include_files(filedata)
        self.assertEquals(os.stat("test1.sh").st_mode & 0777, 0755)
        self.assertEquals(os.stat("private.txt").st_mode & 0777, 0600)

    def test_relative_globbing_and_direcotry_includes(self):
        os.makedirs("indir")
        os.makedirs("outdir")
        os.chdir("indir")
        with open("test1.txt", "w") as f:
            f.write("hello world")
        with open("test2.txt", "w") as f:
            f.write("hello world")
        os.makedirs("subdir/subsubdir")
        os.chdir("subdir/subsubdir")
        with open("test3.txt", "w") as f:
            f.write("hello world")
        os.chdir("../../../outdir")
        filedata = pack_include_files(["../indir/*.txt", "../indir/*dir"])
        unpack_include_files(filedata)
        self.assertEquals(sorted(os.listdir(".")),
                          ["subdir", "test1.txt", "test2.txt"])
        self.assertEquals(os.listdir("./subdir"), ["subsubdir"])
        self.assertEquals(os.listdir("./subdir/subsubdir"), ["test3.txt"])

    def test_unicode_unpack(self):
        # make sure we pass string
        data = (u'PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                '\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        unpack_include_files(data.encode('base64'))

    def test_dict_hash(self):
        data1 = {1: 2, 3: 4}
        data2 = {1: 2, 3: 4}

        self.assertEqual(dict_hash(data1), dict_hash(data2))

        data1['count'] = 'b'
        self.assertNotEqual(dict_hash(data1), dict_hash(data2))

        self.assertEqual(dict_hash(data1, omit_keys=['count']),
                         dict_hash(data2))
