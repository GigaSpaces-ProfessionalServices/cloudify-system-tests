########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
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
from path import path

from cloudify_rest_client.client import CloudifyClient
from cosmo_tester.framework import util

from cosmo_tester.framework.testenv import TestCase


RABBITMQ_USERNAME_KEY = 'rabbitmq_username'
RABBITMQ_PASSWORD_KEY = 'rabbitmq_password'
RABBITMQ_USERNAME_VALUE = 'guest'
RABBITMQ_PASSWORD_VALUE = 'guest'


class NodecellarNackwardsCompatibilityTestBase(TestCase):

    def setup_manager(self):
        self._copy_manager_blueprint()
        self._update_manager_blueprint()
        self._bootstrap()
        self._running_env_setup()

    def _copy_manager_blueprint(self):
        inputs_path, mb_path = util.generate_unique_configurations(
            workdir=self.workdir,
            original_inputs_path=self.env.cloudify_config_path,
            original_manager_blueprint_path=self.env._manager_blueprint_path)
        self.test_manager_blueprint_path = path(mb_path)
        self.test_inputs_path = path(inputs_path)
        self.test_manager_types_path = os.path.join(
            self.workdir, 'manager-blueprint/types/manager-types.yaml')

    def _update_manager_blueprint(self):
        props = self.get_manager_blueprint_inputs_override()
        with util.YamlPatcher(self.test_inputs_path) as patch:
            for key, value in props.items():
                patch.set_value(key, value)

    def get_manager_blueprint_inputs_override(self):
        return {
            RABBITMQ_USERNAME_KEY: RABBITMQ_USERNAME_VALUE,
            RABBITMQ_PASSWORD_KEY: RABBITMQ_PASSWORD_VALUE
        }

    def _bootstrap(self):
        self.cfy.bootstrap(blueprint_path=self.test_manager_blueprint_path,
                           inputs_file=self.test_inputs_path,
                           task_retries=5,
                           install_plugins=self.env.install_plugins)
        self.addCleanup(self.cfy.teardown)

    def set_rest_client(self):
        self.client = CloudifyClient(host=self.env.management_ip)

    def _running_env_setup(self):
        self.env.management_ip = self.cfy.get_management_ip()
        self.set_rest_client()

        def clean_mgmt_ip():
            self.env.management_ip = None
        self.addCleanup(clean_mgmt_ip)

        response = self.client.manager.get_status()
        if not response['status'] == 'running':
            raise RuntimeError('Manager at {0} is not running.'
                               .format(self.env.management_ip))
