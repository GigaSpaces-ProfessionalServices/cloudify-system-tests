########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
import sys
import logging
import json
import random
import shutil
import time

import jinja2
import yaml
import sh
from path import path

from helpers import sh_bake
from helpers.suites_builder import build_suites_yaml

logging.basicConfig()

logger = logging.getLogger('suites_runner')
logger.setLevel(logging.INFO)

docker = sh_bake(sh.docker)
vagrant = sh_bake(sh.vagrant)

reports_dir = path(__file__).dirname() / 'xunit-reports'

TEST_SUITES_PATH = 'TEST_SUITES_PATH'
DOCKER_REPOSITORY = 'cloudify/test'
DOCKER_TAG = 'env'
SUITE_ENVS_DIR = 'suite-envs'
SCHEDULER_INTERVAL = 30


class TestSuite(object):

    def __init__(self, suite_name, suite_def, suite_work_dir, variables):
        self.suite_name = suite_name
        self.suite_def = suite_def
        self.suite_work_dir = suite_work_dir
        self.suite_reports_dir = suite_work_dir / 'xunit-reports'
        self.variables = variables
        self.process = None
        self.started = None
        self.terminated = None

    @property
    def handler_configuration(self):
        return self.suite_def.get('handler_configuration')

    @handler_configuration.setter
    def handler_configuration(self, value):
        self.suite_def['handler_configuration'] = value

    @property
    def requires(self):
        return self.suite_def.get('requires', [])

    def create_env(self):
        self.suite_work_dir.makedirs()
        self.suite_reports_dir.makedirs()
        vagrant_file_template = path('Vagrantfile.template').text()
        vagrant_file_content = jinja2.Template(vagrant_file_template).render({
            'suite_name': self.suite_name,
            'suite': json.dumps(self.suite_def),
            'variables': json.dumps(self.variables)
        })
        path(self.suite_work_dir / 'Vagrantfile').write_text(
            vagrant_file_content)
        files_to_copy = [
            'Dockerfile',
            'suite_runner.py',
            'suite_runner.sh',
            'requirements.txt',
            'suites',
            'helpers',
            'configurations']
        for file_name in files_to_copy:
            if os.path.isdir(file_name):
                shutil.copytree(file_name, os.path.join(self.suite_work_dir,
                                                        file_name))
            else:
                shutil.copy(file_name, os.path.join(self.suite_work_dir,
                                                    file_name))

    @property
    def is_running(self):
        return self.process is not None and self.process.is_alive()

    def run(self):
        logger.info('Creating environment for suite: {0}'.format(
            self.suite_name))
        self.create_env()
        logger.info('Starting suite in docker container: {0}'.format(
            self.suite_name))
        cwd = path.getcwd()
        try:
            os.chdir(self.suite_work_dir)
            vagrant.up().wait()
            self.process = vagrant('docker-logs', f=True, _bg=True).process
        finally:
            os.chdir(cwd)

    def copy_xunit_reports(self):
        report_files = self.suite_reports_dir.files('*.xml')
        logger.info('Suite [{0}] reports: {1}'.format(
            self.suite_name, [r.name for r in report_files]))
        for report in report_files:
            report.copy(reports_dir / report.name)


class SuitesScheduler(object):

    def __init__(self,
                 test_suites,
                 handler_configurations,
                 scheduling_interval=1,
                 optimize=False,
                 after_suite_callback=None):
        self._test_suites = test_suites
        if optimize:
            self._test_suites = sorted(
                test_suites,
                key=lambda x: x.handler_configuration is None)
        self._handler_configurations = handler_configurations
        self._locked_envs = set()
        self._scheduling_interval = scheduling_interval
        self._after_suite_callback = after_suite_callback
        self._validate()
        self._log_test_suites()

    def _log_test_suites(self):
        output = {x.suite_name: x.suite_def for x in self._test_suites}
        logger.info('SuitesScheduler initialized with the following suites'
                    ':\n{0}'.format(json.dumps(output, indent=2)))

    def _validate(self):
        for suite in self._test_suites:
            if not self._find_matching_handler_configurations(suite):
                raise ValueError(
                    'Cannot find a matching handler configuration for '
                    'suite: {0}'.format(suite.suite_name))

    def run(self):
        logger.info('Test suites scheduler started')
        suites_list = self._test_suites
        while len(suites_list) > 0:
            logger.info('Current suites in scheduler: {0}'.format(
                ', '.join(
                    ['{0} [started={1}]'.format(
                        s.suite_name,
                        s.started is not None) for s in suites_list])))
            remaining_suites = []
            for suite in suites_list:
                logger.info('Processing suite: {0}'.format(suite.suite_name))
                if not suite.started:
                    matches = self._find_matching_handler_configurations(suite)
                    config_names = matches.keys()
                    random.shuffle(config_names)
                    logger.info(
                        'Matching handler configurations for {0} are: {1}'
                        .format(suite.suite_name, ', '.join(config_names)))
                    for name in config_names:
                        configuration = matches[name]
                        if self._lock_env(configuration['env']):
                            suite.handler_configuration = name
                            suite.started = time.time()
                            suite.run()
                            break
                    if suite.started:
                        logger.info('Suite {0} will run using handler '
                                    'configuration: {1}'.format(
                                        suite.suite_name,
                                        suite.handler_configuration))
                    else:
                        logger.info(
                            'All matching handler configurations for '
                            '{0} are currently taken'.format(suite.suite_name))
                    remaining_suites.append(suite)
                elif not suite.is_running:
                    suite.terminated = time.time()
                    logger.info(
                        'Suite terminated: {0}'.format(suite.suite_name))
                    try:
                        if self._after_suite_callback:
                            self._after_suite_callback(suite)
                    except Exception as e:
                        logger.error(
                            'After suite callback failed for suite: {0} - '
                            'error: {1}'.format(suite.suite_name, str(e)))
                    config = self._handler_configurations[
                        suite.handler_configuration]
                    self._release_env(config['env'])
                else:
                    remaining_suites.append(suite)
            suites_list = remaining_suites
            time.sleep(self._scheduling_interval)
        logger.info('Test suites scheduler stopped')

    def _find_matching_handler_configurations(self, suite):
        if suite.handler_configuration:
            return {
                suite.handler_configuration:
                    self._handler_configurations[suite.handler_configuration]
            }
        tags_match = lambda x, y: set(x) & set(y) == set(x)
        return {
            k: v for k, v in self._handler_configurations.iteritems()
            if tags_match(suite.requires, v.get('tags', set()))
        }

    def _lock_env(self, env_id):
        if env_id in self._locked_envs:
            return False
        self._locked_envs.add(env_id)
        return True

    def _release_env(self, env_id):
        self._locked_envs.remove(env_id)


def list_containers(quiet=False):
    return sh.docker.ps(a=True, q=quiet).strip()


def get_docker_image_id():
    image_ids = [line for line in sh.docker.images(
        ['-q', DOCKER_REPOSITORY]).strip().split(os.linesep) if len(line) > 0]
    if len(image_ids) > 1:
        raise RuntimeError(
            'Found several docker image ids instead of a single one.')
    return image_ids[0] if image_ids else None


def build_docker_image():
    docker.build(
        ['-t', '{0}:{1}'.format(DOCKER_REPOSITORY, DOCKER_TAG), '.']).wait()
    docker_image_id = get_docker_image_id()
    if not docker_image_id:
        raise RuntimeError(
            'Docker image not found after docker image was built.')


def kill_containers():
    containers = list_containers(quiet=True).replace(os.linesep, ' ')
    if containers:
        logger.info('Killing containers: {0}'.format(containers))
        docker.rm('-f', containers).wait()


def container_exit_code(container_name):
    return int(sh.docker.wait(container_name).strip())


def container_kill(container_name):
    logger.info('Killing container: {0}'.format(container_name))
    docker.rm('-f', container_name).wait()


def copy_xunit_report(suite):
    suite.copy_xunit_reports()


def test_start():
    if os.path.exists(SUITE_ENVS_DIR):
        shutil.rmtree(SUITE_ENVS_DIR)

    with open(os.environ[TEST_SUITES_PATH]) as f:
        suites_yaml = yaml.load(f.read())
    variables = suites_yaml.get('variables', {})

    build_docker_image()

    envs_dir = path.getcwd() / SUITE_ENVS_DIR

    test_suites = [
        TestSuite(suite_name,
                  suite_def,
                  envs_dir / suite_name,
                  variables) for suite_name, suite_def in
        suites_yaml['test_suites'].iteritems()]

    scheduler = SuitesScheduler(test_suites,
                                suites_yaml['handler_configurations'],
                                scheduling_interval=SCHEDULER_INTERVAL,
                                optimize=True,
                                after_suite_callback=copy_xunit_report)
    scheduler.run()


def test_run():
    test_start()
    logger.info('wait for containers exit status codes')
    containers = get_containers_names()
    exit_codes = [(c, container_exit_code(c)) for c in containers]
    logger.info('removing containers')
    for c in containers:
        container_kill(c)
    failed_containers = [(c, exit_code)
                         for c, exit_code in exit_codes
                         if exit_code != 0]
    if failed_containers:
        logger.info('Failed test suites:')
        for c, exit_code in failed_containers:
            logger.info('\t{}: exit code: {}'.format(c, exit_code))
        sys.exit(1)


def setenv(variables_path):
    setup_reports_dir()
    descriptor = os.environ['SYSTEM_TESTS_DESCRIPTOR']
    os.environ[TEST_SUITES_PATH] = build_suites_yaml('suites/suites.yaml',
                                                     variables_path,
                                                     descriptor)


def validate():
    with open(os.environ[TEST_SUITES_PATH]) as f:
        suites = yaml.load(f.read())
    for suite_name, suite in suites['test_suites'].items():
        requires = suite.get('requires')
        configuration_name = suite.get('handler_configuration')
        if requires and configuration_name:
            raise AssertionError(
                'Suite: {0} has both "requires" and "handler_configuration" '
                'set'.format(suite_name))
        elif not requires and not configuration_name:
            raise AssertionError(
                'Suite: {0} does not have "requires" or '
                '""handler_configuration" specified'.format(suite_name))
    for name, configuration in suites['handler_configurations'].iteritems():
        if 'env' not in configuration:
            raise AssertionError(
                '"{0}" handler configuration does not contain an env '
                'property'.format(name))


def cleanup():
    logger.info('Current containers:\n{0}'
                .format(list_containers()))
    kill_containers()


def setup_reports_dir():
    if not reports_dir.exists():
        reports_dir.mkdir()
    for report in reports_dir.files():
        report.remove()


def get_containers_names():
    with open(os.environ[TEST_SUITES_PATH]) as f:
        suites = yaml.load(f.read())['test_suites'].keys()
    return [s for s in suites]


def main():
    variables_path = sys.argv[1]
    setenv(variables_path)
    cleanup()
    validate()
    test_run()

if __name__ == '__main__':
    main()
