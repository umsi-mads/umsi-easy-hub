#!/usr/bin/env python

# This script deploys the control node CloudFormation, which will then
# automatically deploy and configure the cluster CloudFormation and kubernetes
# deployment.

import os
import stat
import sys
import boto3
import re
import argparse
import json
from shutil import copyfile
import yaml
import time

# This should never have to change. This is used in tagging/identifying
# all aws resources
project = "umsi-easy-hub"

secrets = boto3.client('secretsmanager')
s3 = boto3.client('s3')
cloudformation = boto3.client('cloudformation')


def generate_ssh_key(config):
    """Generate an SSH key pair from EC2."""
    name = "{}-{}".format(config["project"], config["tag"])
    file = "{}.pem".format(name)

    # Make sure we can open the file for writing before requesting key.
    with open(file, 'w') as f:
        ec2 = boto3.client('ec2')
        response = ec2.create_key_pair(KeyName=name)
        f.write(response['KeyMaterial'])

    # Only owner can only read
    os.chmod(file, stat.S_IREAD)

    return response['KeyName']


def create_bucket(config):
    """Create an S3 bucket for use by this cluster's control node."""

    bucket_name = get_bucket_name(config)
    response = s3.create_bucket(ACL='private', Bucket=bucket_name)
    print("Created S3 bucket {}".format(bucket_name))

    return bucket_name


def get_bucket_name(config):
    """Generate the name of the S3 bucket."""
    return "-".join([config['account_id'], config['project'], config['tag']])


def stack_name(config):
    """Generate the name of the CloudFormation stack."""
    return '{}-{}-control-node'.format(config['project'], config['tag'])


def upload_cluster_scripts(config):
    """Upload the src/ folder to the s3 bucket."""

    for filename in os.listdir('src'):
        s3.upload_file('src/' + filename, get_bucket_name(config), filename)

    print("Uploaded scripts to bucket.")


def create_control_node(config):
    """Perform the deployment of the control node stack."""

    with open('src/control_node_cf.yaml') as template_fileobj:
        template_data = template_fileobj.read()
    cloudformation.validate_template(TemplateBody=template_data)

    cloudformation.create_stack(
        TemplateBody=template_data,
        StackName=stack_name(config),
        Parameters=[{'ParameterKey': 'BillingTag',
                     'ParameterValue': '{}-{}'.format(config['project'],
                                                      config['tag']),
                     'UsePreviousValue': False},
                    {'ParameterKey': 'ScriptBucket',
                     'ParameterValue': get_bucket_name(config),
                     'UsePreviousValue': False},
                    {'ParameterKey': 'KeyName',
                     'ParameterValue': config['ssh_key_name'],
                     'UsePreviousValue': False},
                    {'ParameterKey': 'Domain',
                     'ParameterValue': config['domain'],
                     'UsePreviousValue': False},
                    {'ParameterKey': 'Tag',
                     'ParameterValue': config['tag'],
                     'UsePreviousValue': False}],
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )
    print("Uploaded deployment spec. CloudFormation will take it from here.")


def upload_ssh_key(key_name):
    """Upload the contents of the local SSH key into the secret."""
    id = "{}.pem".format(key_name)
    secrets.update_secret(SecretId=id, SecretString=open(id, 'r').read())
    print("Uploaded SSH key.")


def fail(msg):
    """Print and quit."""
    print(msg)
    sys.exit(1)


if __name__ == "__main__":

    # The only argument required is the tag that makes this deployment and all
    # its resources unique.
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tag", "-t",
        required=False,
        default="test",
        help="tag to build, must be alphanumeric like \"prod\" or \"test\"")

    parser.add_argument(
        "--project", "-p",
        required=False,
        default="umsi-easy-hub",
        help="name of project, used in all AWS resources")

    parser.add_argument(
        "--domain",
        required=True,
        help="The FQDN which will host the hub")

    args = parser.parse_args()

    # We plan to allow different names, but this project name is hard coded all
    # over this project. We need to convert it to an input.
    if args.project != "umsi-easy-hub":
        fail("Using a different project name is currently unsupported.")

    # This is a current limitation due to our naming scheme.
    # An ELBV2::TargetGroup has a max name length of 32.
    # Our template name is: ueh-${Tag}-target-group-https, leaving 9 for tag.
    # The control node will pass, but the cluster will fail.
    if len(args.tag) > 9:
        fail("Due to limitations in AWS, the tag name must have a length of "
             "at most 9. Your tag '{}' has length {}.".format(
                 args.tag, len(args.tag)))

    # Generate basic config
    config = {}
    config['tag'] = args.tag
    config['project'] = args.project
    config['domain'] = args.domain
    config['account_id'] = boto3.client(
        'sts').get_caller_identity().get('Account')
    config['ssh_key_name'] = generate_ssh_key(config)
    print(config)

    # Create an S3 bucket
    create_bucket(config)

    # Upload all files in src/ to the bucket
    upload_cluster_scripts(config)

    # Finally, deploy the control node CloudFormation
    create_control_node(config)

    name = stack_name(config)
    print("Waiting for your CloudFormation to finish contructing")
    cloudformation.get_waiter('stack_create_complete').wait(StackName=name)

    upload_ssh_key(config['ssh_key_name'])

    outputs = boto3.resource('cloudformation').Stack(name).outputs
    instance = next(
        (x for x in outputs if x['OutputKey'] == 'Instance'), None)

    if instance:
        print("Connect to your control node: ssh -i {}.pem ec2-user@{}".format(
            config['ssh_key_name'],
            boto3.resource('ec2').Instance(
                instance['OutputValue']).public_ip_address
        ))
    else:
        fail("There was a problem finding the instance in your new stack. "
             "Check out the AWS console for more details.")
