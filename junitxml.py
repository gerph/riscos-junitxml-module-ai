"""
JUnitXML PyModule - Python implementation of the JUnitXML RISC OS module.

This module provides the same interface as the C implementation, allowing
creation of JUnit XML test result files.

Python 2.7 compatible.
"""

from __future__ import with_statement

from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

from riscos.modules.pymodules import PyModule
from riscos.errors import RISCOSError
from riscos.rotime import quin_to_datetime


# SWI base number - must match the C module's allocation
SWI_BASE = 0x5AC00

# SWI offsets
SWI_JUnitXML_Create = 0
SWI_JUnitXML_TestSuite = 1
SWI_JUnitXML_TestCase = 2
SWI_JUnitXML_Close = 3
SWI_JUnitXML_Result = 4

# Flag definitions (matching C module)
JUnitXML_Create_FilenameGiven = (1 << 0)

JUnitXML_TestSuite_OpMask = 0x0F
JUnitXML_TestSuite_OpCreate = 0
JUnitXML_TestSuite_OpClose = 1
JUnitXML_TestSuite_OpUpdate = 2
JUnitXML_TestSuite_OpProperty = 3

JUnitXML_TestSuite_PackageSupplied = (1 << 4)
JUnitXML_TestSuite_TSMask = (3 << 5)
JUnitXML_TestSuite_TSShift = 5
JUnitXML_TestSuite_TSCurrent = 0
JUnitXML_TestSuite_TSRiscOS = (1 << 5)
JUnitXML_TestSuite_TSUnix = (2 << 5)
JUnitXML_TestSuite_TSISO8601 = (3 << 5)
JUnitXML_TestSuite_DurationPresent = (1 << 7)

JUnitXML_TestCase_OpMask = 0x0F
JUnitXML_TestCase_OpCreate = 0
JUnitXML_TestCase_OpClose = 1
JUnitXML_TestCase_OpUpdate = 2

JUnitXML_TestCase_StatusMask = (0x0F << 4)
JUnitXML_TestCase_StatusShift = 4
JUnitXML_TestCase_StatusNone = (0 << 4)
JUnitXML_TestCase_StatusSuccess = (1 << 4)
JUnitXML_TestCase_StatusFailure = (2 << 4)
JUnitXML_TestCase_StatusError = (3 << 4)
JUnitXML_TestCase_StatusSkipped = (4 << 4)

JUnitXML_TestCase_ErrorBlock = (1 << 8)

JUnitXML_Close_FilenameGiven = (1 << 0)


class JUnitHandle(object):
    """Represents a JUnit XML file handle."""

    def __init__(self, handle_id, ro, filename=None):
        self.handle_id = handle_id
        self.ro = ro
        self.filename = filename
        self.file = None
        self.suites = []
        self.current_suite = None
        self.next_suite_id = 1

    def open_file(self):
        """Open the output file for writing."""
        if self.filename:
            self.file = self.ro.kernel.api.open(self.filename, 'w')
            self._write_header()

    def close_file(self):
        """Close the output file."""
        if self.file:
            self._write_footer()
            self.file.close()
            self.file = None

    def _write_header(self):
        """Write XML header."""
        if self.file:
            self.file.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            self.file.write('<testsuites>\n')
            self.file.flush()

    def _write_footer(self):
        """Write XML footer."""
        if self.file:
            self.file.write('</testsuites>\n')

    def create_suite(self, id_val, name, package, timestamp):
        """Create a new test suite."""
        suite = JUnitTestSuite(self.next_suite_id, id_val, name, package, timestamp)
        self.suites.append(suite)
        self.current_suite = suite
        self.next_suite_id += 1

        # Write suite header immediately for incremental output
        if self.file:
            suite.write_open(self.file)
            # Write properties container opening tag
            self.file.write('    <properties>\n')
            self.file.flush()

        return suite

    def close_suite(self, duration_cs=0):
        """Close the current test suite."""
        if self.current_suite:
            # Close any open test case first
            if self.current_suite.current_case:
                self.close_testcase(0)

            if self.file:
                # Close properties container if not already closed
                if not self.current_suite.properties_closed:
                    self.file.write('    </properties>\n')
                    self.current_suite.properties_closed = True
                self.current_suite.write_close(self.file, duration_cs)
                self.file.flush()
            self.current_suite = None

    def set_property(self, name, value):
        """Set a property on the current suite."""
        if self.current_suite:
            self.current_suite.properties.append((name, value))
            # Write property immediately for incremental output
            if self.file:
                self.file.write('      <property name="{}" value="{}"/>\n'.format(
                    xml_escape(name), xml_escape(value)))
                self.file.flush()

    def create_testcase(self, id_val, classname, name, status, failure_type, failure_msg):
        """Create a new test case."""
        if not self.current_suite:
            raise self.error('BadSuiteOp')

        # Close any existing open test case
        if self.current_suite.current_case:
            self.close_testcase(0)

        testcase = JUnitTestCase(id_val, classname, name, status, failure_type, failure_msg)
        self.current_suite.current_case = testcase
        return testcase

    def close_testcase(self, duration_cs=0):
        """Close the current test case and write it out."""
        if not self.current_suite or not self.current_suite.current_case:
            raise self.error('BadCaseOp')

        tc = self.current_suite.current_case
        tc.time_cs = duration_cs

        # Update suite counts
        self.current_suite.tests_count += 1
        if tc.status == JUnitXML_TestCase_StatusFailure:
            self.current_suite.failures_count += 1
        elif tc.status == JUnitXML_TestCase_StatusError:
            self.current_suite.errors_count += 1
        elif tc.status == JUnitXML_TestCase_StatusSkipped:
            self.current_suite.skipped_count += 1

        # Close properties container before first test case
        if self.file and not self.current_suite.properties_closed:
            self.file.write('    </properties>\n')
            self.current_suite.properties_closed = True

        # Write the test case to file
        if self.file:
            tc.write(self.file)
            self.file.flush()

        # Add to test cases list
        self.current_suite.testcases.append(tc)
        self.current_suite.current_case = None


class JUnitTestSuite(object):
    """Represents a test suite."""

    def __init__(self, numeric_id, id_val, name, package, timestamp):
        self.numeric_id = numeric_id
        self.id = id_val
        self.name = name
        self.package = package
        self.hostname = None
        self.timestamp = timestamp or datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        self.time_cs = 0
        self.tests_count = 0
        self.failures_count = 0
        self.errors_count = 0
        self.skipped_count = 0
        self.properties = []
        self.testcases = []
        self.current_case = None
        self.properties_closed = False

    def write_open(self, fp):
        """Write the opening tag of the test suite."""
        fp.write('  <testsuite')
        fp.write(' name="{}"'.format(xml_escape(self.name)))
        if self.package:
            fp.write(' package="{}"'.format(xml_escape(self.package)))
        if self.hostname:
            fp.write(' hostname="{}"'.format(xml_escape(self.hostname)))
        if self.id:
            fp.write(' id="{}"'.format(xml_escape(self.id)))
        if self.timestamp:
            fp.write(' timestamp="{}"'.format(xml_escape(self.timestamp)))
        fp.write(' tests="{}"'.format(self.tests_count))
        fp.write(' failures="{}"'.format(self.failures_count))
        fp.write(' errors="{}"'.format(self.errors_count))
        fp.write(' skipped="{}"'.format(self.skipped_count))
        seconds = self.time_cs // 100
        cs = self.time_cs % 100
        fp.write(' time="{}.{:02d}"'.format(seconds, cs))
        fp.write('>\n')

    def write_close(self, fp, duration_cs=0):
        """Write the closing tag of the test suite."""
        if duration_cs > 0:
            self.time_cs = duration_cs
        fp.write('  </testsuite>\n')


class JUnitTestCase(object):
    """Represents a test case."""

    def __init__(self, id_val, classname, name, status, failure_type, failure_msg):
        self.id = id_val
        self.classname = classname
        self.name = name
        self.status = status
        self.failure_type = failure_type
        self.failure_message = failure_msg
        self.time_cs = 0
        self.file = None
        self.line = 0
        self.system_out = None
        self.system_err = None

    def write(self, fp):
        """Write the test case element."""
        fp.write('    <testcase')
        fp.write(' classname="{}"'.format(xml_escape(self.classname)))
        fp.write(' name="{}"'.format(xml_escape(self.name)))
        if self.file:
            fp.write(' file="{}"'.format(xml_escape(self.file)))
        if self.line > 0:
            fp.write(' line="{}"'.format(self.line))
        if self.id:
            fp.write(' id="{}"'.format(xml_escape(self.id)))

        seconds = self.time_cs // 100
        cs = self.time_cs % 100
        fp.write(' time="{}.{:02d}"'.format(seconds, cs))

        # Check if we need a status element
        status_element = self._get_status_element()

        if status_element:
            fp.write('>\n')
            # Write status element with type and message attributes
            fp.write('      <{}'.format(status_element))
            if self.failure_type:
                fp.write(' type="{}"'.format(xml_escape(self.failure_type)))
            if self.failure_message:
                fp.write(' message="{}"'.format(xml_escape(self.failure_message)))
            fp.write('/>\n')

            # Write system-out and system-err if present
            if self.system_out:
                fp.write('      <system-out>{}</system-out>\n'.format(xml_escape(self.system_out)))
            if self.system_err:
                fp.write('      <system-err>{}</system-err>\n'.format(xml_escape(self.system_err)))

            fp.write('    </testcase>\n')
        else:
            # No status element - self-closing tag
            fp.write('/>\n')

    def _get_status_element(self):
        """Get the status element name for this test case."""
        if self.status == JUnitXML_TestCase_StatusFailure:
            return 'failure'
        elif self.status == JUnitXML_TestCase_StatusError:
            return 'error'
        elif self.status == JUnitXML_TestCase_StatusSkipped:
            return 'skipped'
        return None


class JUnitXML(PyModule, object):
    """JUnitXML PyModule implementation."""

    version = '0.01'
    date = '26 Mar 2026'
    swi_base = SWI_BASE
    swi_prefix = "JUnitXML"
    swi_names = [
        'Create',
        'TestSuite',
        'TestCase',
        'Close',
        'Result',
    ]
    error_base = 0x822A00
    errors = [
        ('CreateFailed', "Failed to create JUnitXML handle"),
        ('CreateSuiteFailed', "Failed to create test suite"),
        ('CloseSuiteFailed', "Failed to close test suite"),
        ('SetPropertyFailed', "Failed to set property"),
        ('BadSuiteOp', "Unknown TestSuite operation"),
        ('CreateCaseFailed', "Failed to create test case"),
        ('CloseCaseFailed', "Failed to close test case"),
        ('BadCaseOp', "Unknown TestCase operation"),
        ('CloseFailed', "Failed to close JUnitXML handle"),
        ('NoHandle', "No JUnitXML handle to close"),
        ('InitFailed', "Failed to initialise JUnitXML state"),
    ]

    def __init__(self, ro, module):
        super(JUnitXML, self).__init__(ro, module)
        self.handles = {}
        self.next_handle_id = 1

    def finalise(self, pwp):
        """
        Finalise the module, closing any open files and cleaning up handles.
        Called when the module is unloaded.
        """
        # Close all open handles
        for handle_id, handle in list(self.handles.items()):
            try:
                # Close any open test case first
                if handle.current_suite and handle.current_suite.current_case:
                    handle.close_testcase(0)
                # Close any open test suite
                if handle.current_suite:
                    handle.close_suite(0)
                # Close the file
                if handle.file:
                    handle.close_file()
            except Exception:
                # Ignore errors during finalisation
                pass
        # Clear the handles dictionary
        self.handles = {}

    def swi(self, swioffset, regs):
        """Dispatch SWI calls to appropriate handlers."""
        if swioffset == SWI_JUnitXML_Create:
            return self.swi_create(regs)
        elif swioffset == SWI_JUnitXML_TestSuite:
            return self.swi_testsuite(regs)
        elif swioffset == SWI_JUnitXML_TestCase:
            return self.swi_testcase(regs)
        elif swioffset == SWI_JUnitXML_Close:
            return self.swi_close(regs)
        elif swioffset == SWI_JUnitXML_Result:
            return self.swi_result(regs)
        return False

    def swi_create(self, regs):
        """
        JUnitXML_Create
        =>  R0 = flags:
                b0 : filename to write is supplied
            R1-> filename to write (if b0 set)
        <=  R0 = handle
        """
        flags = regs[0]
        filename = None

        if flags & JUnitXML_Create_FilenameGiven:
            # Read filename from memory
            filename_ptr = regs[1]
            filename = self.ro.memory[filename_ptr].string

        # Create new handle
        handle_id = self.next_handle_id
        self.next_handle_id += 1

        handle = JUnitHandle(handle_id, self.ro, filename)
        self.handles[handle_id] = handle

        # Open file if filename supplied
        if filename:
            handle.open_file()

        regs[0] = handle_id
        return True

    def swi_testsuite(self, regs):
        """
        JUnitXML_TestSuite
        =>  R0 = flags:
                b0-3: operation:
                        0 : create new test suite
                        1 : close test suite
                        2 : update test suite
                        3 : set property
                b4:   package is supplied in R4
                b5-6: timestamp format:
                        0 : ignored (use current time on creation)
                        1 : pointer to a RISC OS time quintuple
                        2 : unix epoch time
                        3 : pointer to ISO 8601 time string
                b7:   duration is present (in centiseconds)
            R1 = junitxml handle
        """
        flags = regs[0]
        handle_id = regs[1]
        op = flags & JUnitXML_TestSuite_OpMask
        ts_format = (flags & JUnitXML_TestSuite_TSMask) >> JUnitXML_TestSuite_TSShift
        has_duration = flags & JUnitXML_TestSuite_DurationPresent
        has_package = flags & JUnitXML_TestSuite_PackageSupplied

        handle = self.handles.get(handle_id)
        if not handle:
            raise self.error('NoHandle')

        if op == JUnitXML_TestSuite_OpCreate:
            # Create new test suite
            id_val = regs[2]
            name_ptr = regs[3]
            package_ptr = regs[4] if has_package else 0
            timestamp_ptr = regs[5]

            # Read strings from memory
            if id_val == 0 or id_val >= 65536:
                # Pointer to string or 0 for auto-generated
                if id_val >= 65536:
                    id_val = self.ro.memory[id_val].string
                else:
                    id_val = None
            else:
                # Small integer ID - convert to string
                id_val = str(id_val)

            name = self.ro.memory[name_ptr].string if name_ptr else None

            package = None
            if has_package and package_ptr:
                package = self.ro.memory[package_ptr].string

            # Handle timestamp based on format
            timestamp = None
            if ts_format == JUnitXML_TestSuite_TSRiscOS:
                # RISC OS time quin (5-byte value)
                time_ptr = timestamp_ptr
                if time_ptr:
                    quin = self.ro.memory[time_ptr].quin
                    dt = quin_to_datetime(quin)
                    timestamp = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            elif ts_format == JUnitXML_TestSuite_TSUnix:
                # Unix epoch time
                unix_time = timestamp_ptr
                # Python 2.7: use utcfromtimestamp and manually add Z
                dt = datetime.utcfromtimestamp(unix_time)
                timestamp = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            elif ts_format == JUnitXML_TestSuite_TSISO8601:
                # Pointer to ISO 8601 string
                if timestamp_ptr:
                    timestamp = self.ro.memory[timestamp_ptr].string
            # else JUnitXML_TestSuite_TSCurrent - use current time (None)

            handle.create_suite(id_val, name, package, timestamp)

        elif op == JUnitXML_TestSuite_OpClose:
            # Close test suite
            duration = regs[2] if has_duration else 0
            handle.close_suite(duration)

        elif op == JUnitXML_TestSuite_OpUpdate:
            # Update operation - not implemented
            raise self.error('BadSuiteOp')

        elif op == JUnitXML_TestSuite_OpProperty:
            # Set property
            name_ptr = regs[2]
            value_ptr = regs[3]

            name = self.ro.memory[name_ptr].string if name_ptr else None
            value = self.ro.memory[value_ptr].string if value_ptr else None

            handle.set_property(name, value)

        return True

    def swi_testcase(self, regs):
        """
        JUnitXML_TestCase
        =>  R0 = flags:
                b0-3: operation:
                        0 : create new test case
                        1 : close test case
                        2 : update test case
                b4-7: status:
                        0 : no result present
                        1 : success
                        2 : failure
                        3 : error
                        4 : skipped
                b5: failure in R6 is a RISC OS error block
            R1 = junitxml handle
            R2-> id (or <65536 for an integer id, or 0 to generate on creation)
            R3-> class name
            R4-> test name
            R5-> failure type name, or 0 for default string
            R6-> failure message, or 0 for default string
        """
        flags = regs[0]
        handle_id = regs[1]
        op = flags & JUnitXML_TestCase_OpMask
        status = flags & JUnitXML_TestCase_StatusMask
        is_error_block = flags & JUnitXML_TestCase_ErrorBlock

        handle = self.handles.get(handle_id)
        if not handle:
            raise self.error('NoHandle')

        if op == JUnitXML_TestCase_OpCreate:
            # Create new test case
            id_val = regs[2]
            classname_ptr = regs[3]
            name_ptr = regs[4]
            failure_type_ptr = regs[5]
            failure_msg_ptr = regs[6]

            # Read strings from memory
            if id_val == 0 or id_val >= 65536:
                # Pointer to string or 0 for auto-generated
                if id_val >= 65536:
                    id_val = self.ro.memory[id_val].string
                else:
                    id_val = None
            else:
                # Small integer ID - convert to string
                id_val = str(id_val)

            classname = self.ro.memory[classname_ptr].string if classname_ptr else None
            name = self.ro.memory[name_ptr].string if name_ptr else None

            failure_type = None
            if failure_type_ptr:
                if is_error_block:
                    # failure_type points to a RISC OS error block
                    failure_type = "RISC_OSError"
                else:
                    failure_type = self.ro.memory[failure_type_ptr].string

            failure_msg = None
            if failure_msg_ptr and not is_error_block:
                failure_msg = self.ro.memory[failure_msg_ptr].string

            handle.create_testcase(id_val, classname, name, status, failure_type, failure_msg)

        elif op == JUnitXML_TestCase_OpClose:
            # Close test case
            duration = regs[2]
            handle.close_testcase(duration)

        elif op == JUnitXML_TestCase_OpUpdate:
            # Update operation - not implemented
            raise self.error('BadCaseOp')

        return True

    def swi_close(self, regs):
        """
        JUnitXML_Close
        =>  R0 = flags:
                b0 : filename to write is supplied (overrides the original filename)
            R1-> filename (if b0 set)
        """
        flags = regs[0]
        filename = None

        if flags & JUnitXML_Close_FilenameGiven:
            # Read filename from memory
            filename_ptr = regs[1]
            filename = self.ro.memory[filename_ptr].string

        # Close the most recently created handle (or first handle in list)
        if not self.handles:
            raise self.error('NoHandle')

        # Get the first (most recent) handle
        handle_id = list(self.handles.keys())[0]
        handle = self.handles[handle_id]

        # If new filename supplied, close old file and open new one
        if filename:
            handle.close_file()
            handle.filename = filename
            handle.open_file()

        # Close the file (writes footer)
        handle.close_file()

        # Remove from handle list
        del self.handles[handle_id]

        return True

    def swi_result(self, regs):
        """
        JUnitXML_Result
        =>  R0 = flags (reserved, must be 0)
            R1 = junitxml handle
        <=  R0 = number of tests present
            R1 = number of passes
            R2 = number of failures
            R3 = number of errors
            R4 = number of skips
        """
        handle_id = regs[1]

        handle = self.handles.get(handle_id)
        if not handle:
            raise self.error('NoHandle')

        tests = 0
        failures = 0
        errors = 0
        skips = 0

        for suite in handle.suites:
            tests    += suite.tests_count
            failures += suite.failures_count
            errors   += suite.errors_count
            skips    += suite.skipped_count

        regs[0] = tests
        regs[1] = tests - failures - errors - skips
        regs[2] = failures
        regs[3] = errors
        regs[4] = skips

        return True
