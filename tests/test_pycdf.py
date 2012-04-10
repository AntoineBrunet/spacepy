#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit test suite for pycdf

Copyright ©2010 Los Alamos National Security, LLC.
"""

import ctypes
import datetime
import gc
import hashlib
import os, os.path
import shutil
import sys
import tempfile
import unittest
import warnings

try:
    type(callable)
except NameError:
    import collections
    def callable(obj):
        return isinstance(obj, collections.Callable)

import numpy
import numpy.testing
import spacepy.pycdf as cdf
import spacepy.pycdf.const as const


class est_tz(datetime.tzinfo):
    """Eastern Standard timezone (no daylight time"""

    def utcoffset(self, dt):
        """Offset from UTC"""
        return datetime.timedelta(hours=-5)

    def dst(self, dt):
        """Minute offset for DST"""
        return datetime.timedelta(0)

    def tzname(self, dt):
        """Name of this time zone"""
        return 'EST'


class NoCDF(unittest.TestCase):
    """Tests that do not involve a CDF file"""
    def testErrorMessage(self):
        """Displays correct messages for exceptions"""
        exceptdic = { cdf.const.CDF_OK:
                      'CDF_OK: Function completed successfully.',
                      cdf.const.ATTR_EXISTS:
                      'ATTR_EXISTS: Named attribute already exists.',
                      cdf.const.CDF_CREATE_ERROR:
                      'CDF_CREATE_ERROR: Creation failed - error from file system.',
                      }
        for status, message in list(exceptdic.items()):
            try:
                raise cdf.CDFError(status)
            except cdf.CDFError:
                (type, val, traceback) = sys.exc_info()
                self.assertEqual(val.__str__(), message)
            else:
                self.assertTrue(False, 'Should have raised a CDFError: ' + message)

    def testHypersliceReorder(self):
        """Reorders sequences to switch array majority"""
        input = [[1, 2, 3, 4, 5], [3, -5, 6, 12], ]
        output = [[1, 5, 4, 3, 2], [3, 12, 6, -5], ]
        for (inp, outp) in zip(input, output):
            self.assertEqual(cdf._pycdf._Hyperslice.reorder(inp).tolist(),
                             outp)

    def testHypersliceconvert(self):
        """Converts start/stop/step to CDF intervals"""
        input = [[None, None, None, 5],
                 [1, 4, None, 5],
                 [-5, -1, 1, 5],
                 [-1, -5, 1, 5],
                 [-1, -5, -1, 5],
                 [-1, -6, -1, 5],
                 [-1, None, -1, 5],
                 [-1, -20, -1, 5],
                 [-4, 0, -6, 10],
                 [-10, 10, 4, 10],
                 [-10, -6, 9, 10],
                 [-6, -9, -7, 10],
                 [-4, -9, -2, 10],
                 [-2, -1, -2, 10],
                 [-3, 4, -1, 10],
                 [10, -17, 10, 20],
                 [-6, -15, -10, 20],
                 ]
        output = [[0, 5, 1, False],
                  [1, 3, 1, False],
                  [0, 4, 1, False],
                  [0, 0, 1, False],
                  [1, 4, 1, True],
                  [0, 5, 1, True],
                  [0, 5, 1, True],
                  [0, 5, 1, True],
                  [6, 1, 6, True],
                  [0, 3, 4, False],
                  [0, 1, 9, False],
                  [4, 1, 7, True],
                  [2, 3, 2, True],
                  [10, 0, 2, True],
                  [5, 3, 1, True],
                  [10, 0, 10, False],
                  [14, 1, 10, True],
                  ]
        for (inp, outp) in zip(input, output):
            result = cdf._pycdf._Hyperslice.convert_range(*inp)
            self.assertEqual(tuple(outp), result,
                             str(tuple(outp)) + ' != ' + str(result) +
                             ' for input ' + str(inp))

    def testHypersliceDimensions(self):
        """Find dimensions of an array"""
        data = [[[2, 3], [4, 5], [6, 7]],
                [[8, 9], [0, 1], [2, 3]],
                [[4, 5], [6, 7], [8, 9]],
                [[0, 1], [2, 3], [4, 5]],
                ]
        self.assertEqual(cdf._pycdf._Hyperslice.dimensions(data),
                         [4, 3, 2])

        data = [[[2, 3], [4, 5], [6, 7]],
                [[8, 9], [0, 1], [2, 3]],
                [[4, 5], [6, 7],],
                [[0, 1], [2, 3], [4, 5]],
                ]
        message = 'Data irregular in dimension 1'
        try:
            cdf._pycdf._Hyperslice.dimensions(data)
        except ValueError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should raise ValueError: ' + message)

        self.assertEqual(cdf._pycdf._Hyperslice.dimensions('hi'),
                         [])

    def testFlipMajority(self):
        """Changes the majority of an array"""
        #Code to generate this 5x5x5:
        #[[[random.randint(0,100) for i in range(5)]
        #  for j in range(5)] for k in range(5)]
        three_d = [[[90, 90, 96, 71, 90], [29, 18, 90, 78, 51],
                   [14, 29, 41, 25, 50], [73, 59, 83, 92, 24],
                   [10, 1, 4, 61, 54]],
                  [[40, 8, 0, 28, 47], [3, 98, 28, 9, 38],
                   [34, 95, 7, 87, 9], [11, 73, 71, 54, 69],
                   [42, 75, 82, 16, 73]],
                  [[88, 40, 5, 69, 41], [35, 15, 32, 68, 8],
                   [68, 74, 6, 30, 9], [86, 48, 52, 49, 100],
                   [8, 35, 26, 16, 61]],
                  [[49, 81, 57, 37, 98], [54, 64, 28, 21, 17],
                   [73, 100, 90, 8, 25], [40, 75, 52, 41, 40],
                   [42, 72, 55, 16, 39]],
                  [[24, 38, 26, 85, 25], [5, 98, 63, 29, 33],
                   [91, 100, 17, 85, 9], [59, 50, 50, 41, 82],
                   [21, 45, 65, 51, 90]]]
        flipped = cdf._pycdf._Hyperslice.flip_majority(three_d)
        for i in range(5):
            for j in range(5):
                for k in range(5):
                    self.assertEqual(three_d[i][j][k],
                                     flipped[k][j][i],
                                     'Original index ' +
                                     str(i) + ', ' +
                                     str(j) + ', ' +
                                     str(k) + ' mismatch ' +
                                     str(three_d[i][j][k]) + ' != ' +
                                     str(flipped[k][j][i]))

        #[[[[random.randint(0,100) for i in range(5)]
        #  for j in range(4)] for k in range(3)] for l in range(2)]
        four_d = [[[[14, 84, 79, 74, 45], [39, 47, 93, 32, 59],
                    [15, 47, 1, 84, 44], [13, 43, 13, 88, 3]],
                   [[65, 75, 36, 90, 93], [64, 36, 59, 39, 42],
                    [59, 85, 21, 88, 61], [64, 29, 62, 33, 35]],
                   [[46, 69, 3, 50, 44], [86, 15, 32, 17, 51],
                    [79, 20, 29, 10, 55], [29, 10, 79, 7, 58]]],
                  [[[20, 76, 81, 40, 85], [44, 56, 5, 83, 32],
                    [34, 88, 23, 57, 74], [24, 55, 83, 39, 60]],
                   [[79, 56, 5, 98, 29], [28, 50, 77, 33, 45],
                    [38, 82, 82, 28, 97], [42, 14, 56, 48, 38]],
                   [[58, 27, 38, 43, 25], [72, 91, 85, 44, 43],
                    [17, 57, 91, 19, 35], [98, 62, 61, 14, 60]]]]
        flipped = cdf._pycdf._Hyperslice.flip_majority(four_d)
        for i in range(2):
            for j in range(3):
                for k in range(4):
                    for l in range(5):
                        self.assertEqual(four_d[i][j][k][l],
                                         flipped[l][k][j][i],
                                         'Original index ' +
                                         str(i) + ', ' +
                                         str(j) + ', ' +
                                         str(k) + ', ' +
                                         str(l) + ' mismatch ' +
                                         str(four_d[i][j][k][l]) + ' != ' +
                                         str(flipped[l][k][j][i]))

        zero_d = 1
        flipped = cdf._pycdf._Hyperslice.flip_majority(zero_d)
        self.assertEqual(zero_d, flipped)

        one_d = [1, 2, 3, 4]
        flipped = cdf._pycdf._Hyperslice.flip_majority(one_d)
        self.assertEqual(one_d, flipped)

        two_d = [[6, 7, 48, 81], [61, 67, 90, 99], [71, 96, 58, 85],
                 [35, 31, 71, 73], [77, 41, 71, 92], [74, 89, 94, 64],
                 [64, 30, 66, 94]]
        flipped = cdf._pycdf._Hyperslice.flip_majority(two_d)
        for i in range(7):
            for j in range(4):
                self.assertEqual(two_d[i][j],
                                 flipped[j][i],
                                 'Original index ' +
                                 str(i) + ', ' +
                                 str(j) + ' mismatch ' +
                                 str(two_d[i][j]) + ' != ' +
                                 str(flipped[j][i]))

    def testFlipMajorityBad(self):
        """Changes the majority of an array, bad input"""
        flip = cdf._pycdf._Hyperslice.flip_majority
        input = [[1, 2, 3], [1, 2]]
        message = 'Array dimensions not regular'
        try:
            flip(input)
        except TypeError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(str(v), message)
        else:
            self.fail('Should have raised TypeError: ' + message)
        input = [[[1, 2, 3], [4, 5, 6]], [7, 8]]

    def testEpoch16ToDatetime(self):
        epochs = [[63397987199.0, 999999999999.0],
                  [-1.0, -1.0],
                  [0.0, 0.0],
                  ]
        dts = [datetime.datetime(2009, 1, 1),
               datetime.datetime(9999, 12, 13, 23, 59, 59, 999999),
               datetime.datetime(9999, 12, 13, 23, 59, 59, 999999),
               ]
        for (epoch, dt) in zip(epochs, dts):
            self.assertEqual(dt, cdf.lib.epoch16_to_datetime(*epoch))
        result = cdf.lib.v_epoch16_to_datetime(numpy.array(epochs))
        expected = numpy.array(dts)
        numpy.testing.assert_array_equal(expected, result)

    def testEpochToDatetime(self):
        epochs = [63397987200000.0,
                  -1.0,
                  0.0,
                  ]
        dts = [datetime.datetime(2009, 1, 1),
               datetime.datetime(9999, 12, 13, 23, 59, 59, 999000),
               datetime.datetime(9999, 12, 13, 23, 59, 59, 999000),
               ]
        for (epoch, dt) in zip(epochs, dts):
            self.assertEqual(dt, cdf.lib.epoch_to_datetime(epoch))
        result = cdf.lib.v_epoch_to_datetime(numpy.array(epochs))
        expected = numpy.array(dts)
        numpy.testing.assert_array_equal(expected, result)

    def testDatetimeToEpoch16(self):
        epochs = [(63397987200.0, 0.0),
                  (63397987200.0, 0.0),
                  ]
        dts = [datetime.datetime(2009, 1, 1),
               datetime.datetime(2008, 12, 31, 19, tzinfo=est_tz()),
               ]
        for (epoch, dt) in zip(epochs, dts):
            self.assertEqual(epoch, cdf.lib.datetime_to_epoch16(dt))
        result = cdf.lib.v_datetime_to_epoch16(numpy.array(dts))
        expected = numpy.array(epochs)
        numpy.testing.assert_array_equal(expected, result)

    def testDatetimeToEpoch(self):
        epochs = [63397987200000.0,
                  63397987200000.0,
                  63397987200001.0,
                  ]
        dts = [datetime.datetime(2009, 1, 1),
               datetime.datetime(2008, 12, 31, 19, tzinfo=est_tz()),
               datetime.datetime(2009, 1, 1, 0, 0, 0, 501),
               ]
        for (epoch, dt) in zip(epochs, dts):
            self.assertEqual(epoch, cdf.lib.datetime_to_epoch(dt))
        result = cdf.lib.v_datetime_to_epoch(numpy.array(dts))
        expected = numpy.array(epochs)
        numpy.testing.assert_array_equal(expected, result)

    def testDatetimeEpoch16RT(self):
        """Roundtrip datetimes to epoch16s and back"""
        dts = [datetime.datetime(2008, 12, 15, 3, 12, 5, 1000),
               datetime.datetime(1821, 1, 30, 2, 31, 5, 23000),
               datetime.datetime(2050, 6, 5, 15, 0, 5, 0),
               ]
        for dt in dts:
            self.assertEqual(dt, cdf.lib.epoch16_to_datetime(
                *cdf.lib.datetime_to_epoch16(dt)))

    def testDatetimeEpochRT(self):
        """Roundtrip datetimes to epochs and back"""
        dts = [datetime.datetime(2008, 12, 15, 3, 12, 5, 1000),
               datetime.datetime(1821, 1, 30, 2, 31, 5, 23000),
               datetime.datetime(2050, 6, 5, 15, 0, 5, 0),
               ]
        for dt in dts:
            self.assertEqual(dt, cdf.lib.epoch_to_datetime(
                cdf.lib.datetime_to_epoch(dt)))

    def testIgnoreErrors(self):
        """Call the library and ignore particular error"""
        nbytes = ctypes.c_long(0)
        status = cdf.lib.call(cdf.const.GET_, cdf.const.DATATYPE_SIZE_,
                              ctypes.c_long(100), ctypes.byref(nbytes),
                              ignore=(cdf.const.BAD_DATA_TYPE,))
        self.assertEqual(cdf.const.BAD_DATA_TYPE, status)

    def testVersion(self):
        """Check library's version"""
        self.assertTrue(cdf.lib.version[0] in (2, 3))
        self.assertTrue(cdf.lib.version[1] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertTrue(cdf.lib.version[2] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertTrue(cdf.lib.version[3] in (b'', b' ', b'a'))
        if cdf.lib.version == (3, 3, 0, ' '):
            self.assertTrue(cdf.lib._del_middle_rec_bug)
        elif cdf.lib.version == (3, 3, 1, ' '):
            self.assertFalse(cdf.lib._del_middle_rec_bug)

    def testTypeGuessing(self):
        """Guess CDF types based on input data"""
        samples = [[1, 2, 3, 4],
                   [[1.2, 1.3, 1.4], [2.2, 2.3, 2.4]],
                   ['hello', 'there', 'everybody'],
                   datetime.datetime(2009, 1, 1),
                   datetime.datetime(2009, 1, 1, 12, 15, 12, 1),
                   [1.0],
                   0.0,
                   ]
        types = [([4], [const.CDF_BYTE, const.CDF_INT1, const.CDF_UINT1,
                        const.CDF_INT2, const.CDF_UINT2,
                        const.CDF_INT4, const.CDF_UINT4,
                        const.CDF_FLOAT, const.CDF_REAL4,
                        const.CDF_DOUBLE, const.CDF_REAL8], 1),
                 ([2, 3], [const.CDF_FLOAT, const.CDF_REAL4,
                           const.CDF_DOUBLE, const.CDF_REAL8], 1),
                 ([3], [const.CDF_CHAR, const.CDF_UCHAR], 9),
                 ([], [const.CDF_EPOCH, const.CDF_EPOCH16], 1),
                 ([], [const.CDF_EPOCH16, const.CDF_EPOCH], 1),
                 ([1], [const.CDF_FLOAT, const.CDF_REAL4,
                        const.CDF_DOUBLE, const.CDF_REAL8], 1),
                 ([], [const.CDF_FLOAT, const.CDF_REAL4,
                       const.CDF_DOUBLE, const.CDF_REAL8], 1),
                 ]
        for (s, t) in zip(samples, types):
            t = (t[0], [i.value for i in t[1]], t[2])
            self.assertEqual(t, cdf._pycdf._Hyperslice.types(s))


class MakeCDF(unittest.TestCase):
    def setUp(self):
        self.testdir = tempfile.mkdtemp()
        self.testfspec = os.path.join(self.testdir, 'foo.cdf')
        self.testmaster = 'po_l1_cam_testc.cdf'

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def testOpenCDFNew(self):
        """Create a new CDF"""

        newcdf = cdf.CDF(self.testfspec, '')
        self.assertTrue(os.path.isfile(self.testfspec))
        self.assertFalse(newcdf.readonly())
        newcdf.close()
        os.remove(self.testfspec)

    def testOpenCDFNonexistent(self):
        """Open a CDF which doesn't exist"""

        self.assertRaises(cdf.CDFError, cdf.CDF, self.testfspec)

    def testOpenCDFNoMaster(self):
        """Open a CDF from a master CDF which doesn't exist"""

        self.assertRaises(IOError, cdf.CDF, self.testfspec, 'nonexist.cdf')

    def testCDFNewMajority(self):
        """Creates a new CDF and changes majority"""
        newcdf = cdf.CDF(self.testfspec, '')
        newcdf.col_major(True)
        self.assertTrue(newcdf.col_major())
        newcdf.col_major(False)
        self.assertFalse(newcdf.col_major())
        newcdf.close()
        os.remove(self.testfspec)

    def testCreateCDFFromMaster(self):
        """Create a CDF from a master"""
        newcdf = cdf.CDF(self.testfspec, self.testmaster)
        self.assertTrue('ATC' in newcdf)
        self.assertFalse(newcdf.readonly())
        newcdf.close()
        os.remove(self.testfspec)

    def testCreateCDFBackward(self):
        """Try a backward-compatible CDF"""
        cdf.lib.set_backward(True)
        newcdf = cdf.CDF(self.testfspec, '')
        (ver, rel, inc) = newcdf.version()
        newcdf.close()
        os.remove(self.testfspec)
        self.assertEqual(2, ver)

        cdf.lib.set_backward(False)
        newcdf = cdf.CDF(self.testfspec, '')
        (ver, rel, inc) = newcdf.version()
        newcdf.close()
        os.remove(self.testfspec)
        self.assertEqual(3, ver)
        cdf.lib.set_backward(True)

    def testNewEPOCHAssign(self):
        """Create a new epoch variable by assigning to a CDF element"""
        cdf.lib.set_backward(True)
        newcdf = cdf.CDF(self.testfspec, '')
        data = [datetime.datetime(2000, 1, 1, 0, 0, 0, 999999),
                datetime.datetime(2001, 1, 1, 0, 0, 0, 999999)]
        newcdf['newzVar'] = data
        newtype = newcdf['newzVar'].type()
        newdata = newcdf['newzVar'][...]
        newcdf.close()
        os.remove(self.testfspec)
        self.assertEqual(const.CDF_EPOCH.value, newtype)
        numpy.testing.assert_array_equal(
            [datetime.datetime(2000, 1, 1, 0, 0, 1),
             datetime.datetime(2001, 1, 1, 0, 0, 1)],
            newdata)

    def testCreateCDFLeak(self):
        """Make a CDF that doesn't get collected"""
        newcdf = cdf.CDF(self.testfspec, '')
        newcdf.close()
        gc.collect()
        old_garblen = len(gc.garbage)
        del newcdf
        os.remove(self.testfspec)
        gc.collect()
        new_garblen = len(gc.garbage)
        self.assertEqual(old_garblen, new_garblen)


class CDFTestsBase(unittest.TestCase):
    """Base class for tests involving existing CDF, column or row major"""
    def __init__(self, *args, **kwargs):
        self.testfile = os.path.join(tempfile.gettempdir(), self.testbase)
        assert(self.calcDigest(self.testmaster) == self.expected_digest)
        super(CDFTestsBase, self).__init__(*args, **kwargs)

    @staticmethod
    def calcDigest(file):
        m = hashlib.md5()
        with open(file, 'rb') as f:
            m.update(f.read())
        return m.hexdigest()


class CDFTests(CDFTestsBase):
    """Tests that involve an existing CDF, read or write"""
    testmaster = 'po_l1_cam_test.cdf'
    testbase = 'test.cdf'
    expected_digest = '39833ef7046c10d001dd6f2cbd2a2ef5'


class ColCDFTests(CDFTestsBase):
    """Tests that involve an existing column-major CDF, read or write"""
    testmaster = 'po_l1_cam_testc.cdf'
    testbase = 'testc.cdf'
    expected_digest = '7728439e20bece4c0962a125373345bf'


class OpenCDF(CDFTests):
    """Tests that open a CDF"""
    def setUp(self):
        shutil.copy(self.testmaster, self.testfile)

    def tearDown(self):
        os.remove(self.testfile)

    def testopenUnicode(self):
        """Opens a CDF providing a Unicode name"""
        try:
            cdffile = cdf.CDF(unicode(self.testfile))
        except NameError: #Py3k, all strings are unicode
            cdffile = cdf.CDF(self.testfile)
        cdffile.close()
        del cdffile

    def testcreateMaster(self):
        """Creates a new CDF from a master"""
        testfspec = 'foo.cdf'
        new = cdf.CDF(testfspec, self.testfile)
        new.close()
        self.assertTrue(os.path.isfile(testfspec))
        self.assertEqual(self.calcDigest(testfspec), self.calcDigest(self.testfile))
        os.remove(testfspec)

    def testcreateMasterExisting(self):
        """Creates a new CDF from a master, on top of an existing"""
        testfspec = 'foo.cdf'
        open(testfspec, 'w').close()
        errstr = 'CDF_EXISTS: The CDF named already exists.'
        try:
            new = cdf.CDF(testfspec, self.testfile)
        except cdf.CDFError:
            self.assertEqual(sys.exc_info()[1].__str__(),
                             errstr)
        else:
            self.fail('Should have raised CDFError: ' +
                      errstr)
        os.remove(testfspec)

    def testContextManager(self):
        expected = ['ATC', 'PhysRecNo', 'SpinNumbers', 'SectorNumbers',
                    'RateScalerNames', 'SectorRateScalerNames',
                    'SectorRateScalersCounts', 'SectorRateScalersCountsSigma',
                    'SpinRateScalersCounts', 'SpinRateScalersCountsSigma',
                    'MajorNumbers', 'MeanCharge', 'Epoch', 'Epoch2D',
                    'String1D']
        with cdf.CDF(self.testfile) as f:
            names = list(f.keys())
        self.assertEqual(expected, names)
        self.assertRaises(cdf.CDFError, f.close)

    def testOpenCDFLeak(self):
        """Open a CDF that doesn't get collected"""
        cdffile = cdf.CDF(self.testfile)
        cdffile.close()
        gc.collect()
        old_garblen = len(gc.garbage)
        del cdffile
        gc.collect()
        new_garblen = len(gc.garbage)
        self.assertEqual(old_garblen, new_garblen)


class ReadCDF(CDFTests):
    """Tests that read an existing CDF, but do not modify it."""
    testbase = 'test_ro.cdf'

    def __init__(self, *args, **kwargs):
        super(ReadCDF, self).__init__(*args, **kwargs)
        #Unittest docs say 'the order in which the various test cases will be
        #run is determined by sorting the test function names with the built-in
        #cmp() function'
        testnames = [name for name in dir(self)
                     if name[0:4] == 'test' and callable(getattr(self,name))]
        self.last_test = max(testnames)

    def setUp(self):
        super(ReadCDF, self).setUp()
        if not os.path.exists(self.testfile):
            shutil.copy(self.testmaster, self.testfile)
        self.cdf = cdf.CDF(self.testfile)

    def tearDown(self):
        self.cdf.close()
        del self.cdf
        if self._testMethodName == self.last_test:
            os.remove(self.testfile)
        super(ReadCDF, self).tearDown()

    def testGetATC(self):
        """Get ATC zVar using subscripting"""
        atc = self.cdf['ATC']
        self.assertEqual(type(atc), cdf.Var)

    def testGetATCByNum(self):
        """Get ATC zVar using subscripting by variable number"""
        atc = self.cdf[0]
        self.assertEqual(type(atc), cdf.Var)
        self.assertEqual(atc.name(), 'ATC')

    def testGetAllzVars(self):
        """Check getting a list of zVars"""
        expectedNames = ['ATC', 'PhysRecNo', 'SpinNumbers', 'SectorNumbers',
                         'RateScalerNames', 'SectorRateScalerNames',
                         'SectorRateScalersCounts', 'SectorRateScalersCountsSigma',
                         'SpinRateScalersCounts', 'SpinRateScalersCountsSigma',
                         'MajorNumbers', 'MeanCharge', 'Epoch', 'Epoch2D',
                         'String1D']
        names = [zVar.name() for zVar in self.cdf.values()]
        self.assertEqual(names, expectedNames)

    def testGetAllVarNames(self):
        """Getting a list of zVar names"""
        expectedNames = ['ATC', 'PhysRecNo', 'SpinNumbers', 'SectorNumbers',
                         'RateScalerNames', 'SectorRateScalerNames',
                         'SectorRateScalersCounts', 'SectorRateScalersCountsSigma',
                         'SpinRateScalersCounts', 'SpinRateScalersCountsSigma',
                         'MajorNumbers', 'MeanCharge', 'Epoch', 'Epoch2D',
                         'String1D']
        names = list(self.cdf.keys())
        self.assertEqual(expectedNames, names)

    def testGetVarNum(self):
        self.assertEqual(0, self.cdf['ATC']._num())

    def testCDFIterator(self):
        expected = ['ATC', 'PhysRecNo', 'SpinNumbers', 'SectorNumbers',
                    'RateScalerNames', 'SectorRateScalerNames',
                    'SectorRateScalersCounts', 'SectorRateScalersCountsSigma',
                    'SpinRateScalersCounts', 'SpinRateScalersCountsSigma',
                    'MajorNumbers', 'MeanCharge', 'Epoch', 'Epoch2D',
                    'String1D']
        self.assertEqual(expected, [i for i in self.cdf])
        a = self.cdf.__iter__()
        a.send(None)
        self.assertEqual('SectorNumbers', a.send('SpinNumbers'))
        try:
            res = a.next()
        except AttributeError:
            res = next(a)
        self.assertEqual('RateScalerNames', res)

    def testRecCount(self):
        """Get number of records in a zVariable"""
        self.assertEqual(len(self.cdf['ATC']), 747)
        self.assertEqual(len(self.cdf['MeanCharge']), 100)
        self.assertEqual(len(self.cdf['SpinNumbers']), 1)

    def testMajority(self):
        """Get majority of the CDF"""
        self.assertFalse(self.cdf.col_major())

    def testgetndims(self):
        """Get number of dimensions in zVar"""
        expected = {'ATC': 0, 'PhysRecNo': 0, 'SpinNumbers': 1,
                    'SectorNumbers': 1, 'RateScalerNames': 1,
                    'SectorRateScalerNames': 1,
                    'SectorRateScalersCounts': 3, 'SectorRateScalersCountsSigma': 3,
                    'SpinRateScalersCounts': 2, 'SpinRateScalersCountsSigma': 2}
        for i in expected:
            self.assertEqual(self.cdf[i]._n_dims(), expected[i])

    def testgetdimsizes(self):
        """Get size of dimensions in zVar"""
        expected = {'ATC': [], 'PhysRecNo': [], 'SpinNumbers': [18],
                    'SectorNumbers': [32], 'RateScalerNames': [16],
                    'SectorRateScalerNames': [9],
                    'SectorRateScalersCounts': [18, 32, 9],
                    'SectorRateScalersCountsSigma': [18, 32, 9],
                    'SpinRateScalersCounts': [18, 16],
                    'SpinRateScalersCountsSigma': [18, 16]}
        for i in expected:
            self.assertEqual(self.cdf[i]._dim_sizes(), expected[i])

    def testgetrecvary(self):
        """Get record variance of zVar"""
        expected = {'ATC': True, 'PhysRecNo': True, 'SpinNumbers': False,
                    'SectorNumbers': False, 'RateScalerNames': False,
                    'SectorRateScalerNames': False,
                    'SectorRateScalersCounts': True,
                    'SectorRateScalersCountsSigma': True,
                    'SpinRateScalersCounts': True,
                    'SpinRateScalersCountsSigma': True}
        for i in expected:
            self.assertEqual(self.cdf[i].rv(), expected[i])

    def testHyperslices(self):
        slices = {'ATC': 1,
                  'PhysRecNo': slice(10, 2, -2),
                  'SpinNumbers': slice(2, None, 2),
                  'SectorRateScalersCounts': (slice(3, 6, None),
                                              slice(None, None, None),
                                              slice(None, None, None)),
                  'SpinRateScalersCounts': (Ellipsis, slice(-1, None, -1)),
                  'MeanCharge': (0, -1)
                  } #Slice objects indexed by variable
        #Expected results [dims, dimsizes, starts, counts, intervals, degen, rev]
        #indexed by variable
        expected = {'ATC': [1, [747], [1], [1], [1], [True], [False]],
                    'PhysRecNo': [1, [100], [4], [4], [2], [False], [True]],
                    'SpinNumbers': [2, [1, 18], [0, 2], [1, 8], [1, 2],
                                    [True, False], [False, False]],
                    'SectorRateScalersCounts': [4, [100, 18, 32, 9],
                                                [0, 3, 0, 0], [100, 3, 32, 9],
                                                [1, 1, 1, 1],
                                                [False, False, False, False],
                                                [False, False, False, False]],
                    'SpinRateScalersCounts': [3, [100, 18, 16],
                                              [0, 0, 0], [100, 18, 16],
                                              [1, 1, 1], [False, False, False],
                                              [False, False, True]],
                    'MeanCharge': [2, [100, 16], [0, 15], [1, 1], [1, 1],
                                   [True, True], [False, False]]
                    }
        for i in expected:
            zvar = self.cdf[i]
            sliced = cdf._pycdf._Hyperslice(zvar, slices[i])
            actual = (sliced.dims, sliced.dimsizes, sliced.starts,
                      sliced.counts.tolist(), sliced.intervals,
                      sliced.degen.tolist(), sliced.rev.tolist())
            self.assertEqual(tuple(expected[i]), actual,
                             '\n' + str(tuple(expected[i])) + '!=\n' +
                             str(actual) + ' variable ' + i)
        self.assertRaises(IndexError, cdf._pycdf._Hyperslice,
                          self.cdf['ATC'], (1, 2))
        self.assertRaises(IndexError, cdf._pycdf._Hyperslice,
                          self.cdf['ATC'], 800)
        self.assertRaises(IndexError, cdf._pycdf._Hyperslice,
                          self.cdf['ATC'], -1000)

    def testHyperslices2(self):
        """Additional checks: converting python slices to CDF counts, etc."""
        slices = {'ATC': Ellipsis,
                  } #Slice objects indexed by variable
        #Expected results [dims, dimsizes, starts, counts, intervals, degen, rev]
        #indexed by variable
        expected = {'ATC': [1, [747], [0], [747], [1], [False], [False]],
                    }
        for i in expected:
            zvar = self.cdf[i]
            sliced = cdf._pycdf._Hyperslice(zvar, slices[i])
            actual = (sliced.dims, sliced.dimsizes, sliced.starts,
                      sliced.counts, sliced.intervals, sliced.degen,
                      sliced.rev)
            self.assertEqual(tuple(expected[i]), actual,
                             '\n' + str(tuple(expected[i])) + '!=\n' +
                             str(actual) + ' variable ' + i)

    def testHypersliceExpand(self):
        """Expand a slice to store the data passed in"""
        zvar = self.cdf['PhysRecNo']
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, None, 1))
        self.assertEqual(100, sliced.counts[0])
        sliced.expand(list(range(110)))
        self.assertEqual(110, sliced.counts[0])
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, 100, 2))
        sliced.expand(list(range(110)))
        self.assertEqual(50, sliced.counts[0])

    def testHypersliceExpectedDims(self):
        """Find dimensions expected by a slice"""
        zvar = self.cdf['PhysRecNo']
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, None, 1))
        self.assertEqual([100], sliced.expected_dims())
        sliced.expand(list(range(110)))
        self.assertEqual([110], sliced.expected_dims())
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, 100, 2))
        sliced.expand(list(range(110)))
        self.assertEqual([50], sliced.expected_dims())

        zvar = self.cdf['SpinRateScalersCounts']
        sliced = cdf._pycdf._Hyperslice(zvar, (slice(None, None, None),
                                               slice(None, None, 2),
                                               slice(0, None, 3)))
        self.assertEqual([100, 9, 6], sliced.expected_dims())

        zvar = self.cdf['SpinNumbers']
        sliced = cdf._pycdf._Hyperslice(zvar, 2)
        self.assertEqual([1, 18], sliced.dimsizes)

    def testPackBuffer(self):
        """Pack a buffer with data"""
        zvar = self.cdf['PhysRecNo']
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, None, 1))
        buff = sliced.create_buffer()
        sliced.pack_buffer(buff, list(range(100)))
        result = [buff[i] for i in range(100)]
        self.assertEqual(list(range(100)), result)

        sliced = cdf._pycdf._Hyperslice(zvar, slice(None, None, -1))
        buff = sliced.create_buffer()
        sliced.pack_buffer(buff, list(range(100)))
        result = [buff[i] for i in range(100)]
        self.assertEqual(list(reversed(range(100))), result)

        zvar = self.cdf['SectorRateScalersCounts']
        sliced = cdf._pycdf._Hyperslice(zvar, (0, slice(0, 3, 2),
                                              slice(3, None, -1), 1))
        buff = sliced.create_buffer()
        data = [[1, 2, 3, 4],
                [5, 6, 7, 8]]
        expected = [[4, 3, 2, 1],
                    [8, 7, 6, 5]]
        sliced.pack_buffer(buff, data)
        self.assertEqual(expected[0], list(buff[0]))
        self.assertEqual(expected[1], list(buff[1]))

        sliced = cdf._pycdf._Hyperslice(zvar, (0, 1, 1, 1))
        buff = sliced.create_buffer()
        sliced.pack_buffer(buff, 10)
        self.assertEqual(10, buff.value)

        zvar = self.cdf['ATC']
        sliced = cdf._pycdf._Hyperslice(zvar, 10)
        buff = sliced.create_buffer()
        sliced.pack_buffer(buff, datetime.datetime(2009, 1, 1))
        self.assertEqual(list(buff), [63397987200.0, 0.0])

        zvar = self.cdf['SpinNumbers']
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, 3, None))
        buff = sliced.create_buffer()
        expected = [b'99', b'98', b'97']
        sliced.pack_buffer(buff, expected)
        for i in range(3):
            self.assertEqual(expected[i], buff[i].value)

    def testConvertArray(self):
        """Convert arrays to format of a slice"""
        sliced = cdf._pycdf._Hyperslice(self.cdf['SpinRateScalersCounts'],
                                        (slice(0, 2, 1), slice(5, 3, -1),
                                         slice(1, 3, 1)))
        input = [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]
        expected = [[[3, 4], [1, 2]], [[7, 8], [5, 6]]]
        output = sliced.convert_array(input)
        self.assertEqual(expected, output)

    def testCDFTypes(self):
        """Look up variable type from the CDF"""
        expected = {'ATC': cdf.const.CDF_EPOCH16,
                    'PhysRecNo': cdf.const.CDF_INT4,
                    'SpinNumbers': cdf.const.CDF_CHAR,
                    'MeanCharge': cdf.const.CDF_FLOAT,
                    'Epoch': cdf.const.CDF_EPOCH,
                    }
        for i in expected:
            self.assertEqual(expected[i].value,
                             self.cdf[i].type())

    def testCTypes(self):
        """Look up ctype to match variable"""
        expected = {'ATC': (ctypes.c_double * 2),
                    'PhysRecNo': ctypes.c_int,
                    'SpinNumbers': ctypes.c_char * 2,
                    'MeanCharge': ctypes.c_float,
                    'Epoch': ctypes.c_double,
                    }
        for i in expected:
            self.assertEqual(expected[i],
                             self.cdf[i]._c_type())

    def testNPTypes(self):
        """Look up numpy type to match variable"""
        expected = {'ATC': numpy.dtype((numpy.float64, 2)),
                    'PhysRecNo': numpy.int32,
                    'SpinNumbers': numpy.dtype('S2'),
                    'MeanCharge': numpy.float32,
                    'Epoch': numpy.float64,
                    }
        for i in expected:
            self.assertEqual(expected[i],
                             self.cdf[i]._np_type())

    def testCreateReadArrays(self):
        """Create an array for reading from a slice"""
        slices = {'ATC': 1,
                  'PhysRecNo': slice(10, 2, -2),
                  'SpinNumbers': slice(2, None, 2),
                  'SectorRateScalersCounts': (slice(3, 6, None),
                                              slice(None, None, None),
                                              slice(None, None, None)),
                  'SpinRateScalersCounts': (Ellipsis, slice(-1, None, -1)),
                  } #Slice objects indexed by variable
        types = {'ATC': (ctypes.c_double * 2),
                 'PhysRecNo': (ctypes.c_int * 4),
                 'SpinNumbers': (ctypes.c_char * 2 * 8),
                 'SectorRateScalersCounts': (ctypes.c_float *
                                             9 * 32 * 3 * 100),
                 'SpinRateScalersCounts': (ctypes.c_float * 16 * 18 * 100),
                 } #constructors, build inside out
        for i in types:
            zvar = self.cdf[i]
            sliced = cdf._pycdf._Hyperslice(zvar, slices[i])
            actual = sliced.create_buffer().__class__
            self.assertEqual(types[i], actual)

    def testSubscriptVariable(self):
        """Refer to an array by subscript"""
        numpy.testing.assert_array_equal([3, 25, 47],
                                         self.cdf['PhysRecNo'][0:5:2])
        numpy.testing.assert_array_equal([1094, 1083, 1072, 1061],
                                         self.cdf['PhysRecNo'][-1:-5:-1])
        self.assertEqual(1.0,
                         self.cdf['SpinRateScalersCounts'][41, 2, 15])

    def testIncompleteSubscript(self):
        """Get data from a variable with a less-than-complete specification"""
        chargedata = self.cdf['MeanCharge'][0] #Should be the first record
        self.assertEqual(len(chargedata), 16)
        SpinRateScalersCounts = self.cdf['SpinRateScalersCounts'][...]
        self.assertEqual(100, len(SpinRateScalersCounts))

    def testEmptyResults(self):
        """Request an empty slice from a variable"""
        data = self.cdf['SectorRateScalersCounts'][1:1]
        self.assertEqual((0,18, 32, 9), data.shape)
        self.assertEqual(data.dtype, numpy.float32)

    def testReadEpochs(self):
        """Read an Epoch16 value"""
        expected = datetime.datetime(1998, 1, 15, 0, 0, 5, 334662)
        self.assertEqual(expected,
                         self.cdf['ATC'][0])
        expected = [datetime.datetime(1998, 1, 15, 0, 6, 48, 231),
                    datetime.datetime(1998, 1, 15, 0, 8, 30, 157015),
                    datetime.datetime(1998, 1, 15, 0, 10, 12, 313815),
                    datetime.datetime(1998, 1, 15, 0, 11, 54, 507400)
                    ]
        numpy.testing.assert_array_equal(
            expected, self.cdf['ATC'][4:8])

    def testReadEpoch8(self):
        """Read an Epoch value"""
        expected = datetime.datetime(1998, 1, 15, 0, 0, 0, 0)
        self.assertEqual(expected,
                         self.cdf['Epoch'][0])
        expected = [datetime.datetime(1998, 1, 15, 0, 4, 0, 0),
                    datetime.datetime(1998, 1, 15, 0, 5, 0, 0),
                    datetime.datetime(1998, 1, 15, 0, 6, 0, 0),
                    datetime.datetime(1998, 1, 15, 0, 7, 0, 0),
                    ]
        numpy.testing.assert_array_equal(
            expected, self.cdf['Epoch'][4:8])

    def testRead2DEpoch(self):
        """Read an Epoch16 variable with nonzero dimension"""
        expected = [[datetime.datetime(2000, 1, 1),
                     datetime.datetime(2000, 1, 1, 1)],
                    [datetime.datetime(2000, 1, 2),
                     datetime.datetime(2000, 1, 2, 1)],
                    [datetime.datetime(2000, 1, 3),
                     datetime.datetime(2000, 1, 3, 1)],
                    ]
        numpy.testing.assert_array_equal(expected, self.cdf['Epoch2D'][...])

    def testRead1DString(self):
        """Read a string with nonzero dimension"""
        expected = [['A', 'B', 'C'], ['D', 'E', 'F']]
        numpy.testing.assert_array_equal(expected, self.cdf['String1D'][...])

    def testnElems(self):
        """Read number of elements in a string variable"""
        self.assertEqual(2, self.cdf['SpinNumbers']._nelems())
        self.assertEqual(2, self.cdf['SectorNumbers']._nelems())

    def testSubscriptString(self):
        """Refer to a string array by subscript"""
        numpy.testing.assert_array_equal(
            ['0 ', '1 ', '2 ', '3 ', '4 ', '5 ', '6 ', '7 ',
             '8 ', '9 ', '10', '11', '12', '13', '14', '15',
             '16', '17'],
            self.cdf['SpinNumbers'][:])

    def testSubscriptIrregString(self):
        """Refer to a variable-length string array by subscript"""
        numpy.testing.assert_array_equal(
            ['H+', 'He+', 'He++', 'O<=+2', 'O>=+3', 'CN<=+2',
             'H0', 'He0', 'CNO0', 'CN>=+3', 'Ne-Si', 'S-Ni',
             '3He', 'D', 'Molecules', 'Others'],
            self.cdf['RateScalerNames'][:])

    def testGetAllNRV(self):
        """Get an entire non record varying variable"""
        numpy.testing.assert_array_equal(
            ['0 ', '1 ', '2 ', '3 ', '4 ', '5 ', '6 ', '7 ',
             '8 ', '9 ', '10', '11', '12', '13', '14', '15',
             '16', '17'],
            self.cdf['SpinNumbers'][...])

    def testGetsingleNRV(self):
        """Get single element of non record varying variable"""
        self.assertEqual('0 ',
                         self.cdf['SpinNumbers'][0])

    def testcharType(self):
        """Get a CDF_CHAR variable and make sure it's a string"""
        self.assertEqual(self.cdf['SpinNumbers'][0].dtype.kind,
                         'S')

    def testGetVarUnicode(self):
        name = 'ATC'
        try:
            name = unicode(name)
        except NameError: #Py3k, all strings are unicode
            pass
        self.assertEqual(cdf.Var(self.cdf, name).name(), 'ATC')

    def testGetAllData(self):
        data = self.cdf.copy()
        expected = ['ATC', 'Epoch', 'Epoch2D', 'MajorNumbers', 'MeanCharge',
                    'PhysRecNo',
                    'RateScalerNames', 'SectorNumbers',
                    'SectorRateScalerNames',
                    'SectorRateScalersCounts',
                    'SectorRateScalersCountsSigma',
                    'SpinNumbers',
                    'SpinRateScalersCounts',
                    'SpinRateScalersCountsSigma',
                    'String1D'
                    ]
        self.assertEqual(expected,
                         sorted([i for i in data]))

    def testCDFGetItem(self):
        """Look up a variable in CDF as a dict key"""
        result = self.cdf['ATC']
        self.assertEqual('ATC', result.name())
        self.assertRaises(KeyError, self.cdf.__getitem__, 'noexist')

    def testCDFlen(self):
        """length of CDF (number of zVars)"""
        result = len(self.cdf)
        self.assertEqual(15, result)

    def testReadonlyDefault(self):
        """CDF should be opened RO by default"""
        message = 'READ_ONLY_MODE: CDF is in read-only mode.'
        try:
            self.cdf['PhysRecNo']._delete()
        except cdf.CDFError:
            (type, val, traceback) = sys.exc_info()
            self.assertEqual(str(val), message)
        else:
            self.fail('Should have raised CDFError: '+ message)

    def testzEntryType(self):
        """Get the type of a zEntry"""
        names = ['DEPEND_0', 'VALIDMAX', ]
        numbers = [1, 0, ]
        types = [cdf.const.CDF_CHAR, cdf.const.CDF_EPOCH16, ]
        for (name, number, cdf_type) in zip(names, numbers, types):
            attribute = cdf.zAttr(self.cdf, name)
            actual_type = attribute.type(number)
            self.assertEqual(actual_type, cdf_type.value,
                             'zAttr ' + name + ' zEntry ' + str(number) +
                             ' ' + str(cdf_type.value) + ' != ' +
                             str(actual_type))
        self.assertEqual(cdf.const.CDF_CHAR.value,
                         self.cdf['PhysRecNo'].attrs.type('DEPEND_0'))

    def testgEntryType(self):
        """Get the type of a gEntry"""
        names = ['PI_name', 'Project', ]
        numbers = [0, 0, ]
        types = [cdf.const.CDF_CHAR, cdf.const.CDF_CHAR, ]
        for (name, number, cdf_type) in zip(names, numbers, types):
            attribute = cdf.gAttr(self.cdf, name)
            actual_type = attribute.type(number)
            self.assertEqual(actual_type, cdf_type.value,
                             'gAttr ' + name + ' gEntry ' + str(number) +
                             ' ' + str(cdf_type.value) + ' != ' +
                             str(actual_type))

    def testzEntryNelems(self):
        """Get number of elements of a zEntry"""
        names = ['DEPEND_0', 'VALIDMAX', ]
        numbers = [1, 0, ]
        nelems = [3, 1, ]
        for (name, number, nelem) in zip(names, numbers, nelems):
            attribute = cdf.zAttr(self.cdf, name)
            actual_number = attribute._entry_len(number)
            self.assertEqual(actual_number, nelem,
                             'zAttr ' + name + ' zEntry ' + str(number) +
                             ' ' + str(nelem) + ' != ' + str(actual_number))

    def testgEntryNelems(self):
        """Get number of elements of a gEntry"""
        names = ['PI_name', 'Project', ]
        numbers = [0, 0, ]
        nelems = [8, 44, ]
        for (name, number, nelem) in zip(names, numbers, nelems):
            attribute = cdf.gAttr(self.cdf, name)
            actual_number = attribute._entry_len(number)
            self.assertEqual(actual_number, nelem,
                             'gAttr ' + name + ' gEntry ' + str(number) +
                             ' ' + str(nelem) + ' != ' + str(actual_number))

    def testzAttrLen(self):
        """Get number of zEntries for a zAttr"""
        names = ['DEPEND_0', 'VALIDMAX', ]
        lengths = [6, 8, ]
        for (name, length) in zip(names, lengths):
            attribute = cdf.zAttr(self.cdf, name)
            actual_length = len(attribute)
            self.assertEqual(actual_length, length,
                             'zAttr ' + name +
                             ' ' + str(length) + ' != ' + str(actual_length))

    def testgAttrLen(self):
        """Get number of gEntries for a gAttr"""
        names = ['PI_name', 'Project', ]
        lengths = [1, 1, ]
        for (name, length) in zip(names, lengths):
            attribute = cdf.gAttr(self.cdf, name)
            actual_length = len(attribute)
            self.assertEqual(actual_length, length,
                             'gAttr ' + name +
                             ' ' + str(length) + ' != ' + str(actual_length))

    def testzEntryValue(self):
        """Get the value of a zEntry"""
        names = ['DEPEND_0', 'VALIDMAX', ]
        numbers = [1, 0]
        values = ['ATC', datetime.datetime(2009, 1, 1)]
        for (name, number, value) in zip(names, numbers, values):
            attribute = cdf.zAttr(self.cdf, name)
            entry = attribute._get_entry(number)
            self.assertEqual(value, entry)

    def testzEntryEpoch(self):
        """Get the value of an Epoch zEntry"""
        expected = datetime.datetime(2008, 12, 31, 23, 59, 59, 999000)
        actual = self.cdf['Epoch'].attrs['VALIDMAX']
        self.assertEqual(expected, actual)

    def testgEntryValue(self):
        """Get the value of a gEntry"""
        names = ['Project', 'TEXT', ]
        numbers = [0, 0, ]
        values = ['ISTP>International Solar-Terrestrial Physics',
                  'Polar CAMMICE Level One intermediate files', ]
        for (name, number, value) in zip(names, numbers, values):
            attribute = cdf.gAttr(self.cdf, name)
            entry = attribute._get_entry(number)
            self.assertEqual(value, entry)

    def testzAttrSlice(self):
        """Slice a zAttribute"""
        entries = cdf.zAttr(self.cdf, 'DEPEND_0')[6:10:2]
        values = [entry for entry in entries]
        self.assertEqual(['ATC', 'ATC'], values)

    def testgAttrSlice(self):
        """Slice a gAttribute"""
        entry = cdf.gAttr(self.cdf, 'Instrument_type')[0]
        value = entry
        self.assertEqual('Particles (space)', value)

    def testzAttrMaxIdx(self):
        """Find max index of a zAttr"""
        self.assertEqual(11,
            cdf.zAttr(self.cdf, 'DEPEND_0').max_idx())

    def testgAttrMaxIdx(self):
        """Find max index of a gAttr"""
        self.assertEqual(0,
            cdf.gAttr(self.cdf, 'Mission_group').max_idx())
        self.assertEqual(-1,
            cdf.gAttr(self.cdf, 'HTTP_LINK').max_idx())

    def testzEntryExists(self):
        """Checks for existence of a zEntry"""
        attribute = cdf.zAttr(self.cdf, 'DEPEND_0')
        self.assertFalse(attribute.has_entry(0))
        self.assertTrue(attribute.has_entry(6))

    def testGetBadzEntry(self):
        message = "'foobar: NO_SUCH_ATTR: Named attribute not found in this CDF.'"
        try:
            attrib = self.cdf['ATC'].attrs['foobar']
        except KeyError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should raise KeyError: ' + message)

        message = "'DEPEND_0: no such attribute for variable ATC'"
        try:
            attrib = self.cdf['ATC'].attrs['DEPEND_0']
        except KeyError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should raise KeyError: ' + message)

    def testgEntryExists(self):
        """Checks for existence of a gEntry"""
        attribute = cdf.gAttr(self.cdf, 'TEXT')
        self.assertTrue(attribute.has_entry(0))
        self.assertFalse(attribute.has_entry(6))

    def testzAttrIterator(self):
        """Iterate through all zEntries of a zAttr"""
        expected = ['ATC'] * 6
        attrib = cdf.zAttr(self.cdf, 'DEPEND_0')
        self.assertEqual(expected, [i for i in attrib])
        a = attrib.__iter__()
        a.send(None)
        res = a.send(1)
        self.assertEqual('ATC', res)
        try:
            res = a.next()
        except AttributeError:
            res = next(a)
        self.assertEqual('ATC', res)

    def testzAttrRevIterator(self):
        """Iterate backwards through all zEntries of a zAttr"""
        expected = ['ATC'] * 6
        attrib = cdf.zAttr(self.cdf, 'DEPEND_0')
        output = [entry for entry in reversed(attrib)]
        self.assertEqual(expected, output)

    def testgAttrIterator(self):
        """Iterate through all gEntries of a gAttr"""
        expected = ['ISTP>International Solar-Terrestrial Physics']
        attrib = cdf.gAttr(self.cdf, 'Project')
        self.assertEqual(expected, [i for i in attrib])

    def testzAttribList(self):
        """Get a zAttrib from the list on the CDF"""
        attrlist = cdf.zAttrList(self.cdf['PhysRecNo'])
        self.assertEqual(attrlist['DEPEND_0'], 'ATC')
        self.assertRaises(KeyError, attrlist.__getitem__, 'Data_type')

    def testgAttribList(self):
        """Get a gAttrib from the list on the CDF"""
        attrlist = cdf.gAttrList(self.cdf)
        self.assertEqual(attrlist['Data_type'][0],
                         'H0>High Time Resolution')
        self.assertRaises(KeyError, attrlist.__getitem__, 'DEPEND_0')

    def testAttribScope(self):
        """Get the variable/global scope of an attribute"""
        self.assertFalse(cdf.gAttr(self.cdf, 'CATDESC').global_scope())
        self.assertFalse(cdf.gAttr(self.cdf, 'DEPEND_0').global_scope())
        self.assertTrue(cdf.gAttr(self.cdf, 'Data_type').global_scope())

    def testAttribNumber(self):
        """Get the number of an attribute"""
        self.assertEqual(25, cdf.zAttr(self.cdf, 'CATDESC').number())
        self.assertEqual(26, cdf.zAttr(self.cdf, 'DEPEND_0').number())
        self.assertEqual(3, cdf.gAttr(self.cdf, 'Data_type').number())

    def testzAttribListLen(self):
        """Number of zAttrib for a zVar"""
        self.assertEqual(10, len(cdf.zAttrList(self.cdf['ATC'])))
        self.assertEqual(8, len(cdf.zAttrList(self.cdf['PhysRecNo'])))

    def testgAttribListLen(self):
        """Number of gAttrib in a CDF"""
        self.assertEqual(25, len(cdf.gAttrList(self.cdf)))

    def testzAttribsonVar(self):
        """Check zAttribs as an attribute of Var"""
        self.assertEqual(10, len(self.cdf['ATC'].attrs))
        self.assertEqual(8, len(self.cdf['PhysRecNo'].attrs))

    def testgAttribsonCDF(self):
        """Check gAttribs as an attribute of CDF"""
        self.assertEqual(25, len(self.cdf.attrs))

    def testzAttribListIt(self):
        """Iterate over keys in a zAttrList"""
        attrlist = cdf.zAttrList(self.cdf['PhysRecNo'])
        self.assertEqual(['CATDESC', 'DEPEND_0', 'FIELDNAM', 'FILLVAL',
                          'FORMAT', 'VALIDMIN', 'VALIDMAX', 'VAR_TYPE'],
                         list(attrlist))

    def testgAttribListIt(self):
        """Iterate over keys in a gAttrList"""
        attrlist = cdf.gAttrList(self.cdf)
        self.assertEqual(['Project', 'Source_name', 'Discipline',
                          'Data_type', 'Descriptor',
                          'File_naming_convention', 'Data_version',
                          'PI_name', 'PI_affiliation', 'TEXT',
                          'Instrument_type', 'Mission_group',
                          'Logical_source',
                          'Logical_file_id', 'Logical_source_description',
                          'Time_resolution', 'Rules_of_use', 'Generated_by',
                          'Generation_date', 'Acknowledgement', 'MODS',
                          'ADID_ref', 'LINK_TEXT', 'LINK_TITLE',
                          'HTTP_LINK',
                          ],
                         list(attrlist))

    def testzAttribListCopy(self):
        """Make a copy of a zAttr list"""
        attrs = self.cdf['PhysRecNo'].attrs
        attrcopy = attrs.copy()
        self.assertEqual(attrs, attrcopy)
        self.assertFalse(attrs is attrcopy)

    def testgAttribListCopy(self):
        """Copy a gAttr list"""
        attrs = self.cdf.attrs
        attrcopy = attrs.copy()
        for key in attrs:
            self.assertEqual(attrs[key][:], attrcopy[key])
            self.assertFalse(attrs[key] is attrcopy[key])

    def testgAttribListSame(self):
        """Are two instances of attributes from a CDF the same?"""
        attrs = self.cdf.attrs
        self.assertTrue(attrs is self.cdf.attrs)

    def testzAttribListSame(self):
        """Are two instances of attributes from a zVar the same?"""
        zv = self.cdf['PhysRecNo']
        attrs = zv.attrs
        self.assertTrue(attrs is zv.attrs)

    def testzVarCopy(self):
        """Make a copy of an entire zVar"""
        zvar = self.cdf['PhysRecNo']
        zvarcopy = zvar.copy()
        self.assertNotEqual(zvar, zvarcopy)
        for i in range(len(zvar)):
            self.assertEqual(zvar[i], zvarcopy[i])
        for i in zvarcopy.attrs:
            self.assertEqual(zvar.attrs[i], zvarcopy.attrs[i])
        numpy.testing.assert_array_equal(zvar[...], zvarcopy[...])

    def testCDFCopy(self):
        """Make a copy of an entire CDF"""
        cdfcopy = self.cdf.copy()
        self.assertNotEqual(cdfcopy, self.cdf)
        for key in self.cdf:
            numpy.testing.assert_array_equal(self.cdf[key][...], cdfcopy[key])
            self.assertNotEqual(self.cdf[key], cdfcopy[key])
        for key in self.cdf.attrs:
            self.assertEqual(self.cdf.attrs[key][:], cdfcopy.attrs[key])
            self.assertNotEqual(self.cdf.attrs[key], cdfcopy.attrs[key])

    def testSliceCDFCopy(self):
        """Slice a copy of a CDF"""
        cdfcopy = self.cdf.copy()
        self.assertEqual([3, 25, 47],
                         cdfcopy['PhysRecNo'][0:5:2])
        self.assertEqual([1094, 1083, 1072, 1061],
                         cdfcopy['PhysRecNo'][-1:-5:-1])
        self.assertEqual(1.0,
                         cdfcopy['SpinRateScalersCounts'][41, 2, 15])

    def testVarString(self):
        """Convert a variable to a string representation"""
        expected = {'String1D': 'CDF_CHAR*1 [2, 3]', 'SectorRateScalerNames': 'CDF_CHAR*9 [9] NRV', 'PhysRecNo': 'CDF_INT4 [100]', 'RateScalerNames': 'CDF_CHAR*9 [16] NRV', 'SpinRateScalersCountsSigma': 'CDF_FLOAT [100, 18, 16]', 'SectorRateScalersCountsSigma': 'CDF_FLOAT [100, 18, 32, 9]', 'SpinRateScalersCounts': 'CDF_FLOAT [100, 18, 16]', 'SpinNumbers': 'CDF_CHAR*2 [18] NRV', 'Epoch': 'CDF_EPOCH [11]', 'SectorRateScalersCounts': 'CDF_FLOAT [100, 18, 32, 9]', 'MeanCharge': 'CDF_FLOAT [100, 16]', 'SectorNumbers': 'CDF_CHAR*2 [32] NRV', 'MajorNumbers': 'CDF_CHAR*2 [11] NRV', 'Epoch2D': 'CDF_EPOCH16 [3, 2]', 'ATC': 'CDF_EPOCH16 [747]'}
        actual = dict([(varname, str(zVar))
                       for (varname, zVar) in self.cdf.items()])
        self.assertEqual(expected, actual)

    def testCDFString(self):
        """Convert a CDF to a string representation"""
        expected = 'ATC: CDF_EPOCH16 [747]\nPhysRecNo: CDF_INT4 [100]\nSpinNumbers: CDF_CHAR*2 [18] NRV\nSectorNumbers: CDF_CHAR*2 [32] NRV\nRateScalerNames: CDF_CHAR*9 [16] NRV\nSectorRateScalerNames: CDF_CHAR*9 [9] NRV\nSectorRateScalersCounts: CDF_FLOAT [100, 18, 32, 9]\nSectorRateScalersCountsSigma: CDF_FLOAT [100, 18, 32, 9]\nSpinRateScalersCounts: CDF_FLOAT [100, 18, 16]\nSpinRateScalersCountsSigma: CDF_FLOAT [100, 18, 16]\nMajorNumbers: CDF_CHAR*2 [11] NRV\nMeanCharge: CDF_FLOAT [100, 16]\nEpoch: CDF_EPOCH [11]\nEpoch2D: CDF_EPOCH16 [3, 2]\nString1D: CDF_CHAR*1 [2, 3]'
        actual = str(self.cdf)
        self.assertEqual(expected, actual)

    def testgAttrListString(self):
        """Convert a list of gattributes to a string"""
        expected = 'Project: ISTP>International Solar-Terrestrial Physics [CDF_CHAR]\nSource_name: POLAR>POLAR PLASMA LABORATORY [CDF_CHAR]\nDiscipline: Space Physics>Magnetospheric Science [CDF_CHAR]\nData_type: H0>High Time Resolution [CDF_CHAR]\nDescriptor: CAM>Charge and Mass Magnetospheric Ion Composition Experiment [CDF_CHAR]\nFile_naming_convention: source_datatype_descriptor [CDF_CHAR]\nData_version: 1 [CDF_CHAR]\nPI_name: T. Fritz [CDF_CHAR]\nPI_affiliation: Boston University [CDF_CHAR]\nTEXT: Polar CAMMICE Level One intermediate files [CDF_CHAR]\n      another entry to simply pad it out [CDF_CHAR]\nInstrument_type: Particles (space) [CDF_CHAR]\nMission_group: Polar [CDF_CHAR]\nLogical_source: polar_h0_cam [CDF_CHAR]\nLogical_file_id: polar_h0_cam_00000000_v01 [CDF_CHAR]\nLogical_source_description: PO_L1_CAM [CDF_CHAR]\nTime_resolution: millisecond [CDF_CHAR]\nRules_of_use: \nGenerated_by: BU Energetic Particle Group [CDF_CHAR]\nGeneration_date: 20100625 [CDF_CHAR]\nAcknowledgement: \nMODS: \nADID_ref: NSSD0241 [CDF_CHAR]\nLINK_TEXT: \nLINK_TITLE: \nHTTP_LINK: '
        self.assertEqual(expected, str(self.cdf.attrs))
        self.assertEqual('<gAttrList:\n' + expected + '\n>',
                         repr(self.cdf.attrs))

    def testzAttrListString(self):
        """Convert a list of zAttributes to a string"""
        expected = {'String1D': '', 'SectorRateScalerNames': 'CATDESC: Species found in each per-sector rate scaler [CDF_CHAR]\nFIELDNAM: Sector Rate Scaler Names [CDF_CHAR]\nFORMAT: A10 [CDF_CHAR]\nVAR_TYPE: metadata [CDF_CHAR]\nVAR_NOTES: From J. Fennell revision 1997/02/28 [CDF_CHAR]', 'PhysRecNo': 'CATDESC: LZ record number for first major in this master [CDF_CHAR]\nDEPEND_0: ATC [CDF_CHAR]\nFIELDNAM: physical record [CDF_CHAR]\nFILLVAL: -2147483648 [CDF_INT4]\nFORMAT: I8 [CDF_CHAR]\nVALIDMIN: 0 [CDF_INT4]\nVALIDMAX: 20000 [CDF_INT4]\nVAR_TYPE: metadata [CDF_CHAR]', 'RateScalerNames': 'CATDESC: Species found in each rate scaler [CDF_CHAR]\nFIELDNAM: Rate Scaler Names [CDF_CHAR]\nFORMAT: A10 [CDF_CHAR]\nVAR_TYPE: metadata [CDF_CHAR]\nVAR_NOTES: From J. Fennell revision 1997/02/28 [CDF_CHAR]', 'SpinRateScalersCountsSigma': 'CATDESC: Uncertainty in counts in the per-spin rate scalers. [CDF_CHAR]\nDEPEND_0: ATC [CDF_CHAR]\nFIELDNAM: Spin rate scaler uncertainty [CDF_CHAR]\nFILLVAL: -9.99999984824e+30 [CDF_FLOAT]\nFORMAT: E6.2 [CDF_CHAR]\nLABL_PTR_1: SpinNumbers [CDF_CHAR]\nLABL_PTR_2: RateScalerNames [CDF_CHAR]\nVALIDMIN: 0.0 [CDF_FLOAT]\nVALIDMAX: 1000000.0 [CDF_FLOAT]\nVAR_TYPE: support_data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nVAR_NOTES: Combines uncertainty from RS compression and Poisson stats. Total counts accumulated over one spin (divide by SectorLength*32-58ms for rate). [CDF_CHAR]', 'SectorRateScalersCountsSigma': 'CATDESC: Uncertainty in counts in the per-sector rate scalers. [CDF_CHAR]\nDEPEND_0: ATC [CDF_CHAR]\nFIELDNAM: Sector rate scaler uncertainty [CDF_CHAR]\nFILLVAL: -9.99999984824e+30 [CDF_FLOAT]\nFORMAT: E12.2 [CDF_CHAR]\nLABL_PTR_1: SpinNumbers [CDF_CHAR]\nLABL_PTR_2: SectorNumbers [CDF_CHAR]\nLABL_PTR_3: SectorRateScalerNames [CDF_CHAR]\nVALIDMIN: 0.0 [CDF_FLOAT]\nVALIDMAX: 9.99999995904e+11 [CDF_FLOAT]\nVAR_TYPE: support_data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nVAR_NOTES: Combines uncertainty from RS compression and Poisson stats. Total counts accumulated over one sector (divide by SectorLength for rate. Subtract 58ms for sector 0) [CDF_CHAR]', 'SpinRateScalersCounts': 'CATDESC: Counts in the per-spin rate scalers [CDF_CHAR]\nDEPEND_0: ATC [CDF_CHAR]\nDEPEND_1: SpinNumbers [CDF_CHAR]\nDEPEND_2: RateScalerNames [CDF_CHAR]\nDISPLAY_TYPE: time_series [CDF_CHAR]\nFIELDNAM: Spin rate scaler number counts [CDF_CHAR]\nFILLVAL: -9.99999984824e+30 [CDF_FLOAT]\nFORMAT: E6.2 [CDF_CHAR]\nLABL_PTR_1: SpinNumbers [CDF_CHAR]\nLABL_PTR_2: RateScalerNames [CDF_CHAR]\nVALIDMIN: 0.0 [CDF_FLOAT]\nVALIDMAX: 1000000.0 [CDF_FLOAT]\nVAR_TYPE: data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nVAR_NOTES: Total counts accumulated over one spin (divide by SectorLength*32-58ms for rate). [CDF_CHAR]\nDELTA_PLUS_VAR: SpinRateScalersCountsSigma [CDF_CHAR]\nDELTA_MINUS_VAR: SpinRateScalersCountsSigma [CDF_CHAR]', 'SpinNumbers': 'CATDESC: Spin number within the TM Master [CDF_CHAR]\nFIELDNAM: Spin Number [CDF_CHAR]\nFORMAT: A3 [CDF_CHAR]\nVAR_TYPE: metadata [CDF_CHAR]', 'Epoch': 'CATDESC: Standard CDF Epoch time (8 byte) [CDF_CHAR]\nFIELDNAM: UTC [CDF_CHAR]\nFILLVAL: 9999-12-31 23:59:59.999000 [CDF_EPOCH]\nVALIDMIN: 1996-01-01 00:00:00 [CDF_EPOCH]\nVALIDMAX: 2008-12-31 23:59:59.999000 [CDF_EPOCH]\nVAR_TYPE: support_data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nMONOTON: INCREASE [CDF_CHAR]', 'SectorRateScalersCounts': 'CATDESC: Counts in the per-sector rate scalers [CDF_CHAR]\nDEPEND_0: ATC [CDF_CHAR]\nDEPEND_1: SpinNumbers [CDF_CHAR]\nDEPEND_2: SectorNumbers [CDF_CHAR]\nDEPEND_3: SectorRateScalerNames [CDF_CHAR]\nDISPLAY_TYPE: time_series [CDF_CHAR]\nFIELDNAM: Sector rate scaler counts [CDF_CHAR]\nFILLVAL: -9.99999984824e+30 [CDF_FLOAT]\nFORMAT: E6.2 [CDF_CHAR]\nLABL_PTR_1: SpinNumbers [CDF_CHAR]\nLABL_PTR_2: SectorNumbers [CDF_CHAR]\nLABL_PTR_3: SectorRateScalerNames [CDF_CHAR]\nVALIDMIN: 0.0 [CDF_FLOAT]\nVALIDMAX: 1000000.0 [CDF_FLOAT]\nVAR_TYPE: data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nVAR_NOTES: Total counts accumulated over one sector (divide by SectorLength for rate, subtracting 58ms for sector 0). [CDF_CHAR]\nDELTA_PLUS_VAR: SectorRateScalersCountsSigma [CDF_CHAR]\nDELTA_MINUS_VAR: SectorRateScalersCountsSigma [CDF_CHAR]', 'MeanCharge': 'CATDESC: Mean charge state [CDF_CHAR]\nDEPEND_0: ATC [CDF_CHAR]\nFIELDNAM: avg charge [CDF_CHAR]\nFILLVAL: -9.99999984824e+30 [CDF_FLOAT]\nFORMAT: F3.1 [CDF_CHAR]\nLABL_PTR_1: RateScalerNames [CDF_CHAR]\nUNITS: e [CDF_CHAR]\nVALIDMIN: 1.0 [CDF_FLOAT]\nVALIDMAX: 8.0 [CDF_FLOAT]\nVAR_TYPE: support_data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nVAR_NOTES: Mean charge state in each rate scaler. For the ENTIRE master period (i.e. summed over all energies), based on COUNTS. [CDF_CHAR]', 'SectorNumbers': 'CATDESC: Data accumulation sector number within the spin [CDF_CHAR]\nFIELDNAM: Sector Number [CDF_CHAR]\nFORMAT: A3 [CDF_CHAR]\nVAR_TYPE: metadata [CDF_CHAR]', 'MajorNumbers': 'CATDESC: major frame number within the TM Master [CDF_CHAR]\nFIELDNAM: Major Frame Number [CDF_CHAR]\nFORMAT: A2 [CDF_CHAR]\nVAR_TYPE: metadata [CDF_CHAR]', 'Epoch2D': '', 'ATC': 'CATDESC: Absolute Time Code [CDF_CHAR]\nFIELDNAM: ATC [CDF_CHAR]\nFILLVAL: 9999-12-31 23:59:59.999999 [CDF_EPOCH16]\nLABLAXIS: UT [CDF_CHAR]\nVALIDMIN: 1996-01-01 00:00:00 [CDF_EPOCH16]\nVALIDMAX: 2009-01-01 00:00:00 [CDF_EPOCH16]\nVAR_TYPE: support_data [CDF_CHAR]\nSCALETYP: linear [CDF_CHAR]\nVAR_NOTES: Time when data in this master started accumulating. [CDF_CHAR]\nMONOTON: INCREASE [CDF_CHAR]'}
        actual = dict([(varname, str(zVar.attrs))
                        for (varname, zVar) in self.cdf.items()])
        #Py3k and 2k display the floats differently,
        #as do numpy and Python
        ignorelist = ('SectorRateScalersCountsSigma',
                      'SpinRateScalersCountsSigma',
                      'SpinRateScalersCounts',
                      'SectorRateScalersCounts',
                      'MeanCharge',
                      )
        for k in ignorelist:
            del expected[k]
            del actual[k]
        for k in expected:
            if expected[k] != actual[k]:
                print('Difference in ' + k)
                print('Expected: ' + expected[k])
                print('Actual: ' + actual[k])
        self.assertEqual(expected, actual)
        for idx in expected:
            expected[idx] = '<zAttrList:\n' + expected[idx] + '\n>'
        actual = dict([(varname, repr(zVar.attrs))
                        for (varname, zVar) in self.cdf.items()])
        for k in ignorelist:
            del actual[k]
        self.assertEqual(expected, actual)

    def testReadClosedCDF(self):
        """Read a CDF that has been closed"""
        self.cdf.close()
        try:
            keylist = list(self.cdf.keys())
        except cdf.CDFError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(const.BAD_CDF_ID, v.status)
        else:
            self.fail('Should raise CDFError: BAD_CDF_ID')
        finally:
            self.cdf = cdf.CDF(self.testfile) #keep tearDown from failing

    def testStrClosedCDF(self):
        """String representation of CDF that has been closed"""
        self.cdf.close()
        cdflabel = str(self.cdf)
        try:
            self.assertEqual('Closed CDF', cdflabel[0:10])
            self.assertEqual(self.testbase, cdflabel[-len(self.testbase):])
        finally:
            self.cdf = cdf.CDF(self.testfile) #keep tearDown from failing

    def testStrClosedVar(self):
        """String representation of zVar in CDF that has been closed"""
        zVar = self.cdf['ATC']
        self.cdf.close()
        varlabel = str(zVar)
        try:
            self.assertEqual('zVar "ATC" in closed CDF ', varlabel[0:25])
            self.assertEqual(self.testbase, varlabel[-len(self.testbase):])
        finally:
            self.cdf = cdf.CDF(self.testfile) #keep tearDown from failing

    def testStrClosedAttribute(self):
        """String representation of attribute in CDF that has been closed"""
        attrib = self.cdf.attrs['Project']
        self.cdf.close()
        attrlabel = str(attrib)
        try:
            self.assertEqual('Attribute "Project" in closed CDF ', attrlabel[0:34])
            self.assertEqual(self.testbase, attrlabel[-len(self.testbase):])
        finally:
            self.cdf = cdf.CDF(self.testfile) #keep tearDown from failing

    def testStrClosedAttributeList(self):
        """String representation of attribute list in closed CDF"""
        al = self.cdf.attrs
        self.cdf.close()
        allabel = str(al)
        try:
            self.assertEqual('Attribute list in closed CDF ', allabel[0:29])
            self.assertEqual(self.testbase, allabel[-len(self.testbase):])
        finally:
            self.cdf = cdf.CDF(self.testfile) #keep tearDown from failing


class ReadColCDF(ColCDFTests):
    """Tests that read a column-major CDF, but do not modify it."""
    testbase = 'testc_ro.cdf'

    def __init__(self, *args, **kwargs):
        super(ReadColCDF, self).__init__(*args, **kwargs)
        #Unittest docs say 'the order in which the various test cases will be
        #run is determined by sorting the test function names with the built-in
        #cmp() function'
        testnames = [name for name in dir(self)
                     if name[0:4] == 'test' and callable(getattr(self,name))]
        self.last_test = max(testnames)

    def setUp(self):
        super(ReadColCDF, self).setUp()
        if not os.path.exists(self.testfile):
            shutil.copy(self.testmaster, self.testfile)
        self.cdf = cdf.CDF(self.testfile)

    def tearDown(self):
        self.cdf.close()
        del self.cdf
        if self._testMethodName == self.last_test:
            os.remove(self.testfile)
        super(ReadColCDF, self).tearDown()

    def testCMajority(self):
        """Get majority of the CDF"""
        self.assertTrue(self.cdf.col_major())

    def testCgetndims(self):
        """Get number of dimensions in zVar"""
        expected = {'ATC': 0, 'PhysRecNo': 0, 'SpinNumbers': 1,
                    'SectorNumbers': 1, 'RateScalerNames': 1,
                    'SectorRateScalerNames': 1,
                    'SectorRateScalersCounts': 3, 'SectorRateScalersCountsSigma': 3,
                    'SpinRateScalersCounts': 2, 'SpinRateScalersCountsSigma': 2}
        for i in expected:
            self.assertEqual(self.cdf[i]._n_dims(), expected[i])

    def testCgetdimsizes(self):
        """Get size of dimensions in zVar"""
        expected = {'ATC': [], 'PhysRecNo': [], 'SpinNumbers': [18],
                    'SectorNumbers': [32], 'RateScalerNames': [16],
                    'SectorRateScalerNames': [9],
                    'SectorRateScalersCounts': [18, 32, 9],
                    'SectorRateScalersCountsSigma': [18, 32, 9],
                    'SpinRateScalersCounts': [18, 16],
                    'SpinRateScalersCountsSigma': [18, 16]}
        for i in expected:
            self.assertEqual(self.cdf[i]._dim_sizes(), expected[i])

    def testColHyperslices(self):
        slices = {'ATC': 1,
                  'PhysRecNo': slice(10, 2, -2),
                  'SpinNumbers': slice(2, None, 2),
                  'SectorRateScalersCounts': (slice(3, 6, None),
                                              slice(None, None, None),
                                              slice(None, None, None)),
                  'SpinRateScalersCounts': (Ellipsis, slice(-1, None, -1)),
                  } #Slice objects indexed by variable
        #Expected results [dims, dimsizes, starts, counts, intervals, degen, rev]
        #indexed by variable
        expected = {'ATC': [1, [747], [1], [1], [1], [True], [False]],
                    'PhysRecNo': [1, [100], [4], [4], [2], [False], [True]],
                    'SpinNumbers': [2, [1, 18], [0, 2], [1, 8], [1, 2],
                                    [True, False], [False, False]],
                    'SectorRateScalersCounts': [4, [100, 18, 32, 9],
                                                [0, 3, 0, 0], [100, 3, 32, 9],
                                                [1, 1, 1, 1],
                                                [False, False, False, False],
                                                [False, False, False, False]],
                    'SpinRateScalersCounts': [3, [100, 18, 16],
                                              [0, 0, 0], [100, 18, 16],
                                              [1, 1, 1], [False, False, False],
                                              [False, False, True]],
                    }
        for i in expected:
            zvar = self.cdf[i]
            sliced = cdf._pycdf._Hyperslice(zvar, slices[i])
            actual = (sliced.dims, sliced.dimsizes, sliced.starts,
                      sliced.counts.tolist(), sliced.intervals,
                      sliced.degen.tolist(), sliced.rev.tolist())
            self.assertEqual(tuple(expected[i]), actual,
                             '\n' + str(tuple(expected[i])) + '!=\n' +
                             str(actual) + ' variable ' + i)

    def testColCreateReadArrays(self):
        """Create an array for reading from a slice"""
        slices = {'ATC': 1,
                  'PhysRecNo': slice(10, 2, -2),
                  'SpinNumbers': slice(2, None, 2),
                  'SectorRateScalersCounts': (slice(3, 6, None),
                                              slice(None, None, None),
                                              slice(None, None, None)),
                  'SpinRateScalersCounts': (Ellipsis, slice(-1, None, -1)),
                  } #Slice objects indexed by variable
        types = {'ATC': (ctypes.c_double * 2),
                 'PhysRecNo': (ctypes.c_int * 4),
                 'SpinNumbers': (ctypes.c_char * 2 * 8),
                 'SectorRateScalersCounts': (ctypes.c_float *
                                             3 * 32 * 9 * 100),
                 'SpinRateScalersCounts': (ctypes.c_float * 18 * 16 * 100),
                 } #constructors, build inside out
        for i in types:
            zvar = self.cdf[i]
            sliced = cdf._pycdf._Hyperslice(zvar, slices[i])
            actual = sliced.create_buffer().__class__
            self.assertEqual(types[i], actual)

    def testColSubscriptVariable(self):
        """Refer to an column-major array by subscript"""
        #NB: Should be in SAME order as row-major,
        #since converted in convert_array
        numpy.testing.assert_array_equal([3, 25, 47],
                                         self.cdf['PhysRecNo'][0:5:2])
        numpy.testing.assert_array_equal([1094, 1083, 1072, 1061],
                                         self.cdf['PhysRecNo'][-1:-5:-1])
        self.assertEqual(1.0,
                         self.cdf['SpinRateScalersCounts'][41, 2, 15])

    def testColSubscriptString(self):
        """Refer to a string array by subscript"""
        numpy.testing.assert_array_equal(['0 ', '1 ', '2 ', '3 ', '4 ', '5 ', '6 ', '7 ',
                                          '8 ', '9 ', '10', '11', '12', '13', '14', '15',
                                          '16', '17'],
                                         self.cdf['SpinNumbers'][:])

    def testColSubscriptIrregString(self):
        """Refer to a variable-length string array by subscript"""
        numpy.testing.assert_array_equal(['H+', 'He+', 'He++', 'O<=+2', 'O>=+3', 'CN<=+2',
                                          'H0', 'He0', 'CNO0', 'CN>=+3', 'Ne-Si', 'S-Ni',
                                          '3He', 'D', 'Molecules', 'Others'],
                                         self.cdf['RateScalerNames'][:])

    def testColReadEpochs(self):
        """Read an Epoch16 value"""
        expected = datetime.datetime(1998, 1, 15, 0, 0, 5, 334662)
        self.assertEqual(expected,
                         self.cdf['ATC'][0])
        expected = [datetime.datetime(1998, 1, 15, 0, 6, 48, 231),
                    datetime.datetime(1998, 1, 15, 0, 8, 30, 157015),
                    datetime.datetime(1998, 1, 15, 0, 10, 12, 313815),
                    datetime.datetime(1998, 1, 15, 0, 11, 54, 507400)
                    ]
        numpy.testing.assert_array_equal(expected,
                                         self.cdf['ATC'][4:8])

    def testContains(self):
        """See if variable exists in CDF"""
        self.assertTrue('ATC' in self.cdf)
        self.assertFalse('notthere' in self.cdf)

    def testColPackBuffer(self):
        """Pack a buffer with data"""
        zvar = self.cdf['PhysRecNo']
        sliced = cdf._pycdf._Hyperslice(zvar, slice(0, None, 1))
        buff = sliced.create_buffer()
        sliced.pack_buffer(buff, list(range(100)))
        result = [buff[i] for i in range(100)]
        self.assertEqual(list(range(100)), result)

        sliced = cdf._pycdf._Hyperslice(zvar, slice(None, None, -1))
        buff = sliced.create_buffer()
        sliced.pack_buffer(buff, list(range(100)))
        result = [buff[i] for i in range(100)]
        self.assertEqual(list(reversed(range(100))), result)

        zvar = self.cdf['SectorRateScalersCounts']
        sliced = cdf._pycdf._Hyperslice(zvar, (0, slice(0, 3, 2),
                                              slice(3, None, -1), 1))
        buff = sliced.create_buffer()
        data = [[1, 2, 3, 4],
                [5, 6, 7, 8]]
        expected = [[4, 8], [3, 7], [2, 6], [1, 5]]
        sliced.pack_buffer(buff, data)
        for i in range(4):
            self.assertEqual(expected[i], list(buff[i]))

    def testgetdimsizescol(self):
        """Get size of dimensions in zVar, column-major"""
        expected = {'ATC': [], 'PhysRecNo': [], 'SpinNumbers': [18],
                    'SectorNumbers': [32], 'RateScalerNames': [16],
                    'SectorRateScalerNames': [9],
                    'SectorRateScalersCounts': [18, 32, 9],
                    'SectorRateScalersCountsSigma': [18, 32, 9],
                    'SpinRateScalersCounts': [18, 16],
                    'SpinRateScalersCountsSigma': [18, 16]}
        for i in expected:
            self.assertEqual(self.cdf[i]._dim_sizes(), expected[i])


class ChangeCDF(CDFTests):
    """Tests that modify an existing CDF"""
    def __init__(self, *args):
        super(ChangeCDF, self).__init__(*args)

    def setUp(self):
        super(ChangeCDF, self).setUp()
        shutil.copy(self.testmaster, self.testfile)
        self.cdf = cdf.CDF(self.testfile)
        self.cdf.readonly(False)

    def tearDown(self):
        self.cdf.close()
        del self.cdf
        os.remove(self.testfile)
        super(ChangeCDF, self).tearDown()

    def testDeletezVar(self):
        """Delete a zVar"""
        self.cdf['PhysRecNo']._delete()
        self.assertRaises(KeyError, self.cdf.__getitem__, 'PhysRecNo')
        del self.cdf['ATC']
        self.assertFalse('ATC' in self.cdf)

    def testSaveCDF(self):
        """Save the CDF and make sure it's different"""
        self.cdf['PhysRecNo']._delete()
        self.cdf.save()
        self.assertNotEqual(self.calcDigest(self.testfile), self.expected_digest)
        self.assertTrue(self.cdf._handle)
        self.cdf['ATC']

    def testReadonlySettable(self):
        """Readonly mode should prevent changes"""
        self.cdf.readonly(True)
        self.assertTrue(self.cdf.readonly())
        message = 'READ_ONLY_MODE: CDF is in read-only mode.'
        try:
            self.cdf['PhysRecNo']._delete()
        except cdf.CDFError:
            (type, val, traceback) = sys.exc_info()
            self.assertEqual(str(val), message)
        else:
            self.fail('Should have raised CDFError: '+ message)

    def testReadonlyDisable(self):
        """Turn off readonly and try to change"""
        self.cdf.readonly(True)
        self.assertTrue(self.cdf.readonly())
        self.cdf.readonly(False)
        try:
            self.cdf['PhysRecNo']._delete()
        except:
            (type, val, traceback) = sys.exc_info()
            self.fail('Raised exception ' + str(val))

    def testWriteSubscripted(self):
        """Write data to a slice of a zVar"""
        expected = ['0 ', '1 ', '99', '3 ', '98', '5 ', '97', '7 ',
                    '8 ', '9 ']
        self.cdf['SpinNumbers'][2:7:2] = ['99', '98', '97']
        numpy.testing.assert_array_equal(
            expected, self.cdf['SpinNumbers'][0:10])

        expected = self.cdf['SectorRateScalersCounts'][...]
        expected[4][5][5][8:3:-1] = [101.0, 102.0, 103.0, 104.0, 105.0]
        self.cdf['SectorRateScalersCounts'][4, 5, 5, 8:3:-1] = \
            [101.0, 102.0, 103.0, 104.0, 105.0]
        numpy.testing.assert_array_equal(
            expected, self.cdf['SectorRateScalersCounts'][...])

        self.cdf['PhysRecNo'] = [1, 2, 3]
        numpy.testing.assert_array_equal(
            [1, 2, 3], self.cdf['PhysRecNo'][...])

    def testWriteExtend(self):
        """Write off the end of the variable"""
        additional = [2000 + i for i in range(20)]
        expected = self.cdf['PhysRecNo'][0:95].tolist() + additional
        self.cdf['PhysRecNo'][95:] = additional
        self.assertEqual(115, len(self.cdf['PhysRecNo']))
        numpy.testing.assert_array_equal(expected, self.cdf['PhysRecNo'][:])

    def testInsertRecord(self):
        """Insert a record into the middle of a variable"""
        PhysRecNoData = self.cdf['PhysRecNo'][...].tolist()
        PhysRecNoData[5:6] = [-1, -2, -3, -4]
        self.cdf['PhysRecNo'][5:6] = [-1, -2, -3, -4]
        self.assertEqual(103, len(self.cdf['PhysRecNo']))
        numpy.testing.assert_array_equal(
            PhysRecNoData, self.cdf['PhysRecNo'][...])

    def testWriteAndTruncate(self):
        """Write with insufficient data to fill all existing records"""
        expected = [-1 * i for i in range(20)]
        self.cdf['PhysRecNo'][:] = expected
        numpy.testing.assert_array_equal(
            expected, self.cdf['PhysRecNo'][:])

    def testWriteWrongSizeData(self):
        """Write with data sized or shaped differently from expected"""
        message = 'attempt to assign data of dimensions [3] ' + \
                  'to slice of dimensions [5]'
        try:
            self.cdf['SpinNumbers'][0:5] = [b'99', b'98', b'97']
        except ValueError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should have raised ValueError: ' + message)

        message = 'attempt to assign data of dimensions [2, 6, 2] ' + \
                  'to slice of dimensions [3, 6, 2]'
        try:
            self.cdf['SpinRateScalersCounts'][0:3, 12:, 0:4:2] = \
                [[[0, 1], [2, 3], [4, 5], [6, 7], [8, 9], [0, 1]],
                 [[2, 3], [4, 5], [6, 7], [8, 9], [0, 1], [2, 3]],
                 ]
        except ValueError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should have raised ValueError: ' + message)

    def testDeleteRecord(self):
        """Delete records from a variable"""
        oldlen = len(self.cdf['PhysRecNo'])
        PhysRecCopy = self.cdf['PhysRecNo'].copy()
        del self.cdf['PhysRecNo'][5]
        del PhysRecCopy[5]
        self.assertEqual(oldlen - 1, len(self.cdf['PhysRecNo']))
        numpy.testing.assert_array_equal(
            PhysRecCopy[0:15], self.cdf['PhysRecNo'][0:15])

        oldlen = len(self.cdf['ATC'])
        ATCCopy = self.cdf['ATC'].copy()
        del self.cdf['ATC'][0::2]
        self.assertEqual(int(oldlen / 2), len(self.cdf['ATC']))
        numpy.testing.assert_array_equal(ATCCopy[1::2], self.cdf['ATC'][...])

        message = 'Cannot delete records from non-record-varying variable.'
        try:
            del self.cdf['SpinNumbers'][0]
        except:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(t, TypeError)
            self.assertEqual(str(v), message)
        else:
            self.fail('Should have raised TypeError: ' + message)

        oldlen = len(self.cdf['SectorRateScalersCounts'])
        SectorRateScalersCountsCopy = \
                                    self.cdf['SectorRateScalersCounts'].copy()
        del SectorRateScalersCountsCopy[-1:-5:-1]
        del self.cdf['SectorRateScalersCounts'][-1:-5:-1]
        self.assertEqual(oldlen - 4, len(self.cdf['SectorRateScalersCounts']))
        numpy.testing.assert_array_equal(
            SectorRateScalersCountsCopy[...],
            self.cdf['SectorRateScalersCounts'][...])

        oldlen = len(self.cdf['SectorRateScalersCounts'])
        del self.cdf['SectorRateScalersCounts'][-1:-5]
        self.assertEqual(oldlen, len(self.cdf['SectorRateScalersCounts']))

        message = 'Can only delete entire records.'
        try:
            del self.cdf['SpinRateScalersCounts'][0, 12, 0:5]
        except:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(t, TypeError)
            self.assertEqual(str(v), message)
        else:
            self.fail('Should have raised TypeError: ' + message)

    def testRenameVar(self):
        """Rename a variable"""
        zvar = self.cdf['PhysRecNo']
        zvardata = zvar[...]
        zvar.rename('foobar')
        numpy.testing.assert_array_equal(
            zvardata, self.cdf['foobar'][...])
        try:
            zvar = self.cdf['PhysRecNo']
        except KeyError:
            pass
        else:
            self.fail('Should have raised KeyError')

        try:
            zvar.rename('a' * 300)
        except cdf.CDFError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(v.status, cdf.const.BAD_VAR_NAME)
        else:
            self.fail('Should have raised CDFError')

    def testChangezEntry(self):
        """Write new or changed zEntry"""
        zvar = self.cdf['PhysRecNo']
        zvar.attrs['DEPEND_0'] = 'foobar'
        self.assertEqual('foobar', zvar.attrs['DEPEND_0'])
        self.assertEqual(const.CDF_CHAR.value,
                         cdf.zAttr(self.cdf,
                                   'DEPEND_0').type(zvar._num()))

        zvar.attrs['FILLVAL'] = [0, 1]
        numpy.testing.assert_array_equal([0,1], zvar.attrs['FILLVAL'])
        self.assertEqual(const.CDF_INT4.value,
                         cdf.zAttr(self.cdf,
                                   'FILLVAL').type(zvar._num()))

        message = 'Entry strings must be scalar.'
        try:
            zvar.attrs['CATDESC'] = ['hi', 'there']
        except ValueError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should have raised ValueError: ' + message)

        message = 'Entries must be scalar or 1D.'
        try:
            zvar.attrs['FILLVAL'] = [[1, 2], [3, 4]]
        except ValueError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(message, str(v))
        else:
            self.fail('Should have raised ValueError: ' + message)

    def testNewzAttr(self):
        """Write a zEntry for a zAttribute that doesn't exist"""
        zvar = self.cdf['PhysRecNo']
        zvar.attrs['NEW_ATTRIBUTE'] = 1
        self.assertTrue('NEW_ATTRIBUTE' in zvar.attrs)
        self.assertEqual(1, zvar.attrs['NEW_ATTRIBUTE'])
        self.assertEqual(const.CDF_INT4.value,
                         cdf.zAttr(self.cdf,
                                   'NEW_ATTRIBUTE').type(zvar._num()))

        zvar.attrs['NEW_ATTRIBUTE2'] = [1, 2]
        numpy.testing.assert_array_equal([1, 2], zvar.attrs['NEW_ATTRIBUTE2'])
        self.assertEqual(const.CDF_INT4.value,
                         cdf.zAttr(self.cdf,
                                   'NEW_ATTRIBUTE2').type(zvar._num()))

        zvar = self.cdf['SpinNumbers']
        zvar.attrs['NEW_ATTRIBUTE3'] = 1
        self.assertEqual(1, zvar.attrs['NEW_ATTRIBUTE3'])
        self.assertEqual(const.CDF_BYTE.value,
                         cdf.zAttr(self.cdf,
                                   'NEW_ATTRIBUTE3').type(zvar._num()))

    def testDelzAttr(self):
        """Delete a zEntry"""
        del self.cdf['PhysRecNo'].attrs['DEPEND_0']
        self.assertFalse('DEPEND_0' in self.cdf['PhysRecNo'].attrs)
        #Make sure attribute still exists
        attrib = cdf.zAttr(self.cdf, 'DEPEND_0')

        del self.cdf['SectorRateScalersCounts'].attrs['DEPEND_3']
        self.assertFalse('DEPEND_3' in
                         self.cdf['SectorRateScalersCounts'].attrs)
        try:
            attrib = cdf.zAttr(self.cdf, 'DEPEND_3')
        except cdf.CDFError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(const.NO_SUCH_ATTR, v.status)
        else:
            self.fail('Should have raised CDFError')

    def testChangegAttr(self):
        """Change an existing gEntry"""
        self.cdf.attrs['Project'][0] = 'not much'
        self.assertEqual('not much',
                         self.cdf.attrs['Project'][0])

        self.cdf.attrs['Source_name'][0] = datetime.datetime(2009, 1, 1)
        self.assertEqual([datetime.datetime(2009, 1, 1)],
                         self.cdf.attrs['Source_name'][:])

        self.cdf.attrs['Data_type'] = 'stuff'
        self.assertEqual('stuff',
                         self.cdf.attrs['Data_type'][0])
        self.cdf.attrs['Data_type'] = ['stuff', 'more stuff']
        self.assertEqual(['stuff', 'more stuff'],
                         self.cdf.attrs['Data_type'][:])

    def testNewgAttr(self):
        """Create a new gAttr by adding a gEntry"""
        self.cdf.attrs['new_attr'] = 1.5
        self.assertEqual([1.5],
                         self.cdf.attrs['new_attr'][:])

        self.cdf.attrs['new_attr2'] = []
        self.assertTrue('new_attr2' in self.cdf.attrs)
        self.cdf.attrs['new_attr2'][0:6:2] = [1, 2, 3]
        self.assertEqual([1, None, 2, None, 3],
                         self.cdf.attrs['new_attr2'][:])

        self.cdf.attrs['new_attr3'] = ['hello', 'there']
        self.assertEqual(['hello', 'there'],
                         self.cdf.attrs['new_attr3'][:])

    def testDelgAttr(self):
        """Delete a gEntry"""
        del self.cdf.attrs['TEXT'][0]
        self.assertTrue('TEXT' in self.cdf.attrs)

        del self.cdf.attrs['Project'][0]
        self.assertTrue('Project' in self.cdf.attrs)

        del self.cdf.attrs['PI_name']
        self.assertFalse('PI_name' in self.cdf.attrs)

    def testRenamegAttr(self):
        """Rename a gAttribute"""
        textcopy = self.cdf.attrs['TEXT'][:]
        self.cdf.attrs['TEXT'].rename('notTEXT')
        self.assertTrue('notTEXT' in self.cdf.attrs)
        self.assertFalse('TEXT' in self.cdf.attrs)
        self.assertEqual(textcopy, self.cdf.attrs['notTEXT'][:])

    def testRenamezAttr(self):
        """Rename a zAttribute"""
        prn_attrs = self.cdf['PhysRecNo'].attrs
        prn_depend = prn_attrs['DEPEND_0']
        mc_attrs = self.cdf['MeanCharge'].attrs
        mc_depend = mc_attrs['DEPEND_0']
        prn_attrs.rename('DEPEND_0', 'notDEPEND_0')
        self.assertTrue('notDEPEND_0' in prn_attrs)
        self.assertTrue('notDEPEND_0' in mc_attrs)
        self.assertFalse('DEPEND_0' in prn_attrs)
        self.assertFalse('DEPEND_0' in mc_attrs)
        self.assertEqual(prn_depend, prn_attrs['notDEPEND_0'])
        self.assertEqual(mc_depend, mc_attrs['notDEPEND_0'])

    def testChangegEntryType(self):
        """Change the type of a gEntry"""
        attrs = self.cdf.attrs
        attrs['new_attr'] = []
        attrs['new_attr'][0] = [ord('a'), ord('b'), ord('c')]
        attrs['new_attr'].type(0, const.CDF_CHAR)
        self.assertEqual(attrs['new_attr'][0], 'abc')
        try:
            attrs['new_attr'].type(0, const.CDF_INT2)
        except cdf.CDFError:
            (t, v, tb) = sys.exc_info()
            self.assertEqual(v.status, const.CANNOT_CHANGE)
        else:
            self.fail('Should have raised CDFError')

    def testChangezEntryType(self):
        """Change the type of a zEntry"""
        attrs = self.cdf['ATC'].attrs
        attrs['new_attr'] = [ord('a'), ord('b'), ord('c')]
        attrs.type('new_attr', const.CDF_CHAR)
        self.assertEqual(attrs['new_attr'], 'abc')
        self.assertEqual(const.CDF_CHAR.value,
                         attrs.type('new_attr'))

    def testgAttrNewEntry(self):
        """Create a new gEntry using Attr.new()"""
        attr = self.cdf.attrs['Project']
        #no type or number
        attr.new([0, 1, 2, 3])
        self.assertEqual(2, len(attr))
        numpy.testing.assert_array_equal([0, 1, 2, 3], attr[1])
        self.assertEqual(const.CDF_BYTE.value, attr.type(1))
        #explicit number
        attr.new('hello there', number=10)
        self.assertEqual(3, len(attr))
        self.assertEqual(10, attr.max_idx())
        self.assertEqual('hello there', attr[10])
        self.assertEqual(const.CDF_CHAR.value, attr.type(10))
        #explicit type and number
        attr.new(10, const.CDF_INT4, 15)
        self.assertEqual(4, len(attr))
        self.assertEqual(15, attr.max_idx())
        self.assertEqual(10, attr[15])
        self.assertEqual(const.CDF_INT4.value, attr.type(15))
        #explicit type
        attr.new([10, 11, 12, 13], const.CDF_REAL8)
        self.assertEqual(5, len(attr))
        numpy.testing.assert_array_equal([10.0, 11.0, 12.0, 13.0], attr[2])
        self.assertEqual(const.CDF_REAL8.value, attr.type(2))

    def testgAttrListNew(self):
        """Create a new gAttr and/or gEntry using gAttrList.new"""
        attrs = self.cdf.attrs
        attrs.new('new')
        self.assertTrue('new' in attrs)
        attrs.new('new2', [1, 2, 3])
        self.assertTrue('new2' in attrs)
        numpy.testing.assert_array_equal([1, 2, 3], attrs['new2'][0])
        attrs.new('new3', [1, 2, 3], const.CDF_INT4)
        self.assertTrue('new3' in attrs)
        numpy.testing.assert_array_equal([1, 2, 3], attrs['new3'][0])
        self.assertEqual(const.CDF_INT4.value, attrs['new3'].type(0))

    def testzAttrListNew(self):
        """Create a new zEntry using zAttrList.new"""
        attrs = self.cdf['ATC'].attrs
        attrs.new('new2', [1, 2, 3])
        self.assertTrue('new2' in attrs)
        numpy.testing.assert_array_equal([1, 2, 3], attrs['new2'])
        attrs.new('new3', [1, 2, 3], const.CDF_INT4)
        self.assertTrue('new3' in attrs)
        numpy.testing.assert_array_equal([1, 2, 3], attrs['new3'])
        self.assertEqual(const.CDF_INT4.value, attrs.type('new3'))

    def testNewVar(self):
        """Create a new variable"""
        self.cdf.new('newzVar', [[1, 2, 3], [4, 5, 6]],
                     const.CDF_INT4)
        self.assertTrue('newzVar' in self.cdf)
        zvar = self.cdf['newzVar']
        numpy.testing.assert_array_equal(
            [[1, 2, 3], [4, 5, 6]], zvar[...])
        self.assertEqual(2, len(zvar))
        self.assertEqual([3], zvar._dim_sizes())

    def testNewVarAssign(self):
        """Create a new variable by assigning to CDF element"""
        self.cdf['newzVar'] = [[1, 2, 3], [4, 5, 6]]
        self.assertTrue('newzVar' in self.cdf)
        zvar = self.cdf['newzVar']
        numpy.testing.assert_array_equal(
            [[1, 2, 3], [4, 5, 6]], zvar[...])
        self.assertEqual(2, len(zvar))
        self.assertEqual([3], zvar._dim_sizes())

    def testBadDataSize(self):
        """Attempt to assign data of the wrong size to a zVar"""
        try:
            self.cdf['MeanCharge'] = [1.0, 2.0, 3.0]
        except ValueError:
            pass
        else:
            self.fail('Should have raised ValueError')

    def testChangeVarType(self):
        """Change the type of a variable"""
        self.cdf['new'] = [-1, -2, -3]
        self.cdf['new'].type(const.CDF_UINT1)
        numpy.testing.assert_array_equal(
            [255, 254, 253], self.cdf['new'][...])

    def testNewVarNoData(self):
        """Create a new variable without providing any data"""
        self.assertRaises(ValueError, self.cdf.new, 'newvar')
        self.cdf.new('newvar', None, const.CDF_INT4)
        self.assertEqual([], self.cdf['newvar']._dim_sizes())

        self.cdf.new('newvar2', None, const.CDF_CHAR, dims=[])
        self.assertEqual(1, self.cdf['newvar2']._nelems())

    def testNewVarNRV(self):
        """Create a new non-record-varying variable"""
        self.cdf.new('newvar2', [1, 2, 3], recVary=False)
        self.assertFalse(self.cdf['newvar2'].rv())
        self.assertEqual([3], self.cdf['newvar2']._dim_sizes())
        numpy.testing.assert_array_equal(
            [1, 2, 3], self.cdf['newvar2'][...])

    def testChangeRV(self):
        """Change record variance"""
        zVar = self.cdf.new('newvar', dims=[], type=const.CDF_INT4)
        self.assertTrue(zVar.rv())
        zVar.rv(False)
        self.assertFalse(zVar.rv())
        zVar.rv(True)
        self.assertTrue(zVar.rv())

    def testChecksum(self):
        """Change checksumming on the CDF"""
        self.cdf.checksum(True)
        self.assertTrue(self.cdf.checksum())
        self.cdf.checksum(False)
        self.assertFalse(self.cdf.checksum())

    def testCompress(self):
        """Change compression on the CDF"""
        self.cdf.compress(const.GZIP_COMPRESSION)
        (comptype, parm) = self.cdf.compress()
        self.assertEqual(const.GZIP_COMPRESSION, comptype),
        self.assertEqual(5, parm)
        self.cdf.compress(const.NO_COMPRESSION)
        (comptype, parm) = self.cdf.compress()
        self.assertEqual(const.NO_COMPRESSION, comptype),
        self.assertEqual(0, parm)

    def testVarCompress(self):
        """Change compression on a variable"""
        zvar = self.cdf.new('newvar', type=const.CDF_INT4, dims=[])
        zvar.compress(const.GZIP_COMPRESSION)
        (comptype, parm) = zvar.compress()
        self.assertEqual(const.GZIP_COMPRESSION, comptype),
        self.assertEqual(5, parm)
        zvar.compress(const.NO_COMPRESSION)
        (comptype, parm) = zvar.compress()
        self.assertEqual(const.NO_COMPRESSION, comptype),
        self.assertEqual(0, parm)

    def testWarnings(self):
        """Bizarre way to force a warning"""
        attrnum = ctypes.c_long(0)
        with warnings.catch_warnings(record=True) as w:
            self.cdf._call(cdf.const.CREATE_, cdf.const.ATTR_,
                           'this is a very long string intended to get up to '
                           '257 characters or so because the maximum length '
                           'of an attribute name is 256 characters and '
                           'attribute name truncated is just about the ONLY '
                           'warning I can figure out how to raise in the CDF '
                           'library and this is really a serious pain in just '
                           'about every portion of the anatomy.',
                           cdf.const.GLOBAL_SCOPE, ctypes.byref(attrnum))
            for curr_warn in w:
                self.assertTrue(isinstance(curr_warn.message, cdf.CDFWarning))
                self.assertEqual('ATTR_NAME_TRUNC: Attribute name truncated.',
                                 str(curr_warn.message))

    def testAssignEmptyList(self):
        """Assign an empty list to a variable"""
        self.cdf['ATC'] = []
        self.assertEqual(0, len(self.cdf['ATC']))

    def testReadEmptyList(self):
        """Read from an empty variable"""
        self.cdf['ATC'] = []
        data = self.cdf['ATC'][...]
        self.assertEqual((0,), data.shape)
        self.assertEqual(numpy.object, data.dtype)

    def testCopyVariable(self):
        """Copy one variable to another"""
        varlist = list(self.cdf.keys())
        #TODO: get rid of this when numpy rewrite is done;
        #right now it is SLOOOOOOW
        skiplist = ['SectorRateScalersCounts',
                    'SectorRateScalersCountsSigma',
                    ]
        for name in varlist:
            if name in skiplist:
                continue
            oldvar = self.cdf[name]
            self.cdf[name + '_2'] = oldvar
            newvar = self.cdf[name + '_2']
            msg = 'Variable ' + name + ' failed.'
            self.assertEqual(oldvar._n_dims(), newvar._n_dims(), msg)
            self.assertEqual(oldvar._dim_sizes(), newvar._dim_sizes(), msg)
            self.assertEqual(oldvar.type(), newvar.type(), msg)
            self.assertEqual(oldvar._nelems(), newvar._nelems(), msg)
            self.assertEqual(oldvar.compress(), newvar.compress(), msg)
            self.assertEqual(oldvar.rv(), newvar.rv(), msg)
            self.assertEqual(oldvar.dv(), newvar.dv(), msg)
            numpy.testing.assert_array_equal(
                oldvar[...], newvar[...], msg)
            oldlist = oldvar.attrs
            newlist = newvar.attrs
            for attrname in oldlist:
                self.assertTrue(attrname in newlist)
                self.assertEqual(oldlist[attrname], newlist[attrname])
                self.assertEqual(oldlist.type(attrname),
                                 newlist.type(attrname))

    def testCloneVariable(self):
        """Clone a variable's type, dims, etc. to another"""
        varlist = list(self.cdf.keys())
        for name in varlist:
            oldvar = self.cdf[name]
            self.cdf.clone(oldvar, name + '_2', False)
            newvar = self.cdf[name + '_2']
            msg = 'Variable ' + name + ' failed.'
            self.assertEqual(oldvar._n_dims(), newvar._n_dims(), msg)
            self.assertEqual(oldvar._dim_sizes(), newvar._dim_sizes(), msg)
            self.assertEqual(oldvar.type(), newvar.type(), msg)
            self.assertEqual(oldvar._nelems(), newvar._nelems(), msg)
            self.assertEqual(oldvar.compress(), newvar.compress(), msg)
            self.assertEqual(oldvar.rv(), newvar.rv(), msg)
            self.assertEqual(oldvar.dv(), newvar.dv(), msg)
            if newvar.rv():
                self.assertEqual(0, newvar[...].size, msg)
            oldlist = oldvar.attrs
            newlist = newvar.attrs
            for attrname in oldlist:
                self.assertTrue(
                    attrname in newlist,
                    'Attribute {0} not found in copy of {1}'.format(
                    attrname, name))
                self.assertEqual(oldlist[attrname], newlist[attrname])
                self.assertEqual(oldlist.type(attrname),
                                 newlist.type(attrname))

    def testDimVariance(self):
        """Check and change dimension variance of a variable"""
        self.assertEqual([True],
            self.cdf['SpinNumbers'].dv())
        self.assertEqual([True, True, True],
            self.cdf['SectorRateScalersCounts'].dv())
        self.cdf.new('foobar', type=const.CDF_INT1,
                     dims=[2, 3], dimVarys=[True, False])
        self.assertEqual([True, False],
                         self.cdf['foobar'].dv())
        self.cdf['foobar'].dv([False, True])
        self.assertEqual([False, True],
                         self.cdf['foobar'].dv())

    def testCopyAttr(self):
        """Assign a gAttribute to another"""
        self.cdf.attrs['new_attr'] = self.cdf.attrs['TEXT']
        old_attr = self.cdf.attrs['TEXT']
        new_attr = self.cdf.attrs['new_attr']
        for i in range(self.cdf.attrs['TEXT'].max_idx()):
            self.assertEqual(old_attr.has_entry(i),
                             new_attr.has_entry(i))
            if old_attr.has_entry(i):
                self.assertEqual(old_attr[i], new_attr[i])
                self.assertEqual(old_attr.type(i),
                                 new_attr.type(i))

    def testCloneAttrList(self):
        """Copy an entire attribute list from one CDF to another"""
        try:
            with cdf.CDF('attrcopy.cdf', '') as newcdf:
                newcdf.attrs['deleteme'] = ['hello']
                newcdf.attrs.clone(self.cdf.attrs)
                for attrname in self.cdf.attrs:
                    self.assertTrue(attrname in newcdf.attrs)
                    old_attr = self.cdf.attrs[attrname]
                    new_attr = newcdf.attrs[attrname]
                    self.assertEqual(old_attr.max_idx(),
                                     new_attr.max_idx())
                    for i in range(old_attr.max_idx()):
                        self.assertEqual(old_attr.has_entry(i),
                                         new_attr.has_entry(i))
                        if old_attr.has_entry(i):
                            self.assertEqual(old_attr[i], new_attr[i])
                            self.assertEqual(old_attr.type(i),
                                             new_attr.type(i))
                for attrname in newcdf.attrs:
                    self.assertTrue(attrname in self.cdf.attrs)
        finally:
            os.remove('attrcopy.cdf')

    def testClonezAttrList(self):
        """Copy entire attribute list from one zVar to another"""
        oldlist = self.cdf['ATC'].attrs
        newlist = self.cdf['PhysRecNo'].attrs
        newlist.clone(oldlist)
        for attrname in oldlist:
            self.assertTrue(attrname in newlist)
            self.assertEqual(oldlist[attrname], newlist[attrname])
            self.assertEqual(oldlist.type(attrname),
                             newlist.type(attrname))
        oldlist = self.cdf['Epoch'].attrs
        newlist = self.cdf['MeanCharge'].attrs
        newlist.clone(oldlist)
        for attrname in oldlist:
            self.assertTrue(attrname in newlist,
                            'Attribute {0} not found in copy.'.format(attrname)
                            )
            self.assertEqual(oldlist[attrname], newlist[attrname])
            self.assertEqual(oldlist.type(attrname),
                             newlist.type(attrname))

    def testAssignEpoch16Entry(self):
        """Assign to an Epoch16 entry"""
        self.cdf['ATC'].attrs['FILLVAL'] = datetime.datetime(2010,1,1)
        self.assertEqual(datetime.datetime(2010,1,1),
                         self.cdf['ATC'].attrs['FILLVAL'])

    def testVarTrailingSpaces(self):
        """Cut trailing spaces from names of vars"""
        self.cdf['foobar  '] = [1, 2, 3]
        namelist = list(self.cdf.keys())
        self.assertTrue('foobar' in namelist)
        self.assertFalse('foobar  ' in namelist)

    def testAttrTrailingSpaces(self):
        """Cut trailing spaces from names of attributes"""
        self.cdf.attrs['hi '] = 'hello'
        namelist = list(self.cdf.attrs.keys())
        self.assertTrue('hi' in namelist)
        self.assertFalse('hi ' in namelist)

    def testzVarInsert(self):
        """Insert a record into a zVariable"""
        before = self.cdf['ATC'][:].tolist()
        self.cdf['ATC'].insert(100, datetime.datetime(2010, 12, 31))
        before.insert(100, datetime.datetime(2010, 12, 31))
        numpy.testing.assert_array_equal(before, self.cdf['ATC'][:])
        before = self.cdf['MeanCharge'][:].tolist()
        self.cdf['MeanCharge'].insert(20, [99] * 16)
        before.insert(20, [99] * 16)
        numpy.testing.assert_array_equal(before, self.cdf['MeanCharge'][:])


class ChangeColCDF(ColCDFTests):
    """Tests that modify an existing colum-major CDF"""
    def __init__(self, *args):
        super(ChangeColCDF, self).__init__(*args)

    def setUp(self):
        shutil.copy(self.testmaster, self.testfile)
        self.cdf = cdf.CDF(self.testfile)
        self.cdf.readonly(False)

    def tearDown(self):
        self.cdf.close()
        del self.cdf
        os.remove(self.testfile)

    def testWriteColSubscripted(self):
        """Write data to a slice of a zVar"""
        expected = ['0 ', '1 ', '99', '3 ', '98', '5 ', '97', '7 ',
                    '8 ', '9 ']
        self.cdf['SpinNumbers'][2:7:2] = ['99', '98', '97']
        numpy.testing.assert_array_equal(expected, self.cdf['SpinNumbers'][0:10])

        expected = self.cdf['SectorRateScalersCounts'][...]
        expected[4][5][5][8:3:-1] = [101.0, 102.0, 103.0, 104.0, 105.0]
        self.cdf['SectorRateScalersCounts'][4, 5, 5, 8:3:-1] = \
            [101.0, 102.0, 103.0, 104.0, 105.0]
        numpy.testing.assert_array_equal(
            expected, self.cdf['SectorRateScalersCounts'][...])


if __name__ == '__main__':
    unittest.main()
