# RISC OS build environment

## Overview
We are building components for the RISC OS operating system. This is a small system, similar
to embedded environments. It is not Linux or RISC OS based. Code will generally be written in C
or BBC BASIC.

The system is 32-bit based, and does not use multi-processing or threads. It is memory
constrained.

## New project
* Create command line tool in C: `riscos-project create --name <project> --type command --skeleton`
* Create module in C: `riscos-project create --name <project> --type cmodule --skeleton`
* Create source control management: (`.gitignore`/`.gitattributes`): `riscos-project create-git`
* Create CI files for GitHub and GitLab: `riscos-project create-ci`

## Build and Test
* Build 32-bit (default): `riscos-amu`
* Build 64-bit: `riscos-amu BUILD64=1`
* Increment version: `vmanage inc`
* Test 32-bit binary: `riscos-build-run aif32 --command aif32.<basename>`

## Coding Standards
* All variable declarations must appear at the **top of their block**, before any statements.
* Floating point should not be used in modules.
* No threading.

## Project Structure
* C source files live in a directory called `c`, and do not have an extension.
* C header files live in a directory called `h`, and do not have an extension.
* Makefile files have names that start with `Makefile` and end with `,fe1`.
* 32-bit executables are stored in the directory `aif32`.
* 64-bit executables are stored in the directory `aif64`.
* BBC BASIC files are named with a suffix of `,fd1`. They do not need line numbers.
* The version number of the project is in `VersionNum`, a C include file which describes values.
* If the project is a module, a `cmhg` directory will exist with a file describing the module definition and entry points.
* If the project name is not otherwise given, the environment variable `$ROBUILD_PROJECT` contains its name.

## RISC OS information
* RISC OS SWI interface information can be summarised using `riscos-prm <SWI name>`.
* Full information on the RISC OS SWI interface can be found a the url given by `riscos-prm --url <SWI name>`.

## Environmental
* Ignore all files inside the `.rotransform` directory.
* Information on how to use the environment can be found by running `riscos-help` and `riscos-help <doc>`.

## Organisation Rules
* Never commit directly to main. Always use feature branches.
* Use British English in comments and documentation.
* Unless otherwise stated, we use MIT license for our software.
* GPL components should not be used, and modules must never use a GPL license.
* Significant features should increment the version number.
* RISC OS is a small system, and memory frugal interfaces should be used where possible.

## Administration
* The user requesting operations has their name in the environment variable `$FULLNAME`.
