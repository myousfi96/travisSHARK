from travisshark.parsers.java_parser.java_build_log_file_parser import JavaBuildLogFileParser

# This class is based on https://github.com/TestRoots/travistorrent-tools/blob/master/lib/languages/java_maven_log_file_analyzer.rb
class MavenBuildLogFileParser(JavaBuildLogFileParser):
    def __init__(self, log, debug_level):
        super().__init__(log, debug_level)
        self.reactor_lines = []
        self._test_lines = []
        self._errored_tests_lines = []
        self._failed_tests_lines = []
        self.tests_failed = set([])
        self.tests_errored = set([])
        self.test_framework = None
        self.tests_run_completely = False

    def parse(self):
        self._extract_tests()
        self._analyze_tests()
        return list(self.tests_failed), list(self.tests_errored), self.test_framework, self.tests_run_completely

    def detect(self, job_config):
        if ('env' in job_config and 'mvn' in job_config['env']) \
                or ('install' in job_config and 'mvn' in ' '.join(job_config['install'])) \
                or ('script' in job_config and 'mvn' in ' '.join(job_config['script'])):
            self.logger.debug("Found Maven build file...")
            return True
        return False

    def _get_fqn_from_line(self, line):
        line_parts = line.strip().split('(')
        method_name = line_parts[0]
        fqn = line_parts[1].split(')')[0] + "." + method_name
        return fqn

    def _analyze_tests(self):

        # If we have the information available which test method was failing, we directly grab it
        for errored_line in self._errored_tests_lines:
            self.tests_errored.add(self._get_fqn_from_line(errored_line.split(' ')[0]))

        for failed_line in self._failed_tests_lines:
            self.tests_failed.add(self._get_fqn_from_line(failed_line.split(' ')[0]))

        # If not, we need to parse through the file, till we get to the "Failed tests" / "Tests in error" part
        failed_tests_started = False
        errored_tests_started = False
        for line in self._test_lines:
            if 'Total tests run' in line and 'Skips:' in line:
                self.test_framework = 'testng'
                self.tests_run_completely = True

            if ('Tests run:' in line and 'Time elapsed:' in line) \
                    or ('Tests run:' in line and 'Failures:' in line and 'Errors:' in line and 'Skipped:' in line):
                self.test_framework = 'junit'
                self.tests_run_completely = True

            if failed_tests_started and line.strip():
                # If we have found a failed test, we try to parse it. This is not always possible
                try:
                    self.tests_failed.add(self._get_fqn_from_line(line))
                except IndexError:
                    self.logger.error("Could not parse line %s" % line)

            if errored_tests_started and line.strip():
                line_part = line.strip().split(' ')[0]
                if ':' in line_part or ('(' not in line_part and ')' not in line_part):
                    fqn_parts = line_part.split(':')[0]
                    class_name = fqn_parts.split('.')[0]
                    method_name = fqn_parts.split('.')[1]
                    # To get the fqn of the test, we need to go through all lines again to find the error line
                    for n_line in self._test_lines:
                        if n_line.startswith(method_name) and class_name in n_line:
                            self.tests_errored.add(self._get_fqn_from_line(n_line))
                else:
                    self.tests_errored.add(self._get_fqn_from_line(line_part))



            if not line.strip():
                failed_tests_started = False
                errored_tests_started = False

            if "Failed tests:" in line:
                failed_tests_started = True

            if "Tests in error:" in line:
                errored_tests_started = True

    def _extract_tests(self):
        test_section_started = False
        reactor_started = False
        line_marker = 0

        for line in self.log.split("\n"):
            if '<<< FAILURE!' in line and not line.startswith("Tests"):
                self._failed_tests_lines.append(line)
            if '<<< ERROR!' in line and not line.startswith("Tests"):
                self._errored_tests_lines.append(line)

            if line == '-------------------------------------------------------\r' and line_marker == 0:
                line_marker = 1
            elif line == '[INFO] Reactor Summary:\r':
                reactor_started = True
                test_section_started = False
            elif reactor_started and not line.startswith('['):
                reactor_started = False
            elif line == ' T E S T S\r' and line_marker == 1:
                line_marker = 2
            elif line_marker == 1:
                line_marker = 0
            elif line == '-------------------------------------------------------\r' and line_marker == 2:
                line_marker = 3
                test_section_started = True
            elif line == '-------------------------------------------------------\r' and line_marker == 3:
                line_marker = 0
                test_section_started = False
            else:
                line_marker = 0

            if test_section_started:
                self._test_lines.append(line)
            elif reactor_started:
                self.reactor_lines.append(line)
