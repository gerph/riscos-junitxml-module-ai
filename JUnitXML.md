# JUnitXML module

Requirements:

* Multiple outputs created with a handle.
* Add test suite to the results. Test suite has:
    * name
    * package
    * hostname
    * id?
    * time (taken in seconds)
    * timestamp (in 8601)
    * tests count
    * failures count
    * errors count
    * nisabled
    * properties (list of keyed properties; name, value attributes)
    * system-out
    * system-err
* Add test case to the current suite. Test case has:
    * classname
    * name
    * time
    * file
    * line
    * id
    * status (elements: succcess, failure, skipped, error)
    * failure_type (property of the status element)
    * failure_message
    * system-out
    * system-err


JUnitXML_Create
=>  R0 = flags:
            b0 : filename to write is supplied
    R1-> filename to write (if b0 set)
<=  R0 = handle


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


JUnitXML_TestSuite 0 (Create new suite)
=>  R0 = flags
    R1 = junitxml handle
    R2-> id (or <65536 for an integer id, or 0 to generate on creation)
    R3-> name
    R4-> package
    R5-> timestamp


JUnitXML_TestSuite 1 (Close suite)
=>  R0 = flags
    R1 = junitxml handle
    R2 = duration (if b7 set)

JUnitXML_TestSuite 3 (Set property)
=>  R0 = flags
    R1 = junitxml handle
    R2-> property name
    R3-> property value


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


JUnitXML_Close
=>  R0 = flags:
            b0 : filename to write is supplied (overrides the original filename)
    R1-> filename (if b0 set)

Example BASIC code that should work:


JUnitXML_Success = (1<<4)
JUnitXML_Failure = (2<<4)
JUnitXML_Create_FilenameGiven = (1<<0)
:
SYS "JUnitXML_Create", JUnitXML_Create_FilenameGiven, "my-junit/xml" TO jx%
SYS "JUnitXML_TestSuite", 0, jx%, 0, "MySuite"
SYS "JUnitXML_TestCase", JUnitXML_Success, jx%, 0, "first test"
SYS "JUnitXML_TestCase", JUnitXML_Failure, jx%, 0, "second test", "DivisionByZero", "You divided by 0. Don't do that"
SYS "JUnitXML_Close", 0
