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

from cosmo_tester.test_suites.test_blueprints.nodecellar_test \
    import OpenStackNodeCellarTestBase
from cosmo_tester.test_suites.test_security.security_test_base import \
    SecurityTestBase


class SecuredOpenstackNodecellarTest(OpenStackNodeCellarTestBase,
                                     SecurityTestBase):

    def test_secured_openstack_nodecellar(self):
        self._setup_secured_manager()
        self._test_openstack_nodecellar('openstack-blueprint.yaml')

    def get_security_settings(self):
        return {
            'enabled': 'true',
            'userstore_driver': {
                'implementation':
                    'flask_securest.userstores.simple:SimpleUserstore',
                'properties': {
                    'userstore': {
                        'user1': {
                            'username': 'user1',
                            'password': 'pass1',
                            'email': 'user1@domain.dom'
                        },
                        'user2': {
                            'username': 'user2',
                            'password': 'pass2',
                            'email': 'user2@domain.dom'
                        },
                        'user3': {
                            'username': 'user3',
                            'password': 'pass3',
                            'email': 'user3@domain.dom'
                        },
                    },
                    'identifying_attribute': 'username'
                }
            },
            'authentication_providers': [
                {
                    'name': 'password',
                    'implementation': 'flask_securest.'
                                      'authentication_providers.password:'
                                      'PasswordAuthenticator',
                    'properties': {
                        'password_hash': 'plaintext'
                    }
                }
            ]
        }
