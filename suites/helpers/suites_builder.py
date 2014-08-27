#! /usr/bin/env python
# flake8: NOQA

import sys
import os
import json
import tempfile
import logging


logger = logging.getLogger('suites_builder')
logger.setLevel(logging.INFO)


def build_suites_json(all_suites_json_path):
    env_system_tests_suites = os.environ['SYSTEM_TESTS_SUITES']
    env_custom_suite = os.environ['SYSTEM_TESTS_CUSTOM_SUITE']
    env_custom_suite_name = os.environ['SYSTEM_TESTS_CUSTOM_SUITE_NAME']
    env_custom_tests_to_run = os.environ['SYSTEM_TESTS_CUSTOM_TESTS_TO_RUN']
    env_custom_cloudify_config = os.environ['SYSTEM_TESTS_CUSTOM_CLOUDIFY_CONFIG']
    env_custom_handler_module = os.environ['SYSTEM_TESTS_CUSTOM_HANDLER_MODULE']

    logger.info('Creating suites json configuration:\n'
                '\tSYSTEM_TESTS_SUITES={}\n'
                '\tSYSTEM_TESTS_CUSTOM_SUITE={}\n'
                '\tSYSTEM_TESTS_CUSTOM_SUITE_NAME={}\n'
                '\tSYSTEM_TESTS_CUSTOM_TESTS_TO_RUN={}\n'
                '\tSYSTEM_TESTS_CUSTOM_CLOUDIFY_CONFIG={}\n'
                '\tSYSTEM_TESTS_CUSTOM_HANDLER_MODULE={}'
                .format(env_system_tests_suites,
                        env_custom_suite,
                        env_custom_suite_name,
                        env_custom_tests_to_run,
                        env_custom_cloudify_config,
                        env_custom_handler_module))

    tests_suites = env_system_tests_suites.split(',')
    custom_suite = env_custom_suite in ['yes', 'true']
    custom_suite_name = env_custom_suite_name
    custom_tests_to_run = env_custom_tests_to_run
    custom_cloudify_config = env_custom_cloudify_config
    custom_handler_module = env_custom_handler_module

    suites_json_path = tempfile.mktemp(prefix='suites-', suffix='.json')

    if custom_suite:
        suites = [{
            'suite_name': custom_suite_name,
            'tests_to_run': custom_tests_to_run,
            'cloudify_test_config': custom_cloudify_config,
            'cloudify_test_handler_module': custom_handler_module
        }]
    else:
        with open(all_suites_json_path) as f:
            all_suites = json.loads(f.read())
        suites = []
        for suite in all_suites:
            if suite['suite_name'] in tests_suites:
                suites.append(suite)

    with open(suites_json_path, 'w') as f:
        f.write(json.dumps(suites))

    return suites_json_path
