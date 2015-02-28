# Copyright 2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import mock

from botocore.waiter import WaiterModel
from botocore.exceptions import DataNotFoundError

from awscli.testutils import unittest, BaseAWSHelpOutputTest, \
    BaseAWSCommandParamsTest
from awscli.customizations.waiters import add_waiters, WaitCommand, \
    get_waiter_model_from_service_object, WaiterStateCommand, WaiterCaller, \
    WaiterStateDocBuilder, WaiterStateCommandBuilder


class TestAddWaiters(unittest.TestCase):
    def setUp(self):
        self.service_object = mock.Mock()
        self.session = mock.Mock()

        self.command_object = mock.Mock()
        self.command_object.service_object = self.service_object

        # Set up the mock service object.
        self.service_object.session = self.session

        # Set up the mock session.
        self.session.get_waiter_model.return_value = WaiterModel(
            {
                'version': 2,
                'waiters': {
                    'FooExists': {},
                }
            }
        )


    def test_add_waiters(self):
        command_table = {}
        add_waiters(command_table, self.session, self.command_object)
        # Make sure a wait command was added.
        self.assertIn('wait', command_table)
        self.assertIsInstance(command_table['wait'], WaitCommand)

    def test_add_waiters_no_waiter_names(self):
        self.session.get_waiter_model.return_value = WaiterModel(
            {
                'version': 2,
                # No waiters are specified.
                'waiters': {}
            }
        )
        command_table = {}
        add_waiters(command_table, self.session, self.command_object)
        # Make sure that no wait command was added since the service object
        # has no waiters.
        self.assertEqual(command_table, {})

    def test_add_waiters_no_service_object(self):
        command_table = {}
        self.command_object.service_object = None
        add_waiters(command_table, self.session, self.command_object)
        # Make sure that no wait command was added since no service object
        # was passed in.
        self.assertEqual(command_table, {})

    def test_add_waiter_no_waiter_config(self):
        self.session.get_waiter_model.side_effect = DataNotFoundError(
            data_path='foo')
        command_table = {}
        add_waiters(command_table, self.session, self.command_object)
        self.assertEqual(command_table, {})


class TestServicetoWaiterModel(unittest.TestCase):
    def test_service_object_to_waiter_model(self):
        service_object = mock.Mock()
        session = mock.Mock()
        service_object.session = session
        service_object.service_name = 'service'
        service_object.api_version = '2014-01-01'
        get_waiter_model_from_service_object(service_object)
        session.get_waiter_model.assert_called_with('service', '2014-01-01')

    def test_can_handle_data_errors(self):
        service_object = mock.Mock()
        session = mock.Mock()
        service_object.session = session
        service_object.service_name = 'service'
        service_object.api_version = '2014-01-01'
        session.get_waiter_model.side_effect = DataNotFoundError(
            data_path='foo')
        self.assertIsNone(
            get_waiter_model_from_service_object(service_object))


class TestWaitCommand(unittest.TestCase):
    def setUp(self):
        self.model = WaiterModel({
            'version': 2,
            'waiters': {
                'Foo': {
                    'operation': 'foo', 'maxAttempts': 1, 'delay': 1,
                    'acceptors': [],
                }
            }
        })
        self.service_object = mock.Mock()
        self.cmd = WaitCommand(self.model, self.service_object)

    def test_passes_on_lineage(self):
        child_cmd = self.cmd.subcommand_table['foo']
        self.assertEqual(len(child_cmd.lineage), 2)
        self.assertEqual(child_cmd.lineage[0], self.cmd) 
        self.assertIsInstance(child_cmd.lineage[1], WaiterStateCommand)

    def test_run_main_error(self):
        self.parsed_args = mock.Mock()
        self.parsed_args.subcommand = None
        with self.assertRaises(ValueError):
            self.cmd._run_main(self.parsed_args, None)


class TestWaitHelpOutput(BaseAWSHelpOutputTest):
    def test_wait_command_is_in_list(self):
        self.driver.main(['ec2', 'help'])
        self.assert_contains('* wait')

    def test_wait_help_command(self):
        self.driver.main(['ec2', 'wait', 'help'])
        self.assert_contains('.. _cli:aws ec2 wait:')
        self.assert_contains('Wait until a particular condition is satisfied.')
        self.assert_contains('* instance-running')
        self.assert_contains('* vpc-available')

    def test_wait_state_help_command(self):
        self.driver.main(['ec2', 'wait', 'instance-running', 'help'])
        self.assert_contains('.. _cli:aws ec2 wait instance-running:')
        self.assert_contains('``describe-instances``')
        self.assert_contains('[--filters <value>]')
        self.assert_contains('``--filters`` (list)')


class TestWait(BaseAWSCommandParamsTest):
    """ This is merely a smoke test.

    Its purpose is to test that the wait command can be run proberly for
    various services. It is by no means exhaustive.
    """
    def test_ec2_instance_running(self):
        cmdline = 'ec2 wait instance-running'
        cmdline += ' --instance-ids i-12345678 i-87654321'
        cmdline += """ --filters {"Name":"group-name","Values":["foobar"]}"""
        result = {'Filters': [{'Name': 'group-name',
                               'Values': ['foobar']}],
                  'InstanceIds': ['i-12345678', 'i-87654321']}
        self.parsed_response = {
            'Reservations': [{
                'Instances': [{
                    'State': {
                        'Name': 'running'
                    }
                }]
            }]
        }
        self.assert_params_for_cmd(cmdline, result)

    def test_dynamodb_table_exists(self):
        cmdline = 'dynamodb wait table-exists'
        cmdline += ' --table-name mytable'
        result = {"TableName": "mytable"}
        self.parsed_response = {'Table': {'TableStatus': 'ACTIVE'}}
        self.assert_params_for_cmd(cmdline, result)

    def test_elastictranscoder_jobs_complete(self):
        cmdline = 'rds wait db-instance-available'
        cmdline += ' --db-instance-identifier abc'
        result = {'DBInstanceIdentifier': 'abc'}
        self.parsed_response = {
            'DBInstances': [{
                'DBInstanceStatus': 'available'
            }]
        }
        self.assert_params_for_cmd(cmdline, result)


class TestWaiterStateCommandBuilder(unittest.TestCase):
    def setUp(self):
        self.service_object = mock.Mock()

        # Create some waiters.
        self.model = WaiterModel({
            'version': 2,
            'waiters': {
                'InstanceRunning': {
                    'description': 'my waiter description',
                    'delay': 1,
                    'maxAttempts': 10,
                    'operation': 'MyOperation',
                },
                'BucketExists': {
                    'description': 'my waiter description',
                    'operation': 'MyOperation',
                    'delay': 1,
                    'maxAttempts': 10,
                }
            }
        })

        self.waiter_builder = WaiterStateCommandBuilder(
            self.model,
            self.service_object
        )

    def test_build_waiter_state_cmds(self):
        subcommand_table = {}
        self.waiter_builder.build_all_waiter_state_cmds(subcommand_table)
        # Check the commands are in the command table
        self.assertEqual(len(subcommand_table), 2)
        self.assertIn('instance-running', subcommand_table)
        self.assertIn('bucket-exists', subcommand_table)

        # Make sure that the correct operation object was used.
        self.service_object.get_operation.assert_called_with('MyOperation')

        # Introspect the commands in the command table
        instance_running_cmd = subcommand_table['instance-running']
        bucket_exists_cmd = subcommand_table['bucket-exists']

        # Check that the instance type is correct.
        self.assertIsInstance(instance_running_cmd, WaiterStateCommand)
        self.assertIsInstance(bucket_exists_cmd, WaiterStateCommand)

        # Check the descriptions are set correctly.
        self.assertEqual(
            instance_running_cmd.DESCRIPTION,
            'my waiter description',
        )
        self.assertEqual(
            bucket_exists_cmd.DESCRIPTION,
            'my waiter description',
        )


class TestWaiterStateDocBuilder(unittest.TestCase):
    def setUp(self):
        self.waiter_config = mock.Mock()
        self.waiter_config.description = ''
        self.waiter_config.operation = 'MyOperation'

        # Set up the acceptors.
        self.success_acceptor = mock.Mock()
        self.success_acceptor.state = 'success'
        self.fail_acceptor = mock.Mock()
        self.fail_acceptor.state = 'failure'
        self.error_acceptor = mock.Mock()
        self.error_acceptor.state = 'error'
        self.waiter_config.acceptors = [
            self.fail_acceptor,
            self.success_acceptor,
            self.error_acceptor
        ]

        self.doc_builder = WaiterStateDocBuilder(self.waiter_config)

    def test_config_provided_description(self):
        # Description is provided by the config file
        self.waiter_config.description = 'my description'
        description = self.doc_builder.build_waiter_state_description()
        self.assertEqual(description, 'my description')

    def test_error_acceptor(self):
        self.success_acceptor.matcher = 'error'
        self.success_acceptor.expected = 'MyException'
        description = self.doc_builder.build_waiter_state_description()
        self.assertEqual(
            description,
            'Wait until MyException is thrown when polling with '
            '``my-operation``.'
        )

    def test_status_acceptor(self):
        self.success_acceptor.matcher = 'status'
        self.success_acceptor.expected = 200
        description = self.doc_builder.build_waiter_state_description()
        self.assertEqual(
            description,
            'Wait until 200 response is received when polling with '
            '``my-operation``.'
        )

    def test_path_acceptor(self):
        self.success_acceptor.matcher = 'path'
        self.success_acceptor.argument = 'MyResource.name'
        self.success_acceptor.expected = 'running'
        description = self.doc_builder.build_waiter_state_description()
        self.assertEqual(
            description,
            'Wait until JMESPath query MyResource.name returns running when '
            'polling with ``my-operation``.'
        )

    def test_path_all_acceptor(self):
        self.success_acceptor.matcher = 'pathAll'
        self.success_acceptor.argument = 'MyResource[].name'
        self.success_acceptor.expected = 'running'
        description = self.doc_builder.build_waiter_state_description()
        self.assertEqual(
            description,
            'Wait until JMESPath query MyResource[].name returns running for '
            'all elements when polling with ``my-operation``.'
        )

    def test_path_any_acceptor(self):
        self.success_acceptor.matcher = 'pathAny'
        self.success_acceptor.argument = 'MyResource[].name'
        self.success_acceptor.expected = 'running'
        description = self.doc_builder.build_waiter_state_description()
        self.assertEqual(
            description,
            'Wait until JMESPath query MyResource[].name returns running for '
            'any element when polling with ``my-operation``.'
        )


class TestWaiterCaller(unittest.TestCase):
    def test_invoke(self):
        waiter = mock.Mock()
        waiter_name = 'my_waiter'
        operation_object = mock.Mock()
        operation_object.service.get_waiter.return_value = waiter

        parameters = {'Foo': 'bar', 'Baz': 'biz'}
        parsed_globals = mock.Mock()
        parsed_globals.region = 'us-east-1'
        parsed_globals.endpoint_url = 'myurl'
        parsed_globals.verify_ssl = True

        waiter_caller = WaiterCaller(waiter_name)
        waiter_caller.invoke(operation_object, parameters, parsed_globals)
        # Make sure the endpoint was created properly
        operation_object.service.get_endpoint.assert_called_with(
            region_name=parsed_globals.region,
            endpoint_url=parsed_globals.endpoint_url,
            verify=parsed_globals.verify_ssl
        )

        # Ensure the wait command was called properly.
        waiter.wait.assert_called_with(
            Foo='bar', Baz='biz')


class TestWaiterStateCommand(unittest.TestCase):
    def test_create_help_command(self):
        operation_object = mock.Mock()
        operation_object.model.input_shape = None
        cmd = WaiterStateCommand(
            name='wait-state', parent_name='wait',
            operation_object=operation_object,
            operation_caller=mock.Mock(),
            service_object=mock.Mock()
        )
        cmd.DESCRIPTION = 'mydescription'
        cmd.create_help_command()
        # Make sure that the description is used and output shape is set
        # to None for creating the help command.
        self.assertEqual(operation_object.documentation, 'mydescription')
        self.assertIsNone(operation_object.model.output_shape)
