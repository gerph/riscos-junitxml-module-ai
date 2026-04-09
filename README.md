# JUnitXML Module

A RISC OS module for generating JUnit XML test output files. This module provides a programmatic interface for creating JUnit-format XML files that are compatible with CI/CD systems, test runners, and reporting tools.

## Features

- **Multiple output handles** - Create multiple JUnit XML files simultaneously
- **Test suites** - Support for name, package, hostname, timestamp, and custom properties
- **Test cases** - Full support for classname, test name, status, and timing
- **Status reporting** - Success, failure, error, and skipped test states
- **Failure details** - Capture failure type and message for failed tests
- **Output capture** - system-out and system-err elements for test output
- **Incremental writing** - XML is written as tests complete (not buffered)
- **Flexible timestamps** - Support for current time, RISC OS time, Unix epoch, or ISO 8601
- **Result retrieval** - Query aggregate pass, failure, error, and skip counts from a handle

## Building

Requires the RISC OS cross-compilation toolchain (`riscos-amu`):

```bash
riscos-amu
```

The built module will be output to `rm32/JUnitXML,ffa`.

## SWI Interface

### JUnitXML_Create

Create a new JUnit XML output handle.

```
SWI "JUnitXML_Create", flags, filename TO handle
```

**Parameters:**
- `flags` - Bit 0: filename supplied
- `filename` - Output filename (if flags bit 0 set)

**Returns:**
- `handle` - Handle number for subsequent calls

**Example:**
```basic
SYS "JUnitXML_Create", 1, "test-results.xml" TO jx%
```

### JUnitXML_TestSuite

Create, close, or modify a test suite.

```
SWI "JUnitXML_TestSuite", flags, handle, ...
```

**Flags:**
- Bits 0-3: Operation
  - 0: Create new test suite
  - 1: Close test suite
  - 2: Update test suite metadata
  - 3: Set property
- Bit 4 (Create): Package supplied in R4
- Bits 5-6 (Create): Timestamp format
  - 0: Use current time
  - 1: RISC OS time quintuple (pointer in R5)
  - 2: Unix epoch time (value in R5)
  - 3: ISO 8601 string (pointer in R5)
- Bit 7 (Close): Duration present in R2 (centiseconds)

**Create operation (op=0):**
```
R2 = id string, or 0 for auto-assigned numeric ID
R3 = suite name
R4 = package name (if bit 4 set)
R5 = timestamp (format per bits 5-6; omit if using current time)
```

**Close operation (op=1):**
```
R2 = duration in centiseconds (if bit 7 set)
```

**Update operation (op=2):**

Updates hostname, name, or package on the open suite. Must be called before the first property or test case is added.

- Bit 4: Hostname supplied in R2
- Bit 5: New suite name supplied in R3
- Bit 6: New package name supplied in R4

```
R2 = hostname string (if bit 4 set)
R3 = new suite name (if bit 5 set)
R4 = new package name (if bit 6 set)
```

**Set property operation (op=3):**
```
R2 = property name
R3 = property value
```

**Example:**
```basic
REM Create a test suite with auto ID and current timestamp
SYS "JUnitXML_TestSuite", 0, jx%, 0, "MyTestSuite"

REM Create with package (bit 4 set)
SYS "JUnitXML_TestSuite", 1<<4, jx%, 0, "MySuite", "com.example.tests"

REM Update hostname before adding any tests
SYS "JUnitXML_TestSuite", 2 OR (1<<4), jx%, "my-machine"

REM Set a property
SYS "JUnitXML_TestSuite", 3, jx%, "build.number", "12345"

REM Close the suite with duration (100 cs = 1 second)
SYS "JUnitXML_TestSuite", 1 OR (1<<7), jx%, 100
```

### JUnitXML_TestCase

Create or close a test case within the current suite.

```
SWI "JUnitXML_TestCase", flags, handle, ...
```

**Flags:**
- Bits 0-3: Operation
  - 0: Create new test case
  - 1: Close test case
  - 2: Update test case (not implemented)
- Bits 4-7: Status
  - 0: No result
  - 1: Success
  - 2: Failure
  - 3: Error
  - 4: Skipped
- Bit 8: Failure is RISC OS error block

**Create operation (op=0):**
```
R2 = id (string or 0 for auto)
R3 = classname
R4 = test name
R5 = failure type (or 0)
R6 = failure message (or 0)
```

**Close operation (op=1):**
```
R2 = duration (in centiseconds)
```

**Example:**
```basic
REM Successful test
SYS "JUnitXML_TestCase", 16, jx%, 0, "MyClass", "testSomething"

REM Failed test with details
SYS "JUnitXML_TestCase", 34, jx%, 0, "MyClass", "testFailure", "AssertionError", "Expected 1 but got 2"

REM Close with timing (150 centiseconds = 1.5 seconds)
SYS "JUnitXML_TestCase", 1, jx%, 150
```

### JUnitXML_Close

Close a JUnit XML handle and finalise the output file.

```
SWI "JUnitXML_Close", flags, filename
```

**Parameters:**
- `flags` - Bit 0: new filename supplied
- `filename` - Override output filename (if flags bit 0 set)

**Example:**
```basic
SYS "JUnitXML_Close", 0
```

### JUnitXML_Result

Retrieve aggregate result counts for all test suites within a handle.

```
SWI "JUnitXML_Result", flags, handle TO tests, passes, failures, errors, skips
```

**Parameters:**
- `flags` - Reserved, must be zero
- `handle` - Handle number

**Returns:**
- `tests` - Total number of test cases recorded
- `passes` - Number of passing tests
- `failures` - Number of tests that reported failure
- `errors` - Number of tests that reported an error
- `skips` - Number of skipped tests

This SWI may be called at any time while the handle is open. The counts are summed across all
suites, including those that are still open.

**Example:**
```basic
SYS "JUnitXML_Result", 0, jx% TO tests%, passes%, failures%, errors%, skips%
PRINT "Tests: "; tests%; " Passes: "; passes%; " Failures: "; failures%
IF failures% + errors% > 0 THEN PRINT "FAILED" ELSE PRINT "PASSED"
```

## Complete Example (BBC BASIC)

```basic
REM JUnit XML output example

JUnitXML_Create_FilenameGiven = 1
JUnitXML_Success = (1<<4)
JUnitXML_Failure = (2<<4)
JUnitXML_Error = (3<<4)
JUnitXML_Skipped = (4<<4)

REM Create output file
SYS "JUnitXML_Create", JUnitXML_Create_FilenameGiven, "test-results.xml" TO jx%

REM Create a test suite (bit 4 set to supply package name)
SYS "JUnitXML_TestSuite", 1<<4, jx%, 0, "CalculatorTests", "com.example.calc"

REM Set suite properties
SYS "JUnitXML_TestSuite", 3, jx%, "build.number", "42"
SYS "JUnitXML_TestSuite", 3, jx%, "os.version", "3.11"

REM Add passing test
SYS "JUnitXML_TestCase", JUnitXML_Success, jx%, 0, "Calculator", "testAddition"
SYS "JUnitXML_TestCase", JUnitXML_Success, jx%, 0, "Calculator", "testSubtraction"

REM Add failing test
SYS "JUnitXML_TestCase", JUnitXML_Failure, jx%, 0, "Calculator", "testDivision", "DivisionByZero", "Cannot divide by zero"

REM Add error test
SYS "JUnitXML_TestCase", JUnitXML_Error, jx%, 0, "Calculator", "testOverflow", "OverflowError", "Result too large"

REM Add skipped test
SYS "JUnitXML_TestCase", JUnitXML_Skipped, jx%, 0, "Calculator", "testMultiplication"

REM Close the suite
SYS "JUnitXML_TestSuite", 1, jx%

REM Retrieve result counts
SYS "JUnitXML_Result", 0, jx% TO tests%, passes%, failures%, errors%, skips%
PRINT "Tests: "; tests%; " Passes: "; passes%; " Failures: "; failures%; " Errors: "; errors%; " Skipped: "; skips%
IF failures% + errors% > 0 THEN PRINT "FAILED" ELSE PRINT "PASSED"

REM Close the file
SYS "JUnitXML_Close", 0

PRINT "JUnit XML written to test-results.xml"
```

## Output Format

The module produces JUnit XML format compatible with CI/CD systems:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="CalculatorTests" package="com.example.calc" id="1" timestamp="2026-01-01T00:00:00Z">
    <properties>
      <property name="build.number" value="42"/>
      <property name="os.version" value="3.11"/>
    </properties>
    <testcase classname="Calculator" name="testAddition" id="1" time="0.010"/>
    <testcase classname="Calculator" name="testSubtraction" id="2" time="0.010"/>
    <testcase classname="Calculator" name="testDivision" id="3" time="0.005">
      <failure type="DivisionByZero" message="Cannot divide by zero"/>
    </testcase>
    <testcase classname="Calculator" name="testOverflow" id="4" time="0.005">
      <error type="OverflowError" message="Result too large"/>
    </testcase>
    <testcase classname="Calculator" name="testMultiplication" id="5" time="0.000">
      <skipped/>
    </testcase>
  </testsuite>
</testsuites>
```

Note: when output is written incrementally (the normal case when a filename is given at create time), the `<testsuite>` opening tag does not include test count attributes (`tests`, `failures`, `errors`, `skipped`) since those totals are not yet known. Test case IDs are auto-assigned sequentially when `0` is passed for the ID.

## Architecture

The module is structured in three layers:

1. **junit_xml_writer** - Platform-independent XML generation functions. Can be tested separately from RISC OS.

2. **junit_state** - State management for handles, suites, and test cases. Manages memory and tracks current context.

3. **module** - RISC OS SWI interface layer. Translates SWI calls to state manager functions.

## License

MIT License - see LICENSE file for details.

## Requirements

- RISC OS 3.10 or later
- riscos-amu build toolchain for compilation
