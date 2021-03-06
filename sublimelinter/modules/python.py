# -*- coding: utf-8 -*-
# python.py - Lint checking for Python - given filename and contents of the code:
# It provides a list of line numbers to outline and offsets to highlight.
#
# This specific module is part of the SublimeLinter project.
# It is a fork by André Roberge from the original SublimeLint project,
# (c) 2011 Ryan Hileman and licensed under the MIT license.
# URL: http://bochs.info/
#
# The original copyright notices for this file/project follows:
#
# (c) 2005-2008 Divmod, Inc.
# See LICENSE file for details
#
# The LICENSE file is as follows:
#
# Copyright (c) 2005 Divmod, Inc., http://www.divmod.com/
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

# TODO:
# * fix regex for variable names inside strings (quotes)

import re
import _ast

import pep8
import pyflakes.checker as pyflakes

from base_linter import BaseLinter

pyflakes.messages.Message.__str__ = lambda self: self.message % self.message_args

CONFIG = {
    'language': 'Python'
}


class PythonLintError(pyflakes.messages.Message):

    def __init__(self, filename, loc, level, message, message_args, offset=None, text=None):
        super(PythonLintError, self).__init__(filename, loc)
        self.level = level
        self.message = message
        self.message_args = message_args
        if offset is not None:
            self.offset = offset
        if text is not None:
            self.text = text


class Pep8Error(PythonLintError):

    def __init__(self, filename, loc, offset, code, text):
        # PEP 8 Errors are downgraded to "warnings"
        super(Pep8Error, self).__init__(filename, loc, 'W', '[W] PEP 8 (%s): %s', (code, text),
                                        offset=offset, text=text)


class Pep8Warning(PythonLintError):

    def __init__(self, filename, loc, offset, code, text):
        # PEP 8 Warnings are downgraded to "violations"
        super(Pep8Warning, self).__init__(filename, loc, 'V', '[V] PEP 8 (%s): %s', (code, text),
                                          offset=offset, text=text)


class OffsetError(PythonLintError):

    def __init__(self, filename, loc, text, offset):
        super(OffsetError, self).__init__(filename, loc, 'E', '[E] %r', (text,), offset=offset + 1, text=text)


class PythonError(PythonLintError):

    def __init__(self, filename, loc, text):
        super(PythonError, self).__init__(filename, loc, 'E', '[E] %r', (text,), text=text)


class Linter(BaseLinter):
    def pyflakes_check(self, code, filename, ignore=None):
        try:
            tree = compile(code, filename, "exec", _ast.PyCF_ONLY_AST)
        except (SyntaxError, IndentationError), value:
            msg = value.args[0]

            (lineno, offset, text) = value.lineno, value.offset, value.text

            # If there's an encoding problem with the file, the text is None.
            if text is None:
                # Avoid using msg, since for the only known case, it contains a
                # bogus message that claims the encoding the file declared was
                # unknown.
                if msg.startswith('duplicate argument'):
                    arg = msg.split('duplicate argument ', 1)[1].split(' ', 1)[0].strip('\'"')
                    error = pyflakes.messages.DuplicateArgument(filename, lineno, arg)
                else:
                    error = PythonError(filename, lineno, msg)
            else:
                line = text.splitlines()[-1]

                if offset is not None:
                    offset = offset - (len(text) - len(line))

                if offset is not None:
                    error = OffsetError(filename, lineno, msg, offset)
                else:
                    error = PythonError(filename, lineno, msg)
            return [error]
        except ValueError, e:
            return [PythonError(filename, 0, e.args[0])]
        else:
            # Okay, it's syntactically valid.  Now check it.
            w = pyflakes.Checker(tree, filename, ignore)
            return w.messages

    def pep8_check(self, code, filename, ignore=None):
        messages = []
        _lines = code.split('\n')

        if _lines:
            class SublimeLinterReport(pep8.BaseReport):
                def error(self, line_number, offset, text, check):
                    """Report an error, according to options."""
                    code = text[:4]
                    message = text[5:]

                    if self._ignore_code(code):
                        return
                    if code in self.counters:
                        self.counters[code] += 1
                    else:
                        self.counters[code] = 1
                        self.messages[code] = message

                    # Don't care about expected errors or warnings
                    if code in self.expected:
                        return

                    self.file_errors += 1
                    self.total_errors += 1

                    if code.startswith('E'):
                        messages.append(Pep8Error(filename, line_number, offset, code, message))
                    else:
                        messages.append(Pep8Warning(filename, line_number, offset, code, message))

                    return code

            _ignore = ignore + pep8.DEFAULT_IGNORE.split(',')

            options = pep8.StyleGuide(reporter=SublimeLinterReport, ignore=_ignore).options
            options.max_line_length = pep8.MAX_LINE_LENGTH

            good_lines = [l + '\n' for l in _lines]
            good_lines[-1] = good_lines[-1].rstrip('\n')

            if not good_lines[-1]:
                good_lines = good_lines[:-1]

            try:
                pep8.Checker(filename, good_lines, options).check_all()
            except Exception, e:
                print "An exception occured when running pep8 checker: %s" % e

        return messages

    def built_in_check(self, view, code, filename):
        errors = []

        if view.settings().get("pep8", True):
            errors.extend(self.pep8_check(code, filename, ignore=view.settings().get('pep8_ignore', [])))

        pyflakes_ignore = view.settings().get('pyflakes_ignore', None)
        pyflakes_disabled = view.settings().get('pyflakes_disabled', False)

        if not pyflakes_disabled:
            errors.extend(self.pyflakes_check(code, filename, pyflakes_ignore))

        return errors

    def parse_errors(self, view, errors, lines, errorUnderlines, violationUnderlines, warningUnderlines, errorMessages, violationMessages, warningMessages):

        def underline_word(lineno, word, underlines):
            regex = r'((and|or|not|if|elif|while|in)\s+|[+\-*^%%<>=\(\{{])*\s*(?P<underline>[\w\.]*{0}[\w]*)'.format(re.escape(word))
            self.underline_regex(view, lineno, regex, lines, underlines, word)

        def underline_import(lineno, word, underlines):
            linematch = '(from\s+[\w_\.]+\s+)?import\s+(?P<match>[^#;]+)'
            regex = '(^|\s+|,\s*|as\s+)(?P<underline>[\w]*{0}[\w]*)'.format(re.escape(word))
            self.underline_regex(view, lineno, regex, lines, underlines, word, linematch)

        def underline_for_var(lineno, word, underlines):
            regex = 'for\s+(?P<underline>[\w]*{0}[\w*])'.format(re.escape(word))
            self.underline_regex(view, lineno, regex, lines, underlines, word)

        def underline_duplicate_argument(lineno, word, underlines):
            regex = 'def [\w_]+\(.*?(?P<underline>[\w]*{0}[\w]*)'.format(re.escape(word))
            self.underline_regex(view, lineno, regex, lines, underlines, word)

        errors.sort(lambda a, b: cmp(a.lineno, b.lineno))
        ignoreImportStar = view.settings().get('pyflakes_ignore_import_*', True)

        for error in errors:
            try:
                error_level = error.level
            except AttributeError:
                error_level = 'W'
            if error_level == 'E':
                messages = errorMessages
                underlines = errorUnderlines
            elif error_level == 'V':
                messages = violationMessages
                underlines = violationUnderlines
            elif error_level == 'W':
                messages = warningMessages
                underlines = warningUnderlines

            if isinstance(error, pyflakes.messages.ImportStarUsed) and ignoreImportStar:
                continue

            self.add_message(error.lineno, lines, str(error), messages)

            if isinstance(error, (Pep8Error, Pep8Warning, OffsetError)):
                self.underline_range(view, error.lineno, error.offset, underlines)

            elif isinstance(error, (pyflakes.messages.RedefinedWhileUnused,
                                    pyflakes.messages.UndefinedName,
                                    pyflakes.messages.UndefinedExport,
                                    pyflakes.messages.UndefinedLocal,
                                    pyflakes.messages.Redefined,
                                    pyflakes.messages.UnusedVariable)):
                underline_word(error.lineno, error.message, underlines)

            elif isinstance(error, pyflakes.messages.ImportShadowedByLoopVar):
                underline_for_var(error.lineno, error.message, underlines)

            elif isinstance(error, pyflakes.messages.UnusedImport):
                underline_import(error.lineno, error.message, underlines)

            elif isinstance(error, pyflakes.messages.ImportStarUsed):
                underline_import(error.lineno, '*', underlines)

            elif isinstance(error, pyflakes.messages.DuplicateArgument):
                underline_duplicate_argument(error.lineno, error.message, underlines)

            elif isinstance(error, pyflakes.messages.LateFutureImport):
                pass

            else:
                print 'Oops, we missed an error type!', type(error)
