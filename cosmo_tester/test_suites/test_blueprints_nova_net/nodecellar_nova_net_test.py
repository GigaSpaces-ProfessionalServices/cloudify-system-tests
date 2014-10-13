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


__author__ = 'boris'

import json

import requests

from cosmo_tester.framework.testenv import TestCase
from cosmo_tester.framework.util import YamlPatcher
from cosmo_tester.framework.git_helper import clone
import cosmo_tester.test_suites.test_blueprints.nodecellar_test as NodeApp


NODECELLAR_URL = "https://github.com/cloudify-cosmo/" \
                 "cloudify-nodecellar-openstack.git"

class NodecellarNovaNetAppTest(TestCase):

    def test_nodecellar(self):

        self.repo_dir = clone(NODECELLAR_URL, self.workdir, branch="CFY-999-Nova-Net")
        self.blueprint_yaml = self.repo_dir / 'blueprint_nova_net.yaml'
        self.modify_blueprint()

        before, after = self.upload_deploy_and_execute_install()

        self.post_install_assertions(before, after)

        self.execute_uninstall()

        NodeApp.post_uninstall_assertions()

    def modify_blueprint(self):
        with YamlPatcher(self.blueprint_yaml) as patch:
            vm_type_path = 'node_types.vm_host.properties'
            patch.merge_obj('{0}.server'.format(vm_type_path), {
                'image_name': self.env.ubuntu_image_name,
                'flavor_name': self.env.flavor_name
            })

    def post_install_assertions(self, before_state, after_state):
        delta = self.get_manager_state_delta(before_state, after_state)

        self.logger.info('Current manager state: {0}'.format(delta))

        self.assertEqual(len(delta['blueprints']), 1,
                         'blueprint: {0}'.format(delta))

        self.assertEqual(len(delta['deployments']), 1,
                         'deployment: {0}'.format(delta))

        deployment_from_list = delta['deployments'].values()[0]

        deployment_by_id = self.client.deployments.get(deployment_from_list.id)
        self.deployment_id = deployment_from_list.id

        executions = self.client.executions.list(
            deployment_id=deployment_by_id.id)

        self.assertEqual(len(executions), 2,
                         'There should be 2 executions but are: {0}'.format(
                             executions))

        execution_from_list = executions[0]
        execution_by_id = self.client.executions.get(execution_from_list.id)

        self.assertEqual(execution_from_list.id, execution_by_id.id)
        self.assertEqual(execution_from_list.workflow_id,
                         execution_by_id.workflow_id)
        self.assertEqual(execution_from_list['blueprint_id'],
                         execution_by_id['blueprint_id'])

        self.assertEqual(len(delta['deployment_nodes']), 1,
                         'deployment_nodes: {0}'.format(delta))

        self.assertEqual(len(delta['node_state']), 1,
                         'node_state: {0}'.format(delta))

        self.assertEqual(len(delta['nodes']), 7,
                         'nodes: {0}'.format(delta))

        nodes_state = delta['node_state'].values()[0]
        self.assertEqual(len(nodes_state), 7,
                         'nodes_state: {0}'.format(nodes_state))

        self.public_ip = None
        for key, value in nodes_state.items():
            if '_vm' in key:
                self.assertTrue('ip' in value['runtime_properties'],
                                'Missing ip in runtime_properties: {0}'
                                .format(nodes_state))
                self.assertEqual(value['state'], 'started',
                                 'vm node should be started: {0}'
                                 .format(nodes_state))
            elif key.startswith('floatingip'):
                self.public_ip = value['runtime_properties'][
                    'floating_ip_address']

        self.assertIsNotNone(self.public_ip,
                             'Could not find the "floatingip" node for '
                             'retrieving the public IP')

        events, total_events = self.client.events.get(execution_by_id.id)

        self.assertGreater(len(events), 0,
                           'Expected at least 1 event for execution id: {0}'
                           .format(execution_by_id.id))

        nodejs_server_page_response = requests.get('http://{0}:8080'
                                                   .format(self.public_ip))
        self.assertEqual(200, nodejs_server_page_response.status_code,
                         'Failed to get home page of nodecellar app')
        page_title = 'Node Cellar'
        self.assertTrue(page_title in nodejs_server_page_response.text,
                        'Expected to find {0} in web server response: {1}'
                        .format(page_title, nodejs_server_page_response))

        wines_page_response = requests.get('http://{0}:8080/wines'.format(
            self.public_ip))
        self.assertEqual(200, wines_page_response.status_code,
                         'Failed to get the wines page on nodecellar app ('
                         'probably means a problem with the connection to '
                         'MongoDB)')

        try:
            wines_json = json.loads(wines_page_response.text)
            if type(wines_json) != list:
                self.fail('Response from wines page is not a JSON list: {0}'
                          .format(wines_page_response.text))

            self.assertGreater(len(wines_json), 0,
                               'Expected at least 1 wine data in nodecellar '
                               'app; json returned on wines page is: {0}'
                               .format(wines_page_response.text))
        except BaseException:
            self.fail('Response from wines page is not a valid JSON: {0}'
                      .format(wines_page_response.text))
